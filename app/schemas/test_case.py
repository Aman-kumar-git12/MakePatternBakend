from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class TestCaseBase(BaseModel):
    title: str = "Test Case"
    input: str = ""
    expected_output: str = ""
    notes: Optional[str] = ""
    position: Optional[int] = 0

class TestCaseCreate(TestCaseBase):
    pass

class TestCaseUpdate(BaseModel):
    title: Optional[str] = None
    input: Optional[str] = None
    expected_output: Optional[str] = None
    notes: Optional[str] = None
    position: Optional[int] = None

class TestCaseResponse(TestCaseBase):
    id: str
    question_id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
