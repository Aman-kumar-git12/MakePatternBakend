from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.db import get_db
from app.routers.auth import CurrentUser, get_current_user
from app.schemas.folder import ForkResponse, PublicSharedPatternResponse
from app.schemas.question import QuestionResponse
from app.services.ratelimit import check_rate_limit
from app.services.share_service import fork_snapshot, resolve_public_snapshot

router = APIRouter(prefix="/shared", tags=["shared"])


@router.get("/{share_id}", response_model=PublicSharedPatternResponse)
def get_shared_pattern(share_id: str, db: Database = Depends(get_db)):
    """Public, read-only, point-in-time snapshot of a shared pattern."""
    snap = resolve_public_snapshot(db, share_id)
    patterns = snap.get("patterns") or []
    return PublicSharedPatternResponse(
        share_id=share_id,
        owner_name=snap.get("owner_name") or "Curator",
        share_type=snap.get("share_type", "single"),
        pattern=patterns[0] if patterns else None,
        patterns=patterns,
    )


@router.get("/{share_id}/questions/{question_id}", response_model=QuestionResponse)
def get_shared_question(share_id: str, question_id: str, db: Database = Depends(get_db)):
    snap = resolve_public_snapshot(db, share_id)
    q = (snap.get("questions") or {}).get(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found in this shared pattern snapshot.")
    q = dict(q)
    q["user_id"] = ""
    return QuestionResponse.model_validate(q)


@router.post("/{share_id}/fork", response_model=ForkResponse)
def fork_shared_pattern(share_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    """Copy a shared pattern (folders, questions, notes, solutions, test cases) into my workspace."""
    check_rate_limit(f"fork:{current_user.id}", limit=20, window_seconds=3600)
    snap = resolve_public_snapshot(db, share_id)
    return fork_snapshot(db, current_user.id, snap)
