import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import func
from app.database import get_db
from app.models.folder import Folder
from app.models.user import User
from app.schemas.folder import (
    FolderCreate, FolderUpdate, FolderMove, FolderTreeResponse, ReorderItem,
    ShareResponse, ShareStatusUpdate
)
from app.mongodb import (
    get_share_for_folder_mongo, create_or_get_share_mongo,
    update_share_status_mongo, revoke_share_mongo,
    save_folder_mongo, bulk_save_folders_mongo, delete_folder_mongo,
    update_share_snapshot_status_mongo, revoke_share_snapshot_mongo
)
from app.services.share_service import capture_and_save_share_snapshot
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
    tree = build_tree_for_user(db, current_user.id)
    if not tree:
        from app.mongodb import restore_user_data_from_mongo_to_sqlite
        restore_user_data_from_mongo_to_sqlite(db, current_user.id)
        tree = build_tree_for_user(db, current_user.id)
    return tree

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

    if folder_in.position is not None and folder_in.position > 0:
        folder_pos = folder_in.position
    else:
        max_pos = db.query(func.max(Folder.position)).filter(
            Folder.user_id == current_user.id,
            Folder.parent_id == folder_in.parent_id
        ).scalar()
        folder_pos = (max_pos + 1) if max_pos is not None else 0

    folder = Folder(
        user_id=current_user.id,
        parent_id=folder_in.parent_id,
        name=folder_in.name.strip(),
        description=folder_in.description or "",
        tags=tags_json,
        position=folder_pos
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    save_folder_mongo(folder)

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

@router.post("/reorder")
def reorder_folders(
    items: List[ReorderItem],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    for item in items:
        db.query(Folder).filter(
            Folder.id == item.id,
            Folder.user_id == current_user.id
        ).update({"position": item.position})
    db.commit()
    reordered_folders = db.query(Folder).filter(Folder.id.in_([it.id for it in items])).all()
    bulk_save_folders_mongo(reordered_folders)
    return {"message": "Folders reordered successfully"}

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
    save_folder_mongo(folder)

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
    db.refresh(folder)
    save_folder_mongo(folder)
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
    delete_folder_mongo(folder_id, list(descendant_ids))

    return {"message": "Folder and contents deleted successfully", "deleted_folder_ids": list(all_target_ids)}

# =========================================================================
# Pattern Sharing Endpoints (Ownership Checked & Persisted in MongoDB)
# =========================================================================

def _resolve_folder_name(folder_id: str, db: Session, current_user: User) -> str:
    if folder_id == "all":
        return "All Patterns"
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == current_user.id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found or unauthorized")
    return folder.name

@router.get("/{folder_id}/share", response_model=ShareResponse)
def get_folder_share_settings(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder_name = _resolve_folder_name(folder_id, db, current_user)
    share = get_share_for_folder_mongo(current_user.id, folder_id)
    if not share:
        raise HTTPException(status_code=404, detail="No share configuration found for this folder")

    return ShareResponse(
        share_id=share["share_id"],
        folder_id=share["folder_id"],
        folder_name=share.get("folder_name") or folder_name,
        is_active=share.get("is_active", False),
        share_url=f"/shared/{share['share_id']}",
        created_at=share.get("created_at", ""),
        updated_at=share.get("updated_at", "")
    )

@router.post("/{folder_id}/share", response_model=ShareResponse)
def enable_or_create_folder_share(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder_name = _resolve_folder_name(folder_id, db, current_user)
    share = create_or_get_share_mongo(
        user_id=current_user.id,
        folder_id=folder_id,
        folder_name=folder_name,
        email=current_user.email,
        full_name=current_user.full_name or "",
        hashed_password=current_user.hashed_password or ""
    )

    # Capture and freeze an immutable snapshot of this pattern hierarchy, questions & solutions
    capture_and_save_share_snapshot(db, current_user, folder_id, folder_name, share["share_id"])

    return ShareResponse(
        share_id=share["share_id"],
        folder_id=share["folder_id"],
        folder_name=share.get("folder_name") or folder_name,
        is_active=share.get("is_active", True),
        share_url=f"/shared/{share['share_id']}",
        created_at=share.get("created_at", ""),
        updated_at=share.get("updated_at", "")
    )

@router.patch("/{folder_id}/share", response_model=ShareResponse)
def toggle_folder_share_status(
    folder_id: str,
    update_data: ShareStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder_name = _resolve_folder_name(folder_id, db, current_user)
    share = update_share_status_mongo(current_user.id, folder_id, update_data.is_active)
    if not share:
        raise HTTPException(status_code=404, detail="Share settings not found")

    update_share_snapshot_status_mongo(current_user.id, folder_id, update_data.is_active)

    return ShareResponse(
        share_id=share["share_id"],
        folder_id=share["folder_id"],
        folder_name=share.get("folder_name") or folder_name,
        is_active=share.get("is_active", False),
        share_url=f"/shared/{share['share_id']}",
        created_at=share.get("created_at", ""),
        updated_at=share.get("updated_at", "")
    )

@router.post("/{folder_id}/share/revoke", response_model=ShareResponse)
def revoke_and_regenerate_folder_share(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder_name = _resolve_folder_name(folder_id, db, current_user)
    share = revoke_share_mongo(current_user.id, folder_id, regenerate_new=True, folder_name=folder_name)
    if not share:
        raise HTTPException(status_code=404, detail="Failed to revoke share link")

    # Capture a fresh snapshot for the new share link
    capture_and_save_share_snapshot(db, current_user, folder_id, folder_name, share["share_id"])

    return ShareResponse(
        share_id=share["share_id"],
        folder_id=share["folder_id"],
        folder_name=share.get("folder_name") or folder_name,
        is_active=share.get("is_active", True),
        share_url=f"/shared/{share['share_id']}",
        created_at=share.get("created_at", ""),
        updated_at=share.get("updated_at", "")
    )

@router.delete("/{folder_id}/share")
def disable_folder_share(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _resolve_folder_name(folder_id, db, current_user)
    revoke_share_mongo(current_user.id, folder_id, regenerate_new=False)
    revoke_share_snapshot_mongo(current_user.id, folder_id)
    return {"message": "Sharing disabled successfully for this pattern"}


