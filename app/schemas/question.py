from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from app.schemas.solution import SolutionResponse
from app.schemas.test_case import TestCaseResponse

class QuestionBase(BaseModel):
    title: str
    folder_id: str
    problem_url: Optional[str] = ""
    problem_statement: Optional[str] = ""
    notes: Optional[str] = ""
    difficulty: Optional[str] = "Medium"
    status: Optional[str] = "Not Started"
    tags: Optional[List[str]] = []
    position: Optional[int] = None

class QuestionCreate(QuestionBase):
    pass

class QuestionUpdate(BaseModel):
    title: Optional[str] = None
    folder_id: Optional[str] = None
    problem_url: Optional[str] = None
    problem_statement: Optional[str] = None
    notes: Optional[str] = None
    difficulty: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    position: Optional[int] = None

class QuestionMove(BaseModel):
    target_folder_id: str
    new_position: Optional[int] = None

class QuestionResponse(BaseModel):
    id: str
    user_id: str
    folder_id: str
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
    model_config = ConfigDict(from_attributes=True)

class QuestionListItem(BaseModel):
    id: str
    folder_id: str
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
    model_config = ConfigDict(from_attributes=True)
