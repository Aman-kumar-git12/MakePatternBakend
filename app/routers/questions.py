import json
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.database import get_db
from app.models.question import Question
from app.models.folder import Folder
from app.models.bookmark import Bookmark
from app.models.user import User
from app.schemas.question import (
    QuestionCreate,
    QuestionUpdate,
    QuestionMove,
    QuestionResponse,
    QuestionListItem
)
from app.schemas.solution import SolutionResponse
from app.schemas.folder import ReorderItem
from app.routers.auth import get_current_user
from app.services.folder_service import get_folder_path_string

router = APIRouter(prefix="/questions", tags=["questions"])

from app.schemas.test_case import TestCaseResponse

def format_question_response(db: Session, q: Question, user_id: str) -> QuestionResponse:
    tags_list = []
    try:
        tags_list = json.loads(q.tags) if q.tags else []
    except Exception:
        tags_list = [q.tags] if q.tags else []

    is_bookmarked = db.query(Bookmark).filter(
        Bookmark.user_id == user_id,
        Bookmark.question_id == q.id
    ).first() is not None

    folder_path = get_folder_path_string(db, q.folder_id)

    solutions = [
        SolutionResponse(
            id=s.id,
            question_id=s.question_id,
            title=s.title,
            solution_type=getattr(s, 'solution_type', 'Optimized') or 'Optimized',
            language=s.language,
            code=s.code,
            explanation=getattr(s, 'explanation', '') or '',
            time_complexity_estimate=getattr(s, 'time_complexity_estimate', '') or '',
            space_complexity_estimate=getattr(s, 'space_complexity_estimate', 'O(1)') or 'O(1)',
            manual_time_complexity=getattr(s, 'manual_time_complexity', None),
            manual_space_complexity=getattr(s, 'manual_space_complexity', None),
            time_complexity=s.time_complexity,
            space_complexity=s.space_complexity,
            analysis_explanation=getattr(s, 'analysis_explanation', '') or '',
            analysis_status=getattr(s, 'analysis_status', 'Completed') or 'Completed',
            analyzed_code_hash=getattr(s, 'analyzed_code_hash', '') or '',
            position=s.position,
            created_at=s.created_at,
            updated_at=s.updated_at
        )
        for s in q.solutions
    ]

    test_cases = [
        TestCaseResponse(
            id=tc.id,
            question_id=tc.question_id,
            title=tc.title,
            input=tc.input,
            expected_output=tc.expected_output,
            notes=tc.notes or '',
            position=tc.position,
            created_at=tc.created_at,
            updated_at=tc.updated_at
        )
        for tc in (q.test_cases if hasattr(q, 'test_cases') else [])
    ]

    return QuestionResponse(
        id=q.id,
        user_id=q.user_id,
        folder_id=q.folder_id,
        title=q.title,
        problem_url=getattr(q, 'problem_url', '') or "",
        problem_statement=q.problem_statement or "",
        notes=q.notes or "",
        difficulty=q.difficulty or "Medium",
        status=q.status or "Not Started",
        tags=tags_list,
        position=q.position,
        is_bookmarked=is_bookmarked,
        folder_path=folder_path,
        solutions=solutions,
        test_cases=test_cases,
        created_at=q.created_at,
        updated_at=q.updated_at
    )

@router.get("/", response_model=List[QuestionListItem])
def list_questions(
    folder_id: Optional[str] = None,
    difficulty: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Question).filter(Question.user_id == current_user.id)

    if folder_id:
        query = query.filter(Question.folder_id == folder_id)
    if difficulty:
        query = query.filter(Question.difficulty == difficulty)
    if status:
        query = query.filter(Question.status == status)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Question.title.ilike(search_filter)) |
            (Question.problem_statement.ilike(search_filter)) |
            (Question.notes.ilike(search_filter)) |
            (Question.tags.ilike(search_filter))
        )

    questions = query.order_by(Question.position.asc(), Question.created_at.asc()).all()
    bookmarked_ids = {b.question_id for b in db.query(Bookmark).filter(Bookmark.user_id == current_user.id).all()}

    result = []
    for q in questions:
        tags_list = []
        try:
            tags_list = json.loads(q.tags) if q.tags else []
        except Exception:
            tags_list = [q.tags] if q.tags else []

        result.append(
            QuestionListItem(
                id=q.id,
                folder_id=q.folder_id,
                title=q.title,
                problem_url=getattr(q, 'problem_url', '') or "",
                difficulty=q.difficulty,
                status=q.status,
                tags=tags_list,
                is_bookmarked=(q.id in bookmarked_ids),
                folder_path=get_folder_path_string(db, q.folder_id),
                position=q.position or 0,
                created_at=q.created_at,
                updated_at=q.updated_at
            )
        )
    return result

@router.get("/random", response_model=List[QuestionListItem])
def get_random_questions(
    count: int = Query(default=5, ge=1, le=10, description="Number of random questions to return (max 10)"),
    only_revision: bool = Query(default=False, description="Filter only questions flagged for revision"),
    status: Optional[str] = Query(default=None, description="Optional status filter"),
    difficulty: Optional[str] = Query(default=None, description="Optional difficulty filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Question).filter(Question.user_id == current_user.id)
    if only_revision or status == "Needs Revision":
        query = query.filter(Question.status == "Needs Revision")
    elif status:
        query = query.filter(Question.status == status)

    if difficulty and difficulty != "all":
        query = query.filter(Question.difficulty == difficulty)

    questions = query.order_by(func.random()).limit(count).all()

    bookmarked_ids = {b.question_id for b in db.query(Bookmark).filter(Bookmark.user_id == current_user.id).all()}

    result = []
    for q in questions:
        tags_list = []
        try:
            tags_list = json.loads(q.tags) if q.tags else []
        except Exception:
            tags_list = [q.tags] if q.tags else []

        result.append(
            QuestionListItem(
                id=q.id,
                folder_id=q.folder_id,
                title=q.title,
                problem_url=getattr(q, 'problem_url', '') or "",
                difficulty=q.difficulty,
                status=q.status,
                tags=tags_list,
                is_bookmarked=(q.id in bookmarked_ids),
                folder_path=get_folder_path_string(db, q.folder_id),
                position=q.position or 0,
                created_at=q.created_at,
                updated_at=q.updated_at
            )
        )
    return result

@router.get("/{question_id}", response_model=QuestionResponse)
def get_question(
    question_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = db.query(Question).filter(
        Question.id == question_id,
        Question.user_id == current_user.id
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    return format_question_response(db, q, current_user.id)

@router.post("/", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
def create_question(
    q_in: QuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder = db.query(Folder).filter(
        Folder.id == q_in.folder_id,
        Folder.user_id == current_user.id
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    tags_str = json.dumps(q_in.tags or [])

    if q_in.position is not None and q_in.position > 0:
        q_pos = q_in.position
    else:
        max_pos = db.query(func.max(Question.position)).filter(
            Question.user_id == current_user.id,
            Question.folder_id == q_in.folder_id
        ).scalar()
        q_pos = (max_pos + 1) if max_pos is not None else 0

    question = Question(
        user_id=current_user.id,
        folder_id=q_in.folder_id,
        title=q_in.title.strip(),
        problem_url=(q_in.problem_url or "").strip(),
        problem_statement=q_in.problem_statement or "",
        notes=q_in.notes or "",
        difficulty=q_in.difficulty or "Medium",
        status=q_in.status or "Not Started",
        tags=tags_str,
        position=q_pos
    )
    db.add(question)
    db.commit()
    db.refresh(question)

    return format_question_response(db, question, current_user.id)

@router.post("/reorder")
def reorder_questions(
    items: List[ReorderItem],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    for item in items:
        db.query(Question).filter(
            Question.id == item.id,
            Question.user_id == current_user.id
        ).update({"position": item.position})
    db.commit()
    return {"message": "Questions reordered successfully"}

@router.put("/{question_id}", response_model=QuestionResponse)
def update_question(
    question_id: str,
    q_in: QuestionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = db.query(Question).filter(
        Question.id == question_id,
        Question.user_id == current_user.id
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    if q_in.title is not None:
        q.title = q_in.title.strip()
    if q_in.problem_url is not None:
        q.problem_url = q_in.problem_url.strip()
    if q_in.folder_id is not None:
        folder = db.query(Folder).filter(
            Folder.id == q_in.folder_id,
            Folder.user_id == current_user.id
        ).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Target folder not found")
        q.folder_id = q_in.folder_id
    if q_in.problem_statement is not None:
        q.problem_statement = q_in.problem_statement
    if q_in.notes is not None:
        q.notes = q_in.notes
    if q_in.difficulty is not None:
        q.difficulty = q_in.difficulty
    if q_in.status is not None:
        q.status = q_in.status
    if q_in.tags is not None:
        q.tags = json.dumps(q_in.tags)
    if q_in.position is not None:
        q.position = q_in.position

    db.commit()
    db.refresh(q)
    return format_question_response(db, q, current_user.id)

@router.post("/{question_id}/move")
def move_question(
    question_id: str,
    move_in: QuestionMove,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = db.query(Question).filter(
        Question.id == question_id,
        Question.user_id == current_user.id
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    target_folder = db.query(Folder).filter(
        Folder.id == move_in.target_folder_id,
        Folder.user_id == current_user.id
    ).first()
    if not target_folder:
        raise HTTPException(status_code=404, detail="Target folder not found")

    q.folder_id = move_in.target_folder_id
    if move_in.new_position is not None:
        q.position = move_in.new_position

    db.commit()
    return {"message": "Question moved successfully", "question_id": q.id, "folder_id": q.folder_id}

@router.delete("/{question_id}")
def delete_question(
    question_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = db.query(Question).filter(
        Question.id == question_id,
        Question.user_id == current_user.id
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    db.delete(q)
    db.commit()
    return {"message": "Question deleted successfully", "id": question_id}
