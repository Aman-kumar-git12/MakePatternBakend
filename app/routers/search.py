import re
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from app.db import get_db, parse_tags, ts
from app.routers.auth import CurrentUser, get_current_user
from app.services.repo import FolderPaths, bookmarked_ids

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/")
def global_search(
    q: str = Query(..., min_length=1, max_length=200),
    db: Database = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    rx = {"$regex": re.escape(q.strip()), "$options": "i"}
    uid = current_user.id
    matches = list(db.questions.find(
        {"user_id": uid, "$or": [{"title": rx}, {"problem_statement": rx}, {"notes": rx}, {"tags": rx}, {"leetcode_id": q.strip()}]},
        {"_id": 0, "problem_statement": 0, "notes": 0},
    ).limit(20))
    paths = FolderPaths.for_user(db, uid)
    bm = bookmarked_ids(db, uid)
    questions_res = [
        {
            "id": m["id"],
            "title": m.get("title") or "",
            "folder_id": m.get("folder_id"),
            "folder_path": paths.path(m.get("folder_id")),
            "difficulty": m.get("difficulty") or "Medium",
            "status": m.get("status") or "Not Started",
            "tags": parse_tags(m.get("tags")),
            "is_bookmarked": m["id"] in bm,
            "updated_at": ts(m, "updated_at").isoformat(),
        }
        for m in matches
    ]
    folders_res = [
        {"id": f["id"], "name": f.get("name"), "path": paths.path(f["id"]), "parent_id": f.get("parent_id")}
        for f in db.folders.find({"user_id": uid, "name": rx}, {"_id": 0}).limit(10)
    ]
    return {"query": q, "questions": questions_res, "folders": folders_res, "total_results": len(questions_res) + len(folders_res)}
