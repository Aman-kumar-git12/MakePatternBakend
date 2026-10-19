from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.test_case import TestCase
from app.models.question import Question
from app.models.user import User
from app.schemas.test_case import TestCaseCreate, TestCaseUpdate, TestCaseResponse
from app.routers.auth import get_current_user
from app.mongodb import save_test_case_mongo, delete_test_case_mongo

router = APIRouter(prefix="/test-cases", tags=["test_cases"])

@router.get("/question/{question_id}", response_model=List[TestCaseResponse])
def get_test_cases_for_question(
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

    return db.query(TestCase).filter(
        TestCase.question_id == question_id
    ).order_by(TestCase.position, TestCase.created_at).all()

@router.post("/question/{question_id}", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED)
def create_test_case(
    question_id: str,
    tc_in: TestCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = db.query(Question).filter(
        Question.id == question_id,
        Question.user_id == current_user.id
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    tc = TestCase(
        question_id=question_id,
        title=tc_in.title or "Test Case",
        input=tc_in.input or "",
        expected_output=tc_in.expected_output or "",
        notes=tc_in.notes or "",
        position=tc_in.position or 0
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    save_test_case_mongo(tc)
    return tc

@router.put("/{test_case_id}", response_model=TestCaseResponse)
def update_test_case(
    test_case_id: str,
    tc_in: TestCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tc = db.query(TestCase).join(Question).filter(
        TestCase.id == test_case_id,
        Question.user_id == current_user.id
    ).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")

    if tc_in.title is not None:
        tc.title = tc_in.title
    if tc_in.input is not None:
        tc.input = tc_in.input
    if tc_in.expected_output is not None:
        tc.expected_output = tc_in.expected_output
    if tc_in.notes is not None:
        tc.notes = tc_in.notes
    if tc_in.position is not None:
        tc.position = tc_in.position

    db.commit()
    db.refresh(tc)
    save_test_case_mongo(tc)
    return tc

@router.delete("/{test_case_id}")
def delete_test_case(
    test_case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tc = db.query(TestCase).join(Question).filter(
        TestCase.id == test_case_id,
        Question.user_id == current_user.id
    ).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")

    db.delete(tc)
    db.commit()
    delete_test_case_mongo(test_case_id)
    return {"message": "Test case deleted successfully", "id": test_case_id}
