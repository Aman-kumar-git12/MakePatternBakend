from pydantic import BaseModel, ConfigDict
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
    title: Optional[str] = "Optimized Approach"
    solution_type: Optional[str] = "Optimized"
    language: Optional[str] = "python"
    code: Optional[str] = ""
    explanation: Optional[str] = ""
    time_complexity: Optional[str] = None
    space_complexity: Optional[str] = None
    manual_time_complexity: Optional[str] = None
    manual_space_complexity: Optional[str] = None
    position: Optional[int] = 0

class SolutionUpdate(BaseModel):
    title: Optional[str] = None
    solution_type: Optional[str] = None
    language: Optional[str] = None
    code: Optional[str] = None
    explanation: Optional[str] = None
    time_complexity: Optional[str] = None
    space_complexity: Optional[str] = None
    manual_time_complexity: Optional[str] = None
    manual_space_complexity: Optional[str] = None
    position: Optional[int] = None

class SolutionResponse(SolutionBase):
    id: str
    question_id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AnalyzeComplexityRequest(BaseModel):
    code: str
    language: str = "python"

class AnalyzeComplexityResponse(BaseModel):
    time_complexity: str
    space_complexity: str
    explanation: str
    status: str
    code_hash: str
