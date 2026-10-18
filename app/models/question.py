from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from app.database import Base

class Question(Base):
    __tablename__ = "questions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id = Column(String(36), ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    problem_url = Column(String(500), default="")
    problem_statement = Column(Text, default="")
    notes = Column(Text, default="")
    difficulty = Column(String(20), default="Medium")  # Easy, Medium, Hard
    status = Column(String(30), default="Not Started")  # Not Started, In Progress, Solved, Needs Revision
    tags = Column(Text, default="[]")  # JSON encoded list of tags
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="questions")
    folder = relationship("Folder", back_populates="questions")
    solutions = relationship("Solution", back_populates="question", cascade="all, delete-orphan", order_by="Solution.position")
    bookmarks = relationship("Bookmark", back_populates="question", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="question", cascade="all, delete-orphan", order_by="TestCase.position")
