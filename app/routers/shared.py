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
from app.mongodb import find_active_share_by_id_mongo

from app.schemas.folder import FolderTreeResponse, PublicSharedPatternResponse

def sanitize_shared_folder_tree(node: FolderTreeResponse) -> FolderTreeResponse:
    if not node:
        return node
    node.solved_count = 0
    node.progress_percentage = 0.0
    if node.questions:
        for q in node.questions:
            q.status = "Not Started"
            q.is_bookmarked = False
    if node.subfolders:
        for sf in node.subfolders:
            sanitize_shared_folder_tree(sf)
    return node

router = APIRouter(prefix="/shared", tags=["shared"])

@router.get("/{share_id}", response_model=PublicSharedPatternResponse)
def get_shared_pattern(
    share_id: str,
    db: Session = Depends(get_db)
):
    """
    Public Read-Only API to retrieve a shared pattern or the whole list of topics.
    Enforces that the shareId is valid and active in MongoDB.
    No authentication required, but strictly read-only and scopes
    access exclusively to the shared pattern hierarchy.
    """
    share_info = find_active_share_by_id_mongo(share_id)
    if not share_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared pattern not found, revoked, or sharing has been disabled by the owner."
        )

    folder_id = share_info["share"]["folder_id"]

    # Case 1: Whole list of topics / all patterns shared
    if folder_id == "all":
        pattern_trees = build_tree_for_user(db, share_info["user_id"])
        sanitized_trees = [sanitize_shared_folder_tree(pt) for pt in pattern_trees]
        return PublicSharedPatternResponse(
            share_id=share_id,
            owner_name=share_info.get("owner_name") or "Curator",
            share_type="all",
            pattern=None,
            patterns=sanitized_trees
        )

    # Case 2: Individual pattern / topic shared
    pattern_tree = build_tree_for_folder(db, folder_id)
    if not pattern_tree:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The pattern associated with this share link is no longer available."
        )

    sanitized_tree = sanitize_shared_folder_tree(pattern_tree)
    return PublicSharedPatternResponse(
        share_id=share_id,
        owner_name=share_info.get("owner_name") or "Curator",
        share_type="single",
        pattern=sanitized_tree,
        patterns=[sanitized_tree]
    )

@router.get("/{share_id}/questions/{question_id}", response_model=QuestionResponse)
def get_shared_question(
    share_id: str,
    question_id: str,
    db: Session = Depends(get_db)
):
    """
    Public Read-Only API to view a specific problem and its solutions within a shared pattern.
    Strictly verifies that the requested question belongs to the shared pattern's folder hierarchy.
    """
    share_info = find_active_share_by_id_mongo(share_id)
    if not share_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared pattern not found, revoked, or sharing has been disabled."
        )

    folder_id = share_info["share"]["folder_id"]

    if folder_id == "all":
        q = db.query(Question).filter(Question.id == question_id, Question.user_id == share_info["user_id"]).first()
        if not q:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found in this shared pattern collection."
            )
        resp = format_question_response(db, q, user_id=share_info["user_id"])
        resp.status = "Not Started"
        resp.is_bookmarked = False
        return resp

    descendant_ids = get_all_descendant_folder_ids(db, folder_id)
    permitted_folder_ids = {folder_id} | descendant_ids

    q = db.query(Question).filter(Question.id == question_id).first()
    if not q or q.folder_id not in permitted_folder_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found in this shared pattern."
        )

    resp = format_question_response(db, q, user_id=share_info["user_id"])
    resp.status = "Not Started"
    resp.is_bookmarked = False
    return resp

