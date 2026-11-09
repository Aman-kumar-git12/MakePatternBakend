from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.db import get_db, now_iso
from app.routers.auth import CurrentUser, get_current_user
from app.schemas.test_case import TestCaseCreate, TestCaseResponse, TestCaseUpdate
from app.services.repo import _sort_children, get_owned_question, new_test_case_doc, next_position, to_test_case

router = APIRouter(prefix="/test-cases", tags=["test_cases"])

MAX_TEST_CASES_PER_QUESTION = 100


def _owned_test_case(db: Database, user_id: str, test_case_id: str) -> Dict[str, Any]:
    tc = db.test_cases.find_one({"id": test_case_id}, {"_id": 0})
    if not tc or not get_owned_question(db, user_id, tc.get("question_id", "")):
        raise HTTPException(status_code=404, detail="Test case not found")
    return tc


@router.get("/question/{question_id}", response_model=List[TestCaseResponse])
def get_test_cases_for_question(question_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    if not get_owned_question(db, current_user.id, question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    return [to_test_case(t) for t in _sort_children(list(db.test_cases.find({"question_id": question_id}, {"_id": 0})))]


@router.post("/question/{question_id}", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED)
def create_test_case(question_id: str, tc_in: TestCaseCreate, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    if not get_owned_question(db, current_user.id, question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    if db.test_cases.count_documents({"question_id": question_id}) >= MAX_TEST_CASES_PER_QUESTION:
        raise HTTPException(status_code=400, detail=f"A question can have at most {MAX_TEST_CASES_PER_QUESTION} test cases.")
    position = tc_in.position if tc_in.position is not None else next_position(db, "test_cases", {"question_id": question_id})
    doc = new_test_case_doc(question_id, current_user.id, tc_in.title or "Test Case", tc_in.input or "", tc_in.expected_output or "", tc_in.notes or "", position)
    db.test_cases.insert_one(doc)
    doc.pop("_id", None)
    return to_test_case(doc)


@router.put("/{test_case_id}", response_model=TestCaseResponse)
def update_test_case(test_case_id: str, tc_in: TestCaseUpdate, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    tc = _owned_test_case(db, current_user.id, test_case_id)
    u = {k: v for k, v in tc_in.model_dump(exclude_unset=True).items() if v is not None}
    if u:
        u["updated_at"] = now_iso()
        db.test_cases.update_one({"id": test_case_id}, {"$set": u})
        tc.update(u)
    return to_test_case(tc)


@router.delete("/{test_case_id}")
def delete_test_case(test_case_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    _owned_test_case(db, current_user.id, test_case_id)
    db.test_cases.delete_one({"id": test_case_id})
    return {"message": "Test case deleted successfully", "id": test_case_id}
