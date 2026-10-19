import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.folder import Folder
from app.models.question import Question
from app.services.folder_service import (
    build_tree_for_folder,
    build_tree_for_user,
    get_all_descendant_folder_ids
)
from app.routers.questions import format_question_response
from app.mongodb import save_share_snapshot_mongo

logger = logging.getLogger("dsa_tracker.share_service")

def sanitize_tree_dict(node_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively resets user-specific solved status and bookmarks in snapshot tree."""
    if not node_dict:
        return node_dict
    node_dict["solved_count"] = 0
    node_dict["progress_percentage"] = 0.0
    if "questions" in node_dict and node_dict["questions"]:
        for q in node_dict["questions"]:
            q["status"] = "Not Started"
            q["is_bookmarked"] = False
    if "subfolders" in node_dict and node_dict["subfolders"]:
        for sf in node_dict["subfolders"]:
            sanitize_tree_dict(sf)
    return node_dict

def capture_share_snapshot_data(
    db: Session,
    user_id: str,
    folder_id: str,
    owner_name: str
) -> Optional[Dict[str, Any]]:
    """
    Captures an immutable, point-in-time snapshot of the folder hierarchy,
    all questions, solutions, test cases, and notes at the exact moment of sharing.
    """
    try:
        if folder_id == "all":
            trees = build_tree_for_user(db, user_id)
            sanitized_trees = [sanitize_tree_dict(t.model_dump(mode="json")) for t in trees]
            share_type = "all"
            questions = db.query(Question).filter(Question.user_id == user_id).all()
        else:
            tree = build_tree_for_folder(db, folder_id)
            if not tree:
                return None
            sanitized_trees = [sanitize_tree_dict(tree.model_dump(mode="json"))]
            share_type = "single"
            descendant_ids = get_all_descendant_folder_ids(db, folder_id)
            permitted_ids = {folder_id} | descendant_ids
            questions = db.query(Question).filter(Question.folder_id.in_(permitted_ids)).all()

        questions_map: Dict[str, Any] = {}
        for q in questions:
            q_resp = format_question_response(db, q, user_id=user_id)
            q_dict = q_resp.model_dump(mode="json")
            q_dict["status"] = "Not Started"
            q_dict["is_bookmarked"] = False
            questions_map[q.id] = q_dict

        return {
            "share_type": share_type,
            "patterns": sanitized_trees,
            "questions": questions_map
        }
    except Exception as e:
        logger.error(f"Error capturing share snapshot for user {user_id}, folder {folder_id}: {e}", exc_info=True)
        return None

def capture_and_save_share_snapshot(
    db: Session,
    current_user: User,
    folder_id: str,
    folder_name: str,
    share_id: str
) -> bool:
    """
    Takes the snapshot and saves it permanently to MongoDB Atlas share_snapshots collection.
    """
    owner_name = current_user.full_name or "Curator"
    snap_data = capture_share_snapshot_data(db, current_user.id, folder_id, owner_name)
    if not snap_data:
        logger.warning(f"Could not generate snapshot for share_id {share_id}")
        return False

    return save_share_snapshot_mongo(
        share_id=share_id,
        user_id=current_user.id,
        owner_name=owner_name,
        folder_id=folder_id,
        folder_name=folder_name,
        share_type=snap_data["share_type"],
        patterns=snap_data["patterns"],
        questions=snap_data["questions"],
        is_active=True
    )
