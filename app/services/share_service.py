"""Pattern sharing: owner-side share records, immutable public snapshots, and forking."""
import json
import logging
import secrets
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pymongo.database import Database

from app.db import new_id, now_iso
from app.services.folder_service import build_tree_for_folder, build_tree_for_user
from app.services.repo import descendant_folder_ids, new_question_doc, next_position, to_responses

logger = logging.getLogger("makepattern.share")

MAX_SNAPSHOT_BYTES = 12 * 1024 * 1024  # Mongo documents are capped at 16MB


def _user_filter(user_id: str) -> Dict[str, Any]:
    return {"$or": [{"id": user_id}, {"_id": user_id}]}


def get_share(db: Database, user_id: str, folder_id: str) -> Optional[Dict[str, Any]]:
    doc = db.users.find_one({**_user_filter(user_id)}, {"shared_patterns": 1})
    for s in (doc or {}).get("shared_patterns") or []:
        if s.get("folder_id") == folder_id:
            return s
    return None


def _set_share_fields(db: Database, user_id: str, folder_id: str, fields: Dict[str, Any]) -> None:
    """Update the folder's share record. Duplicate records for the same folder (left by an
    older race) are collapsed into one, so disabling or regenerating can't miss a live link."""
    owner = db.users.find_one(_user_filter(user_id), {"_id": 1, "shared_patterns": 1})
    if not owner:
        return
    kept: list = []
    seen = False
    for s in owner.get("shared_patterns") or []:
        if s.get("folder_id") == folder_id:
            if seen:
                continue
            seen = True
            s = {**s, **fields}
        kept.append(s)
    db.users.update_one({"_id": owner["_id"]}, {"$set": {"shared_patterns": kept}})


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def _sanitize_tree(node: Dict[str, Any]) -> Dict[str, Any]:
    node["user_id"] = ""
    node["solved_count"] = 0
    node["progress_percentage"] = 0.0
    for q in node.get("questions") or []:
        q.update({"status": "Not Started", "is_bookmarked": False, "solved_at": None, "attempts": 0,
                  "time_spent_minutes": 0, "next_review_at": None, "last_reviewed_at": None,
                  "review_count": 0, "review_interval_days": 0})
    for sf in node.get("subfolders") or []:
        _sanitize_tree(sf)
    return node


def capture_snapshot(db: Database, user_id: str, folder_id: str) -> Dict[str, Any]:
    if folder_id == "all":
        trees = build_tree_for_user(db, user_id)
        share_type = "all"
        questions = list(db.questions.find({"user_id": user_id}, {"_id": 0}))
    else:
        tree = build_tree_for_folder(db, user_id, folder_id)
        if not tree:
            raise HTTPException(status_code=404, detail="Folder not found")
        trees = [tree]
        share_type = "single"
        folders = list(db.folders.find({"user_id": user_id}, {"_id": 0, "id": 1, "parent_id": 1}))
        ids = descendant_folder_ids(folders, folder_id) | {folder_id}
        questions = list(db.questions.find({"user_id": user_id, "folder_id": {"$in": list(ids)}}, {"_id": 0}))

    q_map: Dict[str, Any] = {}
    for resp in to_responses(db, questions, set(), None):
        d = resp.model_dump(mode="json")
        d.update({"user_id": "", "status": "Not Started", "is_bookmarked": False, "solved_at": None, "attempts": 0,
                  "time_spent_minutes": 0, "next_review_at": None, "last_reviewed_at": None,
                  "review_count": 0, "review_interval_days": 0})
        q_map[d["id"]] = d

    snap = {
        "share_type": share_type,
        "patterns": [_sanitize_tree(t.model_dump(mode="json")) for t in trees],
        "questions": q_map,
    }
    if len(json.dumps(snap)) > MAX_SNAPSHOT_BYTES:
        raise HTTPException(status_code=413, detail="This pattern is too large to share as one link. Share a smaller sub-pattern instead.")
    return snap


def _save_snapshot(db: Database, share_id: str, user_id: str, owner_name: str, folder_id: str, folder_name: str, snap: Dict[str, Any]) -> None:
    db.share_snapshots.update_one(
        {"share_id": share_id},
        {"$set": {
            "share_id": share_id,
            "user_id": user_id,
            "owner_name": owner_name,
            "folder_id": folder_id,
            "folder_name": folder_name,
            "is_active": True,
            "created_at": now_iso(),
            **snap,
        }},
        upsert=True,
    )


# ---------------------------------------------------------------------------
# Owner actions
# ---------------------------------------------------------------------------

def create_or_enable_share(db: Database, user, folder_id: str, folder_name: str) -> Dict[str, Any]:
    now = now_iso()
    existing = get_share(db, user.id, folder_id)
    if existing:
        _set_share_fields(db, user.id, folder_id, {"is_active": True, "updated_at": now, "folder_name": folder_name})
        share_id = existing["share_id"]
        snap_exists = db.share_snapshots.find_one({"share_id": share_id}, {"_id": 1})
        if snap_exists:
            db.share_snapshots.update_one({"share_id": share_id}, {"$set": {"is_active": True}})
        else:
            _save_snapshot(db, share_id, user.id, user.display_name, folder_id, folder_name, capture_snapshot(db, user.id, folder_id))
        return get_share(db, user.id, folder_id)  # type: ignore[return-value]

    snap = capture_snapshot(db, user.id, folder_id)
    share = {
        "share_id": secrets.token_urlsafe(16),
        "folder_id": folder_id,
        "folder_name": folder_name,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    # Atomic: only push if this folder has no share yet (a double-click can't create two links).
    owner = db.users.find_one(_user_filter(user.id), {"_id": 1})
    if not owner:
        raise HTTPException(status_code=404, detail="User not found")
    pushed = db.users.update_one(
        {"_id": owner["_id"], "shared_patterns.folder_id": {"$ne": folder_id}},
        {"$push": {"shared_patterns": share}},
    )
    if pushed.modified_count == 0:
        # Another request created the share first: reuse it.
        return create_or_enable_share(db, user, folder_id, folder_name)
    _save_snapshot(db, share["share_id"], user.id, user.display_name, folder_id, folder_name, snap)
    return share


def disable_share(db: Database, user_id: str, folder_id: str) -> Optional[Dict[str, Any]]:
    if not get_share(db, user_id, folder_id):
        return None
    _set_share_fields(db, user_id, folder_id, {"is_active": False, "updated_at": now_iso()})
    db.share_snapshots.update_many({"user_id": user_id, "folder_id": folder_id}, {"$set": {"is_active": False}})
    return get_share(db, user_id, folder_id)


def regenerate_share(db: Database, user, folder_id: str, folder_name: str) -> Dict[str, Any]:
    """Kill the old link for good and issue a new one with a fresh snapshot."""
    snap = capture_snapshot(db, user.id, folder_id)
    if not get_share(db, user.id, folder_id):
        return create_or_enable_share(db, user, folder_id, folder_name)
    new_share_id = secrets.token_urlsafe(16)
    db.share_snapshots.delete_many({"user_id": user.id, "folder_id": folder_id})
    _set_share_fields(db, user.id, folder_id, {"share_id": new_share_id, "is_active": True, "updated_at": now_iso(), "folder_name": folder_name})
    _save_snapshot(db, new_share_id, user.id, user.display_name, folder_id, folder_name, snap)
    return get_share(db, user.id, folder_id)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Public access
# ---------------------------------------------------------------------------

def resolve_public_snapshot(db: Database, share_id: str) -> Dict[str, Any]:
    """The owner's share record is the authority; the snapshot is only content."""
    not_found = HTTPException(status_code=404, detail="Shared pattern not found, revoked, or sharing has been disabled by the owner.")
    if not share_id or len(share_id) > 64:
        raise not_found
    owner = db.users.find_one({"shared_patterns.share_id": share_id}, {"id": 1, "full_name": 1, "email": 1, "shared_patterns": 1})
    if not owner:
        raise not_found
    share = next((s for s in owner.get("shared_patterns") or [] if s.get("share_id") == share_id), None)
    if not share or not share.get("is_active"):
        raise not_found

    snap = db.share_snapshots.find_one({"share_id": share_id}, {"_id": 0})
    if snap and snap.get("is_active") is False:
        raise not_found
    if not snap:
        # Legacy share created before snapshots existed: freeze it now.
        owner_id = owner.get("id") or str(owner.get("_id"))
        owner_name = owner.get("full_name") or "Curator"
        data = capture_snapshot(db, owner_id, share["folder_id"])
        _save_snapshot(db, share_id, owner_id, owner_name, share["folder_id"], share.get("folder_name") or "Pattern", data)
        snap = db.share_snapshots.find_one({"share_id": share_id}, {"_id": 0})
    return snap  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Fork a shared snapshot into the viewer's workspace
# ---------------------------------------------------------------------------

def fork_snapshot(db: Database, user_id: str, snap: Dict[str, Any]) -> Dict[str, Any]:
    now = now_iso()
    q_map: Dict[str, Any] = snap.get("questions") or {}
    folders: List[Dict[str, Any]] = []
    questions: List[Dict[str, Any]] = []
    solutions: List[Dict[str, Any]] = []
    test_cases: List[Dict[str, Any]] = []

    def copy_node(node: Dict[str, Any], parent_id: Optional[str], position: int, name_override: Optional[str] = None) -> str:
        fid = new_id()
        folders.append({
            "id": fid, "user_id": user_id, "parent_id": parent_id,
            "name": name_override or node.get("name") or "Pattern",
            "description": node.get("description") or "", "tags": node.get("tags") or [],
            "position": position, "created_at": now, "updated_at": now,
        })
        for qi, item in enumerate(node.get("questions") or []):
            full = q_map.get(item.get("id")) or item
            qid = new_id()
            questions.append(new_question_doc(
                user_id, id=qid, folder_id=fid, title=full.get("title") or "Untitled",
                problem_url=full.get("problem_url") or "", problem_statement=full.get("problem_statement") or "",
                notes=full.get("notes") or "", difficulty=full.get("difficulty") or "Medium",
                tags=full.get("tags") or [], position=qi,
                leetcode_slug=full.get("leetcode_slug"), leetcode_id=full.get("leetcode_id"),
            ))
            for s in full.get("solutions") or []:
                solutions.append({**{k: v for k, v in s.items() if k not in ("id", "question_id")},
                                  "id": new_id(), "question_id": qid, "user_id": user_id,
                                  "created_at": now, "updated_at": now})
            for t in full.get("test_cases") or []:
                test_cases.append({**{k: v for k, v in t.items() if k not in ("id", "question_id")},
                                   "id": new_id(), "question_id": qid, "user_id": user_id,
                                   "created_at": now, "updated_at": now})
        for si, sub in enumerate(node.get("subfolders") or []):
            copy_node(sub, fid, si)
        return fid

    patterns = snap.get("patterns") or []
    owner = snap.get("owner_name") or "Curator"
    base_name = snap.get("folder_name") or (patterns[0].get("name") if patterns else "Shared Pattern")
    root_name = f"{base_name} (from {owner})"
    root_pos = next_position(db, "folders", {"user_id": user_id, "parent_id": None})
    if snap.get("share_type") == "all" or len(patterns) != 1:
        root_id = new_id()
        folders.append({"id": root_id, "user_id": user_id, "parent_id": None, "name": root_name, "description": "",
                        "tags": [], "position": root_pos, "created_at": now, "updated_at": now})
        for i, p in enumerate(patterns):
            copy_node(p, root_id, i)
    else:
        root_id = copy_node(patterns[0], None, root_pos, name_override=root_name)

    if len(questions) > 5000:
        raise HTTPException(status_code=413, detail="This shared pattern is too large to copy.")
    if folders:
        db.folders.insert_many(folders)
    if questions:
        db.questions.insert_many(questions)
    if solutions:
        db.solutions.insert_many(solutions)
    if test_cases:
        db.test_cases.insert_many(test_cases)
    for coll in (folders, questions, solutions, test_cases):  # insert_many mutates with _id
        for d in coll:
            d.pop("_id", None)
    return {"folder_id": root_id, "folder_name": root_name, "questions_imported": len(questions)}
