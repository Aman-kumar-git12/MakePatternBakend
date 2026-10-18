import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.database import get_db
from app.models.question import Question
from app.models.folder import Folder
from app.models.bookmark import Bookmark
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.folder_service import get_folder_path_string

router = APIRouter(prefix="/search", tags=["search"])

@router.get("/")
def global_search(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    search_term = f"%{q}%"

    # Search questions
    matching_questions = db.query(Question).filter(
        Question.user_id == current_user.id,
        (Question.title.ilike(search_term)) |
        (Question.problem_statement.ilike(search_term)) |
        (Question.notes.ilike(search_term)) |
        (Question.tags.ilike(search_term))
    ).limit(20).all()

    bookmarked_ids = {b.question_id for b in db.query(Bookmark).filter(Bookmark.user_id == current_user.id).all()}

    questions_res = []
    for mq in matching_questions:
        tags_list = []
        try:
            tags_list = json.loads(mq.tags) if mq.tags else []
        except Exception:
            tags_list = [mq.tags] if mq.tags else []

        questions_res.append({
            "id": mq.id,
            "title": mq.title,
            "folder_id": mq.folder_id,
            "folder_path": get_folder_path_string(db, mq.folder_id),
            "difficulty": mq.difficulty,
            "status": mq.status,
            "tags": tags_list,
            "is_bookmarked": (mq.id in bookmarked_ids),
            "updated_at": mq.updated_at.isoformat()
        })

    # Search folders
    matching_folders = db.query(Folder).filter(
        Folder.user_id == current_user.id,
        Folder.name.ilike(search_term)
    ).limit(10).all()

    folders_res = [
        {
            "id": mf.id,
            "name": mf.name,
            "path": get_folder_path_string(db, mf.id),
            "parent_id": mf.parent_id
        }
        for mf in matching_folders
    ]

    return {
        "query": q,
        "questions": questions_res,
        "folders": folders_res,
        "total_results": len(questions_res) + len(folders_res)
    }
