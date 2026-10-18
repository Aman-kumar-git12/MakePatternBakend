from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from app.schemas.question import QuestionListItem

class FolderBase(BaseModel):
    name: str
    parent_id: Optional[str] = None
    description: Optional[str] = ""
    tags: Optional[List[str]] = []
    position: Optional[int] = 0

class FolderCreate(FolderBase):
    pass

class FolderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    parent_id: Optional[str] = None
    position: Optional[int] = None

class FolderMove(BaseModel):
    target_parent_id: Optional[str] = None
    new_position: Optional[int] = None

class FolderTreeResponse(BaseModel):
    id: str
    user_id: str
    parent_id: Optional[str]
    name: str
    description: Optional[str] = ""
    tags: List[str] = []
    position: int
    created_at: datetime
    updated_at: datetime
    question_count: int = 0
    solved_count: int = 0
    progress_percentage: float = 0.0
    subfolders: List['FolderTreeResponse'] = []
    questions: List[QuestionListItem] = []
    model_config = ConfigDict(from_attributes=True)

FolderTreeResponse.model_rebuild()
