from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.question import Question
from app.schemas.folder import PublicSharedPatternResponse
from app.schemas.question import QuestionResponse
from app.routers.questions import format_question_response
from app.services.folder_service import (
    build_tree_for_folder,
    build_tree_for_user,
    get_all_descendant_folder_ids
)
from app.mongodb import (
    find_active_share_by_id_mongo,
    get_share_snapshot_mongo,
    save_share_snapshot_mongo
)

router = APIRouter(prefix="/shared", tags=["shared"])

@router.get("/{share_id}", response_model=PublicSharedPatternResponse)
def get_shared_pattern(
    share_id: str,
    db: Session = Depends(get_db)
):
    """
    Public Read-Only API to retrieve an immutable point-in-time snapshot of a shared pattern.
    Guarantees that subsequent modifications by the pattern owner do not alter this snapshot.
    """
    # 1. First check the frozen point-in-time snapshot in MongoDB
    snapshot = get_share_snapshot_mongo(share_id)
    if snapshot and snapshot.get("is_active"):
        patterns = snapshot.get("patterns", [])
        return PublicSharedPatternResponse(
            share_id=share_id,
            owner_name=snapshot.get("owner_name") or "Curator",
            share_type=snapshot.get("share_type", "single"),
            pattern=patterns[0] if patterns else None,
            patterns=patterns
        )

    # 2. Check if the share configuration is active in MongoDB
    share_info = find_active_share_by_id_mongo(share_id)
    if not share_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared pattern not found, revoked, or sharing has been disabled by the owner."
        )

    # 3. Create, freeze, and persist the snapshot immediately for future calls
    user_id = share_info["user_id"]
    folder_id = share_info["share"]["folder_id"]
    folder_name = share_info["share"].get("folder_name", "Pattern")
    owner_name = share_info.get("owner_name", "Curator")

    from app.services.share_service import capture_share_snapshot_data
    snap_data = capture_share_snapshot_data(db, user_id, folder_id, owner_name)
    if not snap_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The pattern data associated with this share is no longer available."
        )

    save_share_snapshot_mongo(
        share_id=share_id,
        user_id=user_id,
        owner_name=owner_name,
        folder_id=folder_id,
        folder_name=folder_name,
        share_type=snap_data["share_type"],
        patterns=snap_data["patterns"],
        questions=snap_data["questions"],
        is_active=True
    )

    patterns = snap_data["patterns"]
    return PublicSharedPatternResponse(
        share_id=share_id,
        owner_name=owner_name,
        share_type=snap_data["share_type"],
        pattern=patterns[0] if patterns else None,
        patterns=patterns
    )

@router.get("/{share_id}/questions/{question_id}", response_model=QuestionResponse)
def get_shared_question(
    share_id: str,
    question_id: str,
    db: Session = Depends(get_db)
):
    """
    Public Read-Only API to view a specific problem and its solutions from the frozen snapshot.
    Guarantees the code, notes, and test cases remain frozen as of the snapshot time.
    """
    # 1. First look up the question in the frozen snapshot
    snapshot = get_share_snapshot_mongo(share_id)
    if snapshot and snapshot.get("is_active"):
        questions_map = snapshot.get("questions", {})
        if question_id in questions_map:
            return QuestionResponse.model_validate(questions_map[question_id])
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found in this shared pattern snapshot."
        )

    # 2. If snapshot not generated yet, verify share and freeze it
    share_info = find_active_share_by_id_mongo(share_id)
    if not share_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared pattern not found, revoked, or sharing has been disabled."
        )

    user_id = share_info["user_id"]
    folder_id = share_info["share"]["folder_id"]
    folder_name = share_info["share"].get("folder_name", "Pattern")
    owner_name = share_info.get("owner_name", "Curator")

    from app.services.share_service import capture_share_snapshot_data
    snap_data = capture_share_snapshot_data(db, user_id, folder_id, owner_name)
    if snap_data:
        save_share_snapshot_mongo(
            share_id=share_id,
            user_id=user_id,
            owner_name=owner_name,
            folder_id=folder_id,
            folder_name=folder_name,
            share_type=snap_data["share_type"],
            patterns=snap_data["patterns"],
            questions=snap_data["questions"],
            is_active=True
        )
        if question_id in snap_data["questions"]:
            return QuestionResponse.model_validate(snap_data["questions"][question_id])

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Question not found in this shared pattern."
    )

