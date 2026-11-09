from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.solution import SolutionResponse
from app.schemas.test_case import TestCaseResponse

Difficulty = Literal["Easy", "Medium", "Hard"]
Status = Literal["Not Started", "In Progress", "Solved", "Needs Revision"]

MAX_TEXT = 100_000


def _clean_tags(v: Optional[List[str]]) -> Optional[List[str]]:
    if v is None:
        return v
    # Reject huge payloads before doing any work on them (a tag list is never this long).
    if len(v) > 200:
        raise ValueError("At most 30 tags are allowed")
    out: List[str] = []
    seen = set()
    for t in v:
        t = (t or "").strip()[:50]
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    if len(out) > 30:
        raise ValueError("At most 30 tags are allowed")
    return out


class QuestionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    folder_id: Optional[str] = None
    problem_url: Optional[str] = Field(default="", max_length=500)
    problem_statement: Optional[str] = Field(default="", max_length=MAX_TEXT)
    notes: Optional[str] = Field(default="", max_length=MAX_TEXT)
    difficulty: Optional[Difficulty] = "Medium"
    status: Optional[Status] = "Not Started"
    tags: Optional[List[str]] = []
    position: Optional[int] = Field(default=None, ge=0)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _clean_tags(v)

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, v):
        # Strip before validating so a whitespace-only value fails min_length (422).
        return v.strip() if isinstance(v, str) else v

class QuestionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    # "" (empty string) moves the question to "no folder".
    folder_id: Optional[str] = None
    problem_url: Optional[str] = Field(default=None, max_length=500)
    problem_statement: Optional[str] = Field(default=None, max_length=MAX_TEXT)
    notes: Optional[str] = Field(default=None, max_length=MAX_TEXT)
    difficulty: Optional[Difficulty] = None
    status: Optional[Status] = None
    tags: Optional[List[str]] = None
    position: Optional[int] = Field(default=None, ge=0)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _clean_tags(v)

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, v):
        # Strip before validating so a whitespace-only value fails min_length (422).
        return v.strip() if isinstance(v, str) else v

class QuestionMove(BaseModel):
    target_folder_id: Optional[str] = None  # None / "" = unfiled
    new_position: Optional[int] = Field(default=None, ge=0)


class AttemptLog(BaseModel):
    minutes: int = Field(default=0, ge=0, le=600)
    solved: Optional[bool] = None


class QuestionTracking(BaseModel):
    leetcode_slug: Optional[str] = None
    leetcode_id: Optional[str] = None
    solved_at: Optional[datetime] = None
    attempts: int = 0
    time_spent_minutes: int = 0
    next_review_at: Optional[datetime] = None
    last_reviewed_at: Optional[datetime] = None
    review_count: int = 0
    review_interval_days: int = 0


class QuestionResponse(QuestionTracking):
    id: str
    user_id: str = ""
    folder_id: Optional[str] = None
    title: str
    problem_url: Optional[str] = ""
    problem_statement: str = ""
    notes: str = ""
    difficulty: str = "Medium"
    status: str = "Not Started"
    tags: List[str] = []
    position: int = 0
    is_bookmarked: bool = False
    folder_path: Optional[str] = None
    solutions: List[SolutionResponse] = []
    test_cases: List[TestCaseResponse] = []
    created_at: datetime
    updated_at: datetime


class QuestionListItem(QuestionTracking):
    id: str
    folder_id: Optional[str] = None
    title: str
    problem_url: Optional[str] = ""
    difficulty: str
    status: str
    tags: List[str]
    is_bookmarked: bool = False
    folder_path: Optional[str] = None
    position: Optional[int] = 0
    created_at: Optional[datetime] = None
    updated_at: datetime


BulkActionName = Literal["move", "set_status", "set_difficulty", "add_tags", "remove_tags", "bookmark", "unbookmark", "delete"]


class BulkAction(BaseModel):
    question_ids: List[str] = Field(min_length=1, max_length=500)
    action: BulkActionName
    folder_id: Optional[str] = None
    status: Optional[Status] = None
    difficulty: Optional[Difficulty] = None
    tags: Optional[List[str]] = None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _clean_tags(v)


class BulkActionResponse(BaseModel):
    action: str
    updated: int
    trash_id: Optional[str] = None
