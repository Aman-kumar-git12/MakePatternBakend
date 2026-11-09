"""Soft delete: deleted questions/folders are kept in `trash` for 30 days and can be restored."""
import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pymongo.database import Database
from pymongo.errors import BulkWriteError

from app.db import new_id, now_utc, to_iso
from app.services.repo import delete_questions_cascade, descendant_folder_ids

logger = logging.getLogger("makepattern.trash")

TRASH_DAYS = 30
MAX_TRASH_BYTES = 12 * 1024 * 1024  # stay under Mongo's 16MB document cap


def _strip(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: v for k, v in d.items() if k != "_id"} for d in docs]


def _capture(db: Database, user_id: str, question_ids: List[str], folder_ids: List[str]) -> Dict[str, Any]:
    return {
        "folders": _strip(list(db.folders.find({"user_id": user_id, "id": {"$in": folder_ids}}))) if folder_ids else [],
        "questions": _strip(list(db.questions.find({"user_id": user_id, "id": {"$in": question_ids}}))) if question_ids else [],
        "solutions": _strip(list(db.solutions.find({"question_id": {"$in": question_ids}}))) if question_ids else [],
        "test_cases": _strip(list(db.test_cases.find({"question_id": {"$in": question_ids}}))) if question_ids else [],
        "bookmarks": _strip(list(db.bookmarks.find({"user_id": user_id, "question_id": {"$in": question_ids}}))) if question_ids else [],
    }


def _store(db: Database, user_id: str, kind: str, title: str, payload: Dict[str, Any]) -> Optional[str]:
    if len(json.dumps(payload, default=str)) > MAX_TRASH_BYTES:
        logger.warning("Trash payload too large for user %s; deleting permanently", user_id)
        return None
    now = now_utc()
    trash_id = new_id()
    db.trash.insert_one({
        "id": trash_id,
        "user_id": user_id,
        "kind": kind,
        "title": title[:300],
        "deleted_at": to_iso(now),
        "expires_at": now + timedelta(days=TRASH_DAYS),  # BSON date -> TTL index purges it
        "question_count": len(payload["questions"]),
        "folder_count": len(payload["folders"]),
        "payload": payload,
    })
    return trash_id


def trash_questions(db: Database, user_id: str, question_ids: List[str], title: Optional[str] = None) -> Optional[str]:
    qids = [q["id"] for q in db.questions.find({"user_id": user_id, "id": {"$in": question_ids}}, {"_id": 0, "id": 1, "title": 1})]
    if not qids:
        return None
    payload = _capture(db, user_id, qids, [])
    if title is None:
        title = payload["questions"][0].get("title") or "Question" if len(qids) == 1 else f"{len(qids)} questions"
    kind = "question" if len(qids) == 1 else "bulk"
    trash_id = _store(db, user_id, kind, title, payload)
    delete_questions_cascade(db, qids)
    return trash_id


def trash_folder(db: Database, user_id: str, folder_id: str) -> (Optional[str], List[str]):
    folders = list(db.folders.find({"user_id": user_id}, {"_id": 0, "id": 1, "parent_id": 1, "name": 1}))
    root = next((f for f in folders if f["id"] == folder_id), None)
    if not root:
        return None, []
    fids = list(descendant_folder_ids(folders, folder_id) | {folder_id})
    qids = [q["id"] for q in db.questions.find({"user_id": user_id, "folder_id": {"$in": fids}}, {"_id": 0, "id": 1})]
    payload = _capture(db, user_id, qids, fids)
    trash_id = _store(db, user_id, "folder", root.get("name") or "Folder", payload)
    delete_questions_cascade(db, qids)
    db.folders.delete_many({"user_id": user_id, "id": {"$in": fids}})
    return trash_id, fids


def _insert_ignoring_duplicates(db: Database, coll: str, docs: List[Dict[str, Any]]) -> None:
    if not docs:
        return
    try:
        db[coll].insert_many([dict(d) for d in docs], ordered=False)
    except BulkWriteError:
        pass  # an item with the same id already exists (e.g. restored twice); keep the live one


def restore(db: Database, user_id: str, trash_id: str) -> Dict[str, Any]:
    item = db.trash.find_one({"id": trash_id, "user_id": user_id})
    if not item:
        raise HTTPException(status_code=404, detail="This item is no longer in the trash.")
    p = item.get("payload") or {}
    folders: List[Dict[str, Any]] = p.get("folders") or []
    questions: List[Dict[str, Any]] = p.get("questions") or []

    restored_fids = {f["id"] for f in folders}
    live_fids = {f["id"] for f in db.folders.find({"user_id": user_id}, {"_id": 0, "id": 1})}
    valid_fids = restored_fids | live_fids
    for f in folders:
        if f.get("parent_id") and f["parent_id"] not in valid_fids:
            f["parent_id"] = None  # original parent is gone -> restore at root
    for q in questions:
        if q.get("folder_id") and q["folder_id"] not in valid_fids:
            q["folder_id"] = None  # -> unfiled

    _insert_ignoring_duplicates(db, "folders", folders)
    _insert_ignoring_duplicates(db, "questions", questions)
    _insert_ignoring_duplicates(db, "solutions", p.get("solutions") or [])
    _insert_ignoring_duplicates(db, "test_cases", p.get("test_cases") or [])
    _insert_ignoring_duplicates(db, "bookmarks", p.get("bookmarks") or [])
    db.trash.delete_one({"id": trash_id, "user_id": user_id})

    root_folder = next((f for f in folders if f.get("parent_id") not in restored_fids), None)
    return {
        "kind": item.get("kind"),
        "restored_questions": len(questions),
        "restored_folders": len(folders),
        "folder_id": root_folder["id"] if root_folder else (questions[0].get("folder_id") if questions else None),
        "question_ids": [q["id"] for q in questions],
    }


def purge_expired(db: Database, user_id: Optional[str] = None) -> None:
    """TTL index does this in production; this keeps listings exact (and works in tests)."""
    q: Dict[str, Any] = {"expires_at": {"$lt": now_utc()}}
    if user_id:
        q["user_id"] = user_id
    db.trash.delete_many(q)
