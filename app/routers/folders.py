import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.folder import Folder
from app.models.user import User
from app.schemas.folder import FolderCreate, FolderUpdate, FolderMove, FolderTreeResponse
from app.routers.auth import get_current_user
from app.services.folder_service import (
    build_tree_for_user,
    validate_folder_move,
    get_all_descendant_folder_ids
)

router = APIRouter(prefix="/folders", tags=["folders"])

@router.get("/tree", response_model=List[FolderTreeResponse])
def get_folder_tree(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return build_tree_for_user(db, current_user.id)

@router.post("/", response_model=FolderTreeResponse, status_code=status.HTTP_201_CREATED)
def create_folder(
    folder_in: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if folder_in.parent_id:
        parent = db.query(Folder).filter(
            Folder.id == folder_in.parent_id,
            Folder.user_id == current_user.id
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")

    tags_json = json.dumps(folder_in.tags) if folder_in.tags else "[]"

    folder = Folder(
        user_id=current_user.id,
        parent_id=folder_in.parent_id,
        name=folder_in.name.strip(),
        description=folder_in.description or "",
        tags=tags_json,
        position=folder_in.position or 0
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)

    parsed_tags = []
    try:
        parsed_tags = json.loads(folder.tags) if folder.tags else []
    except Exception:
        parsed_tags = [folder.tags] if folder.tags else []

    return FolderTreeResponse(
        id=folder.id,
        user_id=folder.user_id,
        parent_id=folder.parent_id,
        name=folder.name,
        description=folder.description or "",
        tags=parsed_tags,
        position=folder.position,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
        question_count=0,
        solved_count=0,
        progress_percentage=0.0,
        subfolders=[],
        questions=[]
    )

@router.put("/{folder_id}", response_model=FolderTreeResponse)
def update_folder(
    folder_id: str,
    folder_in: FolderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.user_id == current_user.id
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if folder_in.name is not None:
        folder.name = folder_in.name.strip()
    if folder_in.description is not None:
        folder.description = folder_in.description
    if folder_in.tags is not None:
        folder.tags = json.dumps(folder_in.tags)
    if folder_in.parent_id is not None:
        target_id = folder_in.parent_id if folder_in.parent_id != "" else None
        if target_id is not None:
            if target_id == folder.id:
                raise HTTPException(status_code=400, detail="Cannot move a folder into itself.")
            parent = db.query(Folder).filter(
                Folder.id == target_id,
                Folder.user_id == current_user.id
            ).first()
            if not parent:
                raise HTTPException(status_code=404, detail="Target parent folder not found")
        validate_folder_move(db, folder.id, target_id)
        folder.parent_id = target_id
    if folder_in.position is not None:
        folder.position = folder_in.position

    db.commit()
    db.refresh(folder)

    parsed_tags = []
    try:
        parsed_tags = json.loads(folder.tags) if folder.tags else []
    except Exception:
        parsed_tags = [folder.tags] if folder.tags else []

    # Return refreshed tree item
    return FolderTreeResponse(
        id=folder.id,
        user_id=folder.user_id,
        parent_id=folder.parent_id,
        name=folder.name,
        description=folder.description or "",
        tags=parsed_tags,
        position=folder.position,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
        question_count=len(folder.questions),
        solved_count=sum(1 for q in folder.questions if q.status == "Solved"),
        progress_percentage=0.0,
        subfolders=[],
        questions=[]
    )

@router.post("/{folder_id}/move")
def move_folder(
    folder_id: str,
    move_in: FolderMove,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.user_id == current_user.id
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Validate target parent and prevent circular hierarchy
    if move_in.target_parent_id:
        target_parent = db.query(Folder).filter(
            Folder.id == move_in.target_parent_id,
            Folder.user_id == current_user.id
        ).first()
        if not target_parent:
            raise HTTPException(status_code=404, detail="Target parent folder not found")

    validate_folder_move(db, folder_id, move_in.target_parent_id)

    folder.parent_id = move_in.target_parent_id
    if move_in.new_position is not None:
        folder.position = move_in.new_position

    db.commit()
    return {"message": "Folder moved successfully", "folder_id": folder.id, "parent_id": folder.parent_id}

@router.delete("/{folder_id}")
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.user_id == current_user.id
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    descendant_ids = get_all_descendant_folder_ids(db, folder_id)
    all_target_ids = descendant_ids | {folder_id}

    # Delete folder (SQLAlchemy cascading will delete descendant folders & questions)
    db.delete(folder)
    db.commit()

    return {"message": "Folder and contents deleted successfully", "deleted_folder_ids": list(all_target_ids)}
