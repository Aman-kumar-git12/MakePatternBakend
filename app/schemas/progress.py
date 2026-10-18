from pydantic import BaseModel
from typing import Dict, List, Optional
from app.schemas.question import QuestionListItem

class DifficultyBreakdown(BaseModel):
    total: int = 0
    solved: int = 0

class FolderProgressItem(BaseModel):
    folder_id: str
    folder_name: str
    total_questions: int
    solved_questions: int
    progress_percentage: float

class OverallProgressResponse(BaseModel):
    total_topics: int = 0
    total_subtopics: int = 0
    total_questions: int
    solved_questions: int
    in_progress_questions: int
    needs_revision_questions: int
    not_started_questions: int
    overall_percentage: float
    difficulty_breakdown: Dict[str, DifficultyBreakdown]
    recent_questions: List[QuestionListItem]
    continue_learning: List[QuestionListItem]
    folder_overview: List[FolderProgressItem]

