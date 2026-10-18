from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from app.database import Base

class Solution(Base):
    __tablename__ = "solutions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id = Column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), default="Optimized Approach")
    solution_type = Column(String(50), default="Optimized")  # "Brute Force", "Better Approach", "Optimized Approach", "Custom"
    language = Column(String(50), default="python")  # python, cpp, java, javascript
    code = Column(Text, default="")
    explanation = Column(Text, default="")  # Optional explanation for this specific solution
    time_complexity_estimate = Column(String(100), default="")
    space_complexity_estimate = Column(String(100), default="O(1)")
    manual_time_complexity = Column(String(100), nullable=True)
    manual_space_complexity = Column(String(100), nullable=True)
    time_complexity = Column(String(100), default="")  # User specifies time complexity
    space_complexity = Column(String(100), default="O(1)")  # Effective displayed space complexity
    analysis_explanation = Column(Text, default="")  # Why complexity was estimated
    analysis_status = Column(String(50), default="Completed")  # "Analyzing", "Completed", "Unable to Analyze"
    analyzed_code_hash = Column(String(64), default="")
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    question = relationship("Question", back_populates="solutions")
