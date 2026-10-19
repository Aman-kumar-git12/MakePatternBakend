from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.bookmark import Bookmark
from app.models.question import Question
from app.models.user import User
from app.schemas.bookmark import BookmarkToggleResponse, BookmarkResponse
from app.routers.auth import get_current_user
from app.routers.questions import format_question_response
from app.mongodb import save_bookmark_mongo, delete_bookmark_mongo

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])

@router.get("/", response_model=List[BookmarkResponse])
def get_all_bookmarks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    bookmarks = db.query(Bookmark).filter(Bookmark.user_id == current_user.id).order_by(Bookmark.created_at.desc()).all()
    results = []
    for b in bookmarks:
        q_resp = format_question_response(db, b.question, current_user.id)
        results.append(
            BookmarkResponse(
                id=b.id,
                user_id=b.user_id,
                question_id=b.question_id,
                created_at=b.created_at,
                question=q_resp
            )
        )
    return results

@router.post("/{question_id}/toggle", response_model=BookmarkToggleResponse)
def toggle_bookmark(
    question_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = db.query(Question).filter(
        Question.id == question_id,
        Question.user_id == current_user.id
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    existing = db.query(Bookmark).filter(
        Bookmark.user_id == current_user.id,
        Bookmark.question_id == question_id
    ).first()

    if existing:
        b_id = existing.id
        db.delete(existing)
        db.commit()
        delete_bookmark_mongo(bookmark_id=b_id, user_id=current_user.id, question_id=question_id)
        return BookmarkToggleResponse(
            question_id=question_id,
            is_bookmarked=False,
            message="Question removed from bookmarks"
        )
    else:
        new_b = Bookmark(user_id=current_user.id, question_id=question_id)
        db.add(new_b)
        db.commit()
        save_bookmark_mongo(new_b)
        return BookmarkToggleResponse(
            question_id=question_id,
            is_bookmarked=True,
            message="Question added to bookmarks"
        )
