import json
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.folder import Folder
from app.models.question import Question
from app.models.bookmark import Bookmark
from app.schemas.folder import FolderTreeResponse
from app.schemas.question import QuestionListItem
from typing import List, Optional, Set, Dict

def get_folder_path_string(db: Session, folder_id: str) -> str:
    path_names = []
    curr_id: Optional[str] = folder_id

    visited = set()
    while curr_id and curr_id not in visited:
        visited.add(curr_id)
        folder = db.query(Folder).filter(Folder.id == curr_id).first()
        if not folder:
            break
        path_names.append(folder.name)
        curr_id = folder.parent_id

    path_names.reverse()
    return " / ".join(path_names) if path_names else ""

def get_all_descendant_folder_ids(db: Session, folder_id: str) -> Set[str]:
    descendants = set()
    queue = [folder_id]

    while queue:
        current_id = queue.pop(0)
        subfolders = db.query(Folder).filter(Folder.parent_id == current_id).all()
        for sf in subfolders:
            if sf.id not in descendants:
                descendants.add(sf.id)
                queue.append(sf.id)

    return descendants

def validate_folder_move(db: Session, folder_id: str, target_parent_id: Optional[str]):
    if target_parent_id is None:
        return  # Moving to root is always valid

    if folder_id == target_parent_id:
        raise HTTPException(status_code=400, detail="Cannot move a folder into itself.")

    descendants = get_all_descendant_folder_ids(db, folder_id)
    if target_parent_id in descendants:
        raise HTTPException(
            status_code=400,
            detail="Cannot move a folder into one of its subfolders (circular hierarchy)."
        )

def build_tree_for_user(db: Session, user_id: str) -> List[FolderTreeResponse]:
    all_folders = db.query(Folder).filter(Folder.user_id == user_id).order_by(Folder.position, Folder.created_at).all()
    all_questions = db.query(Question).filter(Question.user_id == user_id).order_by(Question.position, Question.created_at).all()
    bookmarked_qids = {b.question_id for b in db.query(Bookmark).filter(Bookmark.user_id == user_id).all()}

    # Group questions by folder_id
    folder_questions: Dict[str, List[QuestionListItem]] = {}
    for q in all_questions:
        tags_list = []
        try:
            tags_list = json.loads(q.tags) if q.tags else []
        except Exception:
            tags_list = [q.tags] if q.tags else []

        item = QuestionListItem(
            id=q.id,
            folder_id=q.folder_id,
            title=q.title,
            problem_url=q.problem_url or "",
            difficulty=q.difficulty,
            status=q.status,
            tags=tags_list,
            is_bookmarked=(q.id in bookmarked_qids),
            folder_path="",
            updated_at=q.updated_at
        )
        folder_questions.setdefault(q.folder_id, []).append(item)

    # Build folder lookup
    folder_map: Dict[str, dict] = {}
    for f in all_folders:
        f_tags = []
        try:
            f_tags = json.loads(f.tags) if f.tags else []
        except Exception:
            f_tags = [f.tags] if f.tags else []

        folder_map[f.id] = {
            "id": f.id,
            "user_id": f.user_id,
            "parent_id": f.parent_id,
            "name": f.name,
            "description": f.description or "",
            "tags": f_tags,
            "position": f.position,
            "created_at": f.created_at,
            "updated_at": f.updated_at,
            "questions": folder_questions.get(f.id, []),
            "subfolders": [],
            "direct_q_count": len(folder_questions.get(f.id, [])),
            "direct_solved_count": sum(1 for q in folder_questions.get(f.id, []) if q.status == "Solved"),
            "total_q_count": 0,
            "total_solved_count": 0,
        }

    # Connect subfolders
    root_folder_ids = []
    for f in all_folders:
        if f.parent_id and f.parent_id in folder_map:
            folder_map[f.parent_id]["subfolders"].append(folder_map[f.id])
        else:
            root_folder_ids.append(f.id)

    # Post-order traversal to calculate recursive counts
    def aggregate_counts(node_dict: dict) -> (int, int):
        total_q = node_dict["direct_q_count"]
        total_s = node_dict["direct_solved_count"]

        for child in node_dict["subfolders"]:
            cq, cs = aggregate_counts(child)
            total_q += cq
            total_s += cs

        node_dict["total_q_count"] = total_q
        node_dict["total_solved_count"] = total_s
        node_dict["progress_percentage"] = (
            round((total_s / total_q) * 100, 1) if total_q > 0 else 0.0
        )
        return total_q, total_s

    for r_id in root_folder_ids:
        aggregate_counts(folder_map[r_id])

    # Convert to schema response
    def to_schema(node_dict: dict) -> FolderTreeResponse:
        return FolderTreeResponse(
            id=node_dict["id"],
            user_id=node_dict["user_id"],
            parent_id=node_dict["parent_id"],
            name=node_dict["name"],
            description=node_dict.get("description", ""),
            tags=node_dict.get("tags", []),
            position=node_dict["position"],
            created_at=node_dict["created_at"],
            updated_at=node_dict["updated_at"],
            question_count=node_dict["total_q_count"],
            solved_count=node_dict["total_solved_count"],
            progress_percentage=node_dict["progress_percentage"],
            questions=node_dict["questions"],
            subfolders=[to_schema(sf) for sf in node_dict["subfolders"]]
        )

    return [to_schema(folder_map[r_id]) for r_id in root_folder_ids]
