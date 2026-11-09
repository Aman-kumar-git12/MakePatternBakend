from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class TrashItem(BaseModel):
    id: str
    kind: str
    title: str
    deleted_at: datetime
    expires_at: datetime
    question_count: int
    folder_count: int


class RestoreResponse(BaseModel):
    kind: Optional[str] = None
    restored_questions: int
    restored_folders: int
    folder_id: Optional[str] = None
    question_ids: List[str]
