from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List
from datetime import datetime
from app.schemas.question import QuestionListItem

class FolderBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: Optional[str] = None
    description: Optional[str] = Field(default="", max_length=20_000)
    tags: Optional[List[str]] = Field(default=[], max_length=30)
    position: Optional[int] = Field(default=None, ge=0)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v):
        # Strip before validating so a whitespace-only value fails min_length (422).
        return v.strip() if isinstance(v, str) else v

class FolderCreate(FolderBase):
    pass

class FolderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=20_000)
    tags: Optional[List[str]] = Field(default=None, max_length=30)
    parent_id: Optional[str] = None  # "" = move to root
    position: Optional[int] = Field(default=None, ge=0)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v):
        # Strip before validating so a whitespace-only value fails min_length (422).
        return v.strip() if isinstance(v, str) else v

class FolderMove(BaseModel):
    target_parent_id: Optional[str] = None
    new_position: Optional[int] = Field(default=None, ge=0)

class ReorderItem(BaseModel):
    id: str
    position: int = Field(ge=0)

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

class ShareStatusUpdate(BaseModel):
    is_active: bool

class ShareResponse(BaseModel):
    share_id: str
    folder_id: str
    folder_name: str
    is_active: bool
    share_url: str
    created_at: str
    updated_at: str

class PublicSharedPatternResponse(BaseModel):
    share_id: str
    owner_name: str
    share_type: str = "single"  # "single" or "all"
    pattern: Optional[FolderTreeResponse] = None
    patterns: Optional[List[FolderTreeResponse]] = None



class ForkResponse(BaseModel):
    folder_id: str
    folder_name: str
    questions_imported: int
