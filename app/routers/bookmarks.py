from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.db import get_db, new_id, now_iso, ts
from app.routers.auth import CurrentUser, get_current_user
from app.schemas.bookmark import BookmarkResponse, BookmarkToggleResponse
from app.services.repo import FolderPaths, get_owned_question, to_responses

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


@router.get("/", response_model=List[BookmarkResponse])
def get_all_bookmarks(db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    bms = list(db.bookmarks.find({"user_id": current_user.id}, {"_id": 0}).sort("created_at", -1))
    qids = [b["question_id"] for b in bms]
    questions = {q["id"]: q for q in db.questions.find({"user_id": current_user.id, "id": {"$in": qids}}, {"_id": 0})}
    ordered = [questions[qid] for qid in qids if qid in questions]
    responses = {r.id: r for r in to_responses(db, ordered, set(qids), FolderPaths.for_user(db, current_user.id))}
    return [
        BookmarkResponse(id=b.get("id") or b["question_id"], user_id=current_user.id, question_id=b["question_id"],
                         created_at=ts(b, "created_at"), question=responses[b["question_id"]])
        for b in bms if b["question_id"] in responses
    ]


@router.post("/{question_id}/toggle", response_model=BookmarkToggleResponse)
def toggle_bookmark(question_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    if not get_owned_question(db, current_user.id, question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    removed = db.bookmarks.delete_one({"user_id": current_user.id, "question_id": question_id})
    if removed.deleted_count:
        return BookmarkToggleResponse(question_id=question_id, is_bookmarked=False, message="Question removed from bookmarks")
    try:
        db.bookmarks.insert_one({"id": new_id(), "user_id": current_user.id, "question_id": question_id, "created_at": now_iso()})
    except DuplicateKeyError:
        pass  # concurrent double-click; it's bookmarked either way
    return BookmarkToggleResponse(question_id=question_id, is_bookmarked=True, message="Question added to bookmarks")
