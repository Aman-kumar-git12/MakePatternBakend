from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.db import bulk_update, get_db, now_iso
from app.routers.auth import CurrentUser, get_current_user
from app.schemas.folder import (
    FolderCreate,
    FolderMove,
    FolderTreeResponse,
    FolderUpdate,
    ReorderItem,
    ShareResponse,
    ShareStatusUpdate,
)
from app.services import share_service
from app.services.folder_service import build_tree_for_folder, build_tree_for_user, folder_summary, validate_folder_move
from app.services.repo import get_owned_folder, new_folder_doc, next_position
from app.services.trash import trash_folder

router = APIRouter(prefix="/folders", tags=["folders"])


def _all_folders(db: Database, user_id: str) -> List[Dict[str, Any]]:
    return list(db.folders.find({"user_id": user_id}, {"_id": 0, "id": 1, "parent_id": 1}))


@router.get("/tree", response_model=List[FolderTreeResponse])
def get_folder_tree(db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    return build_tree_for_user(db, current_user.id)


@router.post("/", response_model=FolderTreeResponse, status_code=status.HTTP_201_CREATED)
def create_folder(folder_in: FolderCreate, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    parent_id = folder_in.parent_id or None
    if parent_id and not get_owned_folder(db, current_user.id, parent_id):
        raise HTTPException(status_code=404, detail="Parent folder not found")
    position = folder_in.position if folder_in.position is not None else next_position(
        db, "folders", {"user_id": current_user.id, "parent_id": parent_id}
    )
    doc = new_folder_doc(
        current_user.id,
        folder_in.name.strip(),
        parent_id,
        position,
        description=folder_in.description or "",
        tags=[t.strip()[:50] for t in (folder_in.tags or []) if t and t.strip()],
    )
    db.folders.insert_one(doc)
    return folder_summary(doc)


@router.post("/reorder")
def reorder_folders(items: List[ReorderItem], db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    now = now_iso()
    # One round trip instead of up to 2000 sequential updates.
    ops = [
        ({"id": item.id, "user_id": current_user.id}, {"$set": {"position": item.position, "updated_at": now}})
        for item in items[:2000]
    ]
    if ops:
        bulk_update(db.folders, ops)
    return {"message": "Folders reordered successfully"}


@router.put("/{folder_id}", response_model=FolderTreeResponse)
def update_folder(folder_id: str, folder_in: FolderUpdate, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    folder = get_owned_folder(db, current_user.id, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    updates: Dict[str, Any] = {}
    if folder_in.name is not None:
        updates["name"] = folder_in.name.strip()
    if folder_in.description is not None:
        updates["description"] = folder_in.description
    if folder_in.tags is not None:
        updates["tags"] = [t.strip()[:50] for t in folder_in.tags if t and t.strip()]
    if folder_in.parent_id is not None:
        target = folder_in.parent_id or None
        if target and not get_owned_folder(db, current_user.id, target):
            raise HTTPException(status_code=404, detail="Target parent folder not found")
        validate_folder_move(_all_folders(db, current_user.id), folder_id, target)
        updates["parent_id"] = target
    if folder_in.position is not None:
        updates["position"] = folder_in.position
    if updates:
        updates["updated_at"] = now_iso()
        db.folders.update_one({"id": folder_id, "user_id": current_user.id}, {"$set": updates})
        folder.update(updates)

    # Same recursive counts as /folders/tree, so progress doesn't change after a rename.
    tree = build_tree_for_folder(db, current_user.id, folder_id)
    if tree is not None:
        return tree
    direct = list(db.questions.find({"user_id": current_user.id, "folder_id": folder_id}, {"_id": 0, "status": 1}))
    return folder_summary(folder, len(direct), sum(1 for q in direct if q.get("status") == "Solved"))


@router.post("/{folder_id}/move")
def move_folder(folder_id: str, move_in: FolderMove, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    if not get_owned_folder(db, current_user.id, folder_id):
        raise HTTPException(status_code=404, detail="Folder not found")
    target = move_in.target_parent_id or None
    if target and not get_owned_folder(db, current_user.id, target):
        raise HTTPException(status_code=404, detail="Target parent folder not found")
    validate_folder_move(_all_folders(db, current_user.id), folder_id, target)
    updates: Dict[str, Any] = {"parent_id": target, "updated_at": now_iso()}
    updates["position"] = move_in.new_position if move_in.new_position is not None else next_position(
        db, "folders", {"user_id": current_user.id, "parent_id": target}
    )
    db.folders.update_one({"id": folder_id, "user_id": current_user.id}, {"$set": updates})
    return {"message": "Folder moved successfully", "folder_id": folder_id, "parent_id": target}


@router.delete("/{folder_id}")
def delete_folder(folder_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    if not get_owned_folder(db, current_user.id, folder_id):
        raise HTTPException(status_code=404, detail="Folder not found")
    trash_id, deleted = trash_folder(db, current_user.id, folder_id)
    for fid in deleted:
        share_service.disable_share(db, current_user.id, fid)
    return {"message": "Folder moved to trash", "deleted_folder_ids": sorted(deleted), "trash_id": trash_id}


# ---------------------------------------------------------------------------
# Sharing (owner side)
# ---------------------------------------------------------------------------

def _folder_name(db: Database, user: CurrentUser, folder_id: str) -> str:
    if folder_id == "all":
        return "All Patterns"
    folder = get_owned_folder(db, user.id, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found or unauthorized")
    return folder.get("name") or "Pattern"


def _share_response(share: Dict[str, Any], folder_name: str) -> ShareResponse:
    return ShareResponse(
        share_id=share["share_id"],
        folder_id=share["folder_id"],
        folder_name=share.get("folder_name") or folder_name,
        is_active=bool(share.get("is_active")),
        share_url=f"/shared/{share['share_id']}",
        created_at=share.get("created_at", ""),
        updated_at=share.get("updated_at", ""),
    )


@router.get("/{folder_id}/share", response_model=ShareResponse)
def get_folder_share_settings(folder_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    name = _folder_name(db, current_user, folder_id)
    share = share_service.get_share(db, current_user.id, folder_id)
    if not share:
        raise HTTPException(status_code=404, detail="No share configuration found for this folder")
    return _share_response(share, name)


@router.post("/{folder_id}/share", response_model=ShareResponse)
def enable_or_create_folder_share(folder_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    name = _folder_name(db, current_user, folder_id)
    share = share_service.create_or_enable_share(db, current_user, folder_id, name)
    return _share_response(share, name)


@router.patch("/{folder_id}/share", response_model=ShareResponse)
@router.put("/{folder_id}/share", response_model=ShareResponse)
def toggle_folder_share_status(folder_id: str, update_data: ShareStatusUpdate, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    name = _folder_name(db, current_user, folder_id)
    if update_data.is_active:
        share = share_service.create_or_enable_share(db, current_user, folder_id, name)
    else:
        share = share_service.disable_share(db, current_user.id, folder_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share settings not found")
    return _share_response(share, name)


@router.post("/{folder_id}/share/revoke", response_model=ShareResponse)
def revoke_and_regenerate_folder_share(folder_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    name = _folder_name(db, current_user, folder_id)
    share = share_service.regenerate_share(db, current_user, folder_id, name)
    return _share_response(share, name)


@router.delete("/{folder_id}/share")
def disable_folder_share(folder_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    _folder_name(db, current_user, folder_id)
    share_service.disable_share(db, current_user.id, folder_id)
    return {"message": "Sharing disabled successfully for this pattern"}
