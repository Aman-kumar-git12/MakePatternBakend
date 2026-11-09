from typing import List

from fastapi import APIRouter, Depends, status
from pymongo.database import Database

from app.db import get_db
from app.routers.auth import CurrentUser, get_current_user
from app.routers.leetcode import tracked_slugs
from app.schemas.leetcode import CurriculumImportResponse, CurriculumInfo
from app.services.curricula import import_curriculum, list_curricula

router = APIRouter(prefix="/curricula", tags=["curricula"])


@router.get("", response_model=List[CurriculumInfo])
@router.get("/", response_model=List[CurriculumInfo], include_in_schema=False)
def get_curricula(current_user: CurrentUser = Depends(get_current_user)):
    return list_curricula()


@router.post("/{curriculum_id}/import", response_model=CurriculumImportResponse, status_code=status.HTTP_201_CREATED)
def import_into_workspace(curriculum_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    return import_curriculum(db, current_user.id, curriculum_id, tracked_slugs(db, current_user.id))
