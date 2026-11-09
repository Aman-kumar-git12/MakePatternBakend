from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException
from pymongo.database import Database

from app.db import parse_tags, ts
from app.schemas.folder import FolderTreeResponse
from app.schemas.question import QuestionListItem
from app.services.repo import bookmarked_ids, descendant_folder_ids, to_list_item


def _sort_key(d: Dict[str, Any]):
    return (int(d.get("position") or 0), str(d.get("created_at") or ""))


def validate_folder_move(folders: List[Dict[str, Any]], folder_id: str, target_parent_id: Optional[str]) -> None:
    if not target_parent_id:
        return
    if folder_id == target_parent_id:
        raise HTTPException(status_code=400, detail="Cannot move a folder into itself.")
    if target_parent_id in descendant_folder_ids(folders, folder_id):
        raise HTTPException(status_code=400, detail="Cannot move a folder into one of its subfolders (circular hierarchy).")


def _build(
    folders: List[Dict[str, Any]],
    questions: List[Dict[str, Any]],
    bookmarked: Set[str],
    root_ids: Optional[List[str]] = None,
) -> List[FolderTreeResponse]:
    by_folder: Dict[Optional[str], List[QuestionListItem]] = defaultdict(list)
    for q in sorted(questions, key=_sort_key):
        by_folder[q.get("folder_id")].append(to_list_item(q, bookmarked, None))

    folder_ids = {f["id"] for f in folders}
    children: Dict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)
    for f in sorted(folders, key=_sort_key):
        parent = f.get("parent_id") if f.get("parent_id") in folder_ids else None
        children[parent].append(f)

    def node(f: Dict[str, Any], seen: Set[str]) -> FolderTreeResponse:
        seen = seen | {f["id"]}
        subs = [node(c, seen) for c in children.get(f["id"], []) if c["id"] not in seen]
        qs = by_folder.get(f["id"], [])
        total = len(qs) + sum(s.question_count for s in subs)
        solved = sum(1 for q in qs if q.status == "Solved") + sum(s.solved_count for s in subs)
        return FolderTreeResponse(
            id=f["id"],
            user_id=f.get("user_id") or "",
            parent_id=f.get("parent_id"),
            name=f.get("name") or "Untitled",
            description=f.get("description") or "",
            tags=parse_tags(f.get("tags")),
            position=int(f.get("position") or 0),
            created_at=ts(f, "created_at"),
            updated_at=ts(f, "updated_at"),
            question_count=total,
            solved_count=solved,
            progress_percentage=round(solved / total * 100, 1) if total else 0.0,
            questions=qs,
            subfolders=subs,
        )

    if root_ids is None:
        roots = children.get(None, [])
    else:
        roots = [f for f in folders if f["id"] in root_ids]
    return [node(f, set()) for f in roots]


def build_tree_for_user(db: Database, user_id: str) -> List[FolderTreeResponse]:
    folders = list(db.folders.find({"user_id": user_id}, {"_id": 0}))
    questions = list(db.questions.find({"user_id": user_id}, {"_id": 0, "problem_statement": 0, "notes": 0}))
    return _build(folders, questions, bookmarked_ids(db, user_id))


def build_tree_for_folder(db: Database, user_id: str, folder_id: str) -> Optional[FolderTreeResponse]:
    folders = list(db.folders.find({"user_id": user_id}, {"_id": 0}))
    if not any(f["id"] == folder_id for f in folders):
        return None
    ids = descendant_folder_ids(folders, folder_id) | {folder_id}
    scoped = [f for f in folders if f["id"] in ids]
    questions = list(db.questions.find({"user_id": user_id, "folder_id": {"$in": list(ids)}}, {"_id": 0, "problem_statement": 0, "notes": 0}))
    tree = _build(scoped, questions, set(), root_ids=[folder_id])
    return tree[0] if tree else None


def folder_summary(f: Dict[str, Any], question_count: int = 0, solved: int = 0) -> FolderTreeResponse:
    return FolderTreeResponse(
        id=f["id"],
        user_id=f.get("user_id") or "",
        parent_id=f.get("parent_id"),
        name=f.get("name") or "Untitled",
        description=f.get("description") or "",
        tags=parse_tags(f.get("tags")),
        position=int(f.get("position") or 0),
        created_at=ts(f, "created_at"),
        updated_at=ts(f, "updated_at"),
        question_count=question_count,
        solved_count=solved,
        progress_percentage=round(solved / question_count * 100, 1) if question_count else 0.0,
        questions=[],
        subfolders=[],
    )
