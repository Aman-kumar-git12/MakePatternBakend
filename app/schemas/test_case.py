from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime

class TestCaseBase(BaseModel):
    title: str = "Test Case"
    input: str = ""
    expected_output: str = ""
    notes: Optional[str] = ""
    position: Optional[int] = 0

class TestCaseCreate(BaseModel):
    title: str = Field(default="Test Case", max_length=200)
    input: str = Field(default="", max_length=20_000)
    expected_output: str = Field(default="", max_length=20_000)
    notes: Optional[str] = Field(default="", max_length=20_000)
    position: Optional[int] = Field(default=None, ge=0)

class TestCaseUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    input: Optional[str] = Field(default=None, max_length=20_000)
    expected_output: Optional[str] = Field(default=None, max_length=20_000)
    notes: Optional[str] = Field(default=None, max_length=20_000)
    position: Optional[int] = Field(default=None, ge=0)

class TestCaseResponse(TestCaseBase):
    id: str
    question_id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
