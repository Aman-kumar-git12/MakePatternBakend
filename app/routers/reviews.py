"""Spaced-repetition review queue."""
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from datetime import timezone

from app.db import get_db, now_iso, now_utc, parse_dt, to_iso
from app.routers.auth import CurrentUser, get_current_user
from app.schemas.question import QuestionListItem
from app.schemas.review import DueReviewsResponse, ReviewBatchRequest, ReviewBatchResponse, ReviewBatchResult, ReviewRequest
from app.services.repo import FolderPaths, bookmarked_ids, get_owned_question, to_list_item
from app.services.tracking import (
    end_of_local_day_iso,
    get_user_tz,
    local_today,
    record_activity,
    review_updates,
    start_of_local_day_iso,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])

PROJECTION = {"_id": 0, "problem_statement": 0, "notes": 0}


def _apply_review(db: Database, uid: str, q: dict, rating: str, at, now) -> dict:
    """Update the question's schedule; log a "solved" activity when the review marks it Solved."""
    was_solved = (q.get("status") or "Not Started") == "Solved"
    updates = review_updates(q, rating, now=at)
    updates["updated_at"] = to_iso(now)
    db.questions.update_one({"id": q["id"], "user_id": uid}, {"$set": updates})
    if not was_solved and updates.get("status") == "Solved":
        record_activity(db, uid, "solved", q["id"], at=at)
    return updates


@router.get("/due", response_model=DueReviewsResponse)
def due_reviews(db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user), tz: ZoneInfo = Depends(get_user_tz)):
    uid = current_user.id
    today = local_today(tz)
    cutoff = end_of_local_day_iso(tz)
    week = end_of_local_day_iso(tz, today + timedelta(days=7))
    due_docs = list(db.questions.find({"user_id": uid, "next_review_at": {"$ne": None, "$lte": cutoff}}, PROJECTION).sort("next_review_at", 1).limit(200))
    upcoming_docs = list(db.questions.find({"user_id": uid, "next_review_at": {"$gt": cutoff, "$lte": week}}, PROJECTION).sort("next_review_at", 1).limit(100))
    reviewed_today = db.activity.count_documents({"user_id": uid, "type": "review", "at": {"$gte": start_of_local_day_iso(tz)}})
    paths = FolderPaths.for_user(db, uid)
    bm = bookmarked_ids(db, uid)
    return DueReviewsResponse(
        due=[to_list_item(q, bm, paths) for q in due_docs],
        upcoming=[to_list_item(q, bm, paths) for q in upcoming_docs],
        due_count=db.questions.count_documents({"user_id": uid, "next_review_at": {"$ne": None, "$lte": cutoff}}),
        reviewed_today=reviewed_today,
    )


@router.post("/batch", response_model=ReviewBatchResponse)
def sync_offline_reviews(body: ReviewBatchRequest, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    """Apply reviews done offline, in the order they happened. Idempotent per client_id."""
    uid = current_user.id
    now = now_utc()
    results = []
    for r in sorted(body.reviews, key=lambda r: r.reviewed_at):
        if db.activity.find_one({"user_id": uid, "client_id": r.client_id}, {"_id": 1}):
            results.append(ReviewBatchResult(client_id=r.client_id, status="duplicate"))
            continue
        q = get_owned_question(db, uid, r.question_id)
        if not q:
            results.append(ReviewBatchResult(client_id=r.client_id, status="not_found"))
            continue
        at = r.reviewed_at if r.reviewed_at.tzinfo else r.reviewed_at.replace(tzinfo=timezone.utc)
        at = min(max(at, now - timedelta(days=30)), now)
        # Claim the client_id first: the unique index makes a concurrent second sync (another tab)
        # a no-op instead of applying the same review twice.
        try:
            record_activity(db, uid, "review", r.question_id, at=at, client_id=r.client_id)
        except DuplicateKeyError:
            results.append(ReviewBatchResult(client_id=r.client_id, status="duplicate"))
            continue
        last = parse_dt(q.get("last_reviewed_at"))
        if last and last > at:
            # A newer review already happened on another device; don't roll the schedule back.
            results.append(ReviewBatchResult(client_id=r.client_id, status="stale"))
            continue
        _apply_review(db, uid, q, r.rating, at, now)
        results.append(ReviewBatchResult(client_id=r.client_id, status="applied"))
    applied = sum(1 for x in results if x.status == "applied")
    return ReviewBatchResponse(applied=applied, skipped=len(results) - applied, results=results)


@router.post("/{question_id}", response_model=QuestionListItem)
def review_question(question_id: str, body: ReviewRequest, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    q = get_owned_question(db, current_user.id, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    record_activity(db, current_user.id, "review", question_id)
    updates = _apply_review(db, current_user.id, q, body.rating, now_utc(), now_utc())
    q.update(updates)
    return to_list_item(q, bookmarked_ids(db, current_user.id), FolderPaths.for_user(db, current_user.id))
