from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.db import get_db, parse_dt
from app.routers.auth import CurrentUser, get_current_user
from app.schemas.trash import RestoreResponse, TrashItem
from app.services.trash import purge_expired, restore

router = APIRouter(prefix="/trash", tags=["trash"])


@router.get("", response_model=List[TrashItem])
@router.get("/", response_model=List[TrashItem], include_in_schema=False)
def list_trash(db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    purge_expired(db, current_user.id)
    items = db.trash.find({"user_id": current_user.id}, {"_id": 0, "payload": 0}).sort("deleted_at", -1).limit(500)
    return [
        TrashItem(id=t["id"], kind=t.get("kind") or "question", title=t.get("title") or "Untitled",
                  deleted_at=parse_dt(t["deleted_at"]), expires_at=parse_dt(t["expires_at"]),
                  question_count=int(t.get("question_count") or 0), folder_count=int(t.get("folder_count") or 0))
        for t in items
    ]


@router.post("/{trash_id}/restore", response_model=RestoreResponse)
def restore_item(trash_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    return restore(db, current_user.id, trash_id)


@router.delete("/{trash_id}")
def delete_forever(trash_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    res = db.trash.delete_one({"id": trash_id, "user_id": current_user.id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="This item is no longer in the trash.")
    return {"message": "Deleted permanently"}


@router.delete("")
@router.delete("/", include_in_schema=False)
def empty_trash(db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    res = db.trash.delete_many({"user_id": current_user.id})
    return {"deleted": res.deleted_count}
