from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.question import Status


class LeetCodeSummary(BaseModel):
    slug: str
    frontend_id: str
    title: str
    difficulty: str
    tags: List[str] = []
    url: str
    acceptance_rate: Optional[float] = None
    is_paid_only: bool = False


class TrackedSummary(LeetCodeSummary):
    already_tracked: bool = False
    question_id: Optional[str] = None


class LeetCodeExample(BaseModel):
    input: str = ""
    output: str = ""
    explanation: str = ""


class LeetCodeProblem(TrackedSummary):
    statement_html: str = ""
    hints: List[str] = []
    examples: List[LeetCodeExample] = []


class DailyChallenge(BaseModel):
    date: str
    problem: LeetCodeSummary
    already_tracked: bool = False
    question_id: Optional[str] = None


class ImportRequest(BaseModel):
    q: str = Field(min_length=1, max_length=500)
    folder_id: Optional[str] = None
    status: Optional[Status] = None


class SyncRequest(BaseModel):
    username: Optional[str] = Field(default=None, max_length=40)
    import_missing: bool = False
    folder_id: Optional[str] = None


class LeetCodeProfile(BaseModel):
    username: str
    real_name: str = ""
    ranking: Optional[int] = None
    avatar: str = ""
    solved: Dict[str, int]
    total: Dict[str, int]


class RecentAccepted(BaseModel):
    slug: str
    title: str
    timestamp: int


class SyncResponse(BaseModel):
    username: str
    profile: LeetCodeProfile
    recent_accepted: List[RecentAccepted]
    newly_solved: List[str]
    imported: int
    already_solved: int


class CurriculumInfo(BaseModel):
    id: str
    name: str
    description: str
    problem_count: int
    patterns: List[str]


class CurriculumImportResponse(BaseModel):
    folder_id: str
    folder_name: str
    questions_imported: int
