from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.db import get_db, new_id, now_iso
from app.routers.auth import CurrentUser, get_current_user
from app.schemas.solution import (
    AnalyzeComplexityRequest,
    AnalyzeComplexityResponse,
    SolutionCreate,
    SolutionResponse,
    SolutionUpdate,
)
from app.services.complexity_service import analyze_complexity, compute_code_hash
from app.services.repo import _sort_children, get_owned_question, next_position, to_solution

router = APIRouter(prefix="/solutions", tags=["solutions"])

MAX_SOLUTIONS_PER_QUESTION = 50


def _owned_solution(db: Database, user_id: str, solution_id: str) -> Dict[str, Any]:
    sol = db.solutions.find_one({"id": solution_id}, {"_id": 0})
    if not sol or not get_owned_question(db, user_id, sol.get("question_id", "")):
        raise HTTPException(status_code=404, detail="Solution not found")
    return sol


@router.post("/analyze-complexity", response_model=AnalyzeComplexityResponse)
def analyze_solution_code(payload: AnalyzeComplexityRequest, current_user: CurrentUser = Depends(get_current_user)):
    a = analyze_complexity(payload.code, payload.language)
    return AnalyzeComplexityResponse(
        time_complexity=a["time_complexity"], space_complexity=a["space_complexity"],
        explanation=a["explanation"], status=a["status"], code_hash=a["code_hash"],
    )


@router.get("/question/{question_id}", response_model=List[SolutionResponse])
def get_solutions_for_question(question_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    if not get_owned_question(db, current_user.id, question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    return [to_solution(s) for s in _sort_children(list(db.solutions.find({"question_id": question_id}, {"_id": 0})))]


@router.post("/question/{question_id}", response_model=SolutionResponse, status_code=status.HTTP_201_CREATED)
def create_solution(question_id: str, sol_in: SolutionCreate, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    if not get_owned_question(db, current_user.id, question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    if db.solutions.count_documents({"question_id": question_id}) >= MAX_SOLUTIONS_PER_QUESTION:
        raise HTTPException(status_code=400, detail=f"A question can have at most {MAX_SOLUTIONS_PER_QUESTION} solutions.")

    code = sol_in.code or ""
    language = sol_in.language or "python"
    a = analyze_complexity(code, language)
    now = now_iso()
    doc = {
        "id": new_id(),
        "question_id": question_id,
        "user_id": current_user.id,
        "title": sol_in.title or "Optimized Approach",
        "solution_type": sol_in.solution_type or "Optimized",
        "language": language,
        "code": code,
        "explanation": sol_in.explanation or "",
        "time_complexity_estimate": a["time_complexity"],
        "space_complexity_estimate": a["space_complexity"],
        "manual_time_complexity": sol_in.manual_time_complexity,
        "manual_space_complexity": sol_in.manual_space_complexity,
        # Time complexity is left for the user to state themselves.
        "time_complexity": sol_in.manual_time_complexity or sol_in.time_complexity or "",
        "space_complexity": sol_in.manual_space_complexity or sol_in.space_complexity or a["space_complexity"],
        "analysis_explanation": a["explanation"],
        "analysis_status": a["status"],
        "analyzed_code_hash": a["code_hash"],
        "position": sol_in.position if sol_in.position is not None else next_position(db, "solutions", {"question_id": question_id}),
        "created_at": now,
        "updated_at": now,
    }
    db.solutions.insert_one(doc)
    doc.pop("_id", None)
    db.questions.update_one({"id": question_id}, {"$set": {"updated_at": now}})
    return to_solution(doc)


@router.put("/{solution_id}", response_model=SolutionResponse)
def update_solution(solution_id: str, sol_in: SolutionUpdate, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    sol = _owned_solution(db, current_user.id, solution_id)
    u: Dict[str, Any] = {}
    for field in ("title", "solution_type", "language", "explanation", "position"):
        val = getattr(sol_in, field)
        if val is not None:
            u[field] = val
    if sol_in.manual_time_complexity is not None:
        u["manual_time_complexity"] = sol_in.manual_time_complexity or None
    if sol_in.manual_space_complexity is not None:
        u["manual_space_complexity"] = sol_in.manual_space_complexity or None
    if sol_in.code is not None:
        if compute_code_hash(sol_in.code.strip()) != (sol.get("analyzed_code_hash") or ""):
            a = analyze_complexity(sol_in.code, u.get("language") or sol.get("language") or "python")
            u.update({
                "time_complexity_estimate": a["time_complexity"],
                "space_complexity_estimate": a["space_complexity"],
                "analysis_explanation": a["explanation"],
                "analysis_status": a["status"],
                "analyzed_code_hash": a["code_hash"],
            })
        u["code"] = sol_in.code

    merged = {**sol, **u}
    if sol_in.time_complexity is not None:
        u["time_complexity"] = sol_in.time_complexity
    elif "manual_time_complexity" in u:
        # Clearing the manual value falls back to the analysed estimate, not the stale stored value
        # (which is the manual value being removed).
        u["time_complexity"] = merged.get("manual_time_complexity") or merged.get("time_complexity_estimate") or ""
    if sol_in.space_complexity is not None:
        u["space_complexity"] = sol_in.space_complexity
    elif "manual_space_complexity" in u or "space_complexity_estimate" in u:
        u["space_complexity"] = merged.get("manual_space_complexity") or merged.get("space_complexity_estimate") or "O(1)"

    if u:
        now = now_iso()
        u["updated_at"] = now
        db.solutions.update_one({"id": solution_id}, {"$set": u})
        db.questions.update_one({"id": sol["question_id"]}, {"$set": {"updated_at": now}})
        sol.update(u)
    return to_solution(sol)


@router.post("/{solution_id}/analyze", response_model=SolutionResponse)
def trigger_solution_analysis(solution_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    sol = _owned_solution(db, current_user.id, solution_id)
    a = analyze_complexity(sol.get("code") or "", sol.get("language") or "python")
    u = {
        "time_complexity_estimate": a["time_complexity"],
        "space_complexity_estimate": a["space_complexity"],
        "analysis_explanation": a["explanation"],
        "analysis_status": a["status"],
        "analyzed_code_hash": a["code_hash"],
        "updated_at": now_iso(),
    }
    if not sol.get("manual_space_complexity"):
        u["space_complexity"] = a["space_complexity"]
    db.solutions.update_one({"id": solution_id}, {"$set": u})
    sol.update(u)
    return to_solution(sol)


@router.delete("/{solution_id}")
def delete_solution(solution_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    _owned_solution(db, current_user.id, solution_id)
    db.solutions.delete_one({"id": solution_id})
    return {"message": "Solution deleted successfully", "id": solution_id}
