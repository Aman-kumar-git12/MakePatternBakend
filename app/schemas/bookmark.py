from pydantic import BaseModel, ConfigDict
from datetime import datetime
from app.schemas.question import QuestionResponse

class BookmarkToggleResponse(BaseModel):
    question_id: str
    is_bookmarked: bool
    message: str

class BookmarkResponse(BaseModel):
    id: str
    user_id: str
    question_id: str
    created_at: datetime
    question: QuestionResponse
    model_config = ConfigDict(from_attributes=True)
