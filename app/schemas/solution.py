from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime

class SolutionBase(BaseModel):
    title: str = "Optimized Approach"
    solution_type: str = "Optimized"  # "Brute Force", "Better Approach", "Optimized Approach", "Custom"
    language: str = "python"
    code: str = ""
    explanation: Optional[str] = ""
    time_complexity_estimate: Optional[str] = ""
    space_complexity_estimate: Optional[str] = "O(1)"
    manual_time_complexity: Optional[str] = None
    manual_space_complexity: Optional[str] = None
    time_complexity: str = ""
    space_complexity: str = "O(1)"
    analysis_explanation: Optional[str] = ""
    analysis_status: Optional[str] = "Completed"
    analyzed_code_hash: Optional[str] = ""
    position: Optional[int] = 0

class SolutionCreate(BaseModel):
    title: Optional[str] = Field(default="Optimized Approach", max_length=200)
    solution_type: Optional[str] = Field(default="Optimized", max_length=50)
    language: Optional[str] = Field(default="python", max_length=30)
    code: Optional[str] = Field(default="", max_length=100_000)
    explanation: Optional[str] = Field(default="", max_length=100_000)
    time_complexity: Optional[str] = Field(default=None, max_length=100)
    space_complexity: Optional[str] = Field(default=None, max_length=100)
    manual_time_complexity: Optional[str] = Field(default=None, max_length=100)
    manual_space_complexity: Optional[str] = Field(default=None, max_length=100)
    position: Optional[int] = Field(default=None, ge=0)

class SolutionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    solution_type: Optional[str] = Field(default=None, max_length=50)
    language: Optional[str] = Field(default=None, max_length=30)
    code: Optional[str] = Field(default=None, max_length=100_000)
    explanation: Optional[str] = Field(default=None, max_length=100_000)
    time_complexity: Optional[str] = Field(default=None, max_length=100)
    space_complexity: Optional[str] = Field(default=None, max_length=100)
    manual_time_complexity: Optional[str] = Field(default=None, max_length=100)
    manual_space_complexity: Optional[str] = Field(default=None, max_length=100)
    position: Optional[int] = Field(default=None, ge=0)

class SolutionResponse(SolutionBase):
    id: str
    question_id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AnalyzeComplexityRequest(BaseModel):
    code: str = Field(max_length=100_000)
    language: str = Field(default="python", max_length=30)

class AnalyzeComplexityResponse(BaseModel):
    time_complexity: str
    space_complexity: str
    explanation: str
    status: str
    code_hash: str
