from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.solution import Solution
from app.models.question import Question
from app.models.user import User
from app.schemas.solution import (
    SolutionCreate,
    SolutionUpdate,
    SolutionResponse,
    AnalyzeComplexityRequest,
    AnalyzeComplexityResponse
)
from app.routers.auth import get_current_user
from app.services.complexity_service import analyze_complexity, compute_code_hash
from app.mongodb import save_solution_mongo, delete_solution_mongo

router = APIRouter(prefix="/solutions", tags=["solutions"])

@router.post("/analyze-complexity", response_model=AnalyzeComplexityResponse)
def analyze_solution_code(
    payload: AnalyzeComplexityRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Analyzes code complexity on-demand without saving.
    Returns estimated time & space complexity, explanation, and status.
    """
    analysis = analyze_complexity(payload.code, payload.language)
    return AnalyzeComplexityResponse(
        time_complexity=analysis["time_complexity"],
        space_complexity=analysis["space_complexity"],
        explanation=analysis["explanation"],
        status=analysis["status"],
        code_hash=analysis["code_hash"]
    )

@router.get("/question/{question_id}", response_model=List[SolutionResponse])
def get_solutions_for_question(
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

    solutions = db.query(Solution).filter(
        Solution.question_id == question_id
    ).order_by(Solution.position, Solution.created_at).all()

    return solutions

@router.post("/question/{question_id}", response_model=SolutionResponse, status_code=status.HTTP_201_CREATED)
def create_solution(
    question_id: str,
    sol_in: SolutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = db.query(Question).filter(
        Question.id == question_id,
        Question.user_id == current_user.id
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    code = sol_in.code or ""
    language = sol_in.language or "python"

    # Analyze complexity
    analysis = analyze_complexity(code, language)
    est_time = analysis["time_complexity"]
    est_space = analysis["space_complexity"]

    # Time complexity is left empty for user to provide themselves
    eff_time = sol_in.manual_time_complexity or sol_in.time_complexity or ""
    eff_space = sol_in.manual_space_complexity or sol_in.space_complexity or est_space

    sol = Solution(
        question_id=question_id,
        title=sol_in.title or "Optimized Approach",
        solution_type=sol_in.solution_type or "Optimized",
        language=language,
        code=code,
        explanation=sol_in.explanation or "",
        time_complexity_estimate=est_time,
        space_complexity_estimate=est_space,
        manual_time_complexity=sol_in.manual_time_complexity,
        manual_space_complexity=sol_in.manual_space_complexity,
        time_complexity=eff_time,
        space_complexity=eff_space,
        analysis_explanation=analysis["explanation"],
        analysis_status=analysis["status"],
        analyzed_code_hash=analysis["code_hash"],
        position=sol_in.position or 0
    )
    db.add(sol)
    db.commit()
    db.refresh(sol)
    save_solution_mongo(sol)
    return sol

@router.put("/{solution_id}", response_model=SolutionResponse)
def update_solution(
    solution_id: str,
    sol_in: SolutionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sol = db.query(Solution).join(Question).filter(
        Solution.id == solution_id,
        Question.user_id == current_user.id
    ).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solution not found")

    if sol_in.title is not None:
        sol.title = sol_in.title
    if sol_in.solution_type is not None:
        sol.solution_type = sol_in.solution_type
    if sol_in.language is not None:
        sol.language = sol_in.language
    if sol_in.explanation is not None:
        sol.explanation = sol_in.explanation
    if sol_in.position is not None:
        sol.position = sol_in.position

    # Check if manual override was changed
    if sol_in.manual_time_complexity is not None:
        sol.manual_time_complexity = sol_in.manual_time_complexity or None
    if sol_in.manual_space_complexity is not None:
        sol.manual_space_complexity = sol_in.manual_space_complexity or None

    # Handle code update & complexity re-analysis
    if sol_in.code is not None:
        new_hash = compute_code_hash(sol_in.code)
        if new_hash != getattr(sol, 'analyzed_code_hash', ''):
            # Code modified -> re-run static analysis
            analysis = analyze_complexity(sol_in.code, sol.language)
            sol.time_complexity_estimate = analysis["time_complexity"]
            sol.space_complexity_estimate = analysis["space_complexity"]
            sol.analysis_explanation = analysis["explanation"]
            sol.analysis_status = analysis["status"]
            sol.analyzed_code_hash = analysis["code_hash"]
        sol.code = sol_in.code

    # If explicit time/space passed
    if sol_in.time_complexity is not None:
        sol.time_complexity = sol_in.time_complexity
    else:
        sol.time_complexity = sol.manual_time_complexity or sol.time_complexity or ""

    if sol_in.space_complexity is not None:
        sol.space_complexity = sol_in.space_complexity
    else:
        sol.space_complexity = sol.manual_space_complexity or sol.space_complexity_estimate or "O(1)"

    db.commit()
    db.refresh(sol)
    save_solution_mongo(sol)
    return sol

@router.post("/{solution_id}/analyze", response_model=SolutionResponse)
def trigger_solution_analysis(
    solution_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Re-runs analysis on an existing saved solution.
    """
    sol = db.query(Solution).join(Question).filter(
        Solution.id == solution_id,
        Question.user_id == current_user.id
    ).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solution not found")

    analysis = analyze_complexity(sol.code or "", sol.language)
    sol.time_complexity_estimate = analysis["time_complexity"]
    sol.space_complexity_estimate = analysis["space_complexity"]
    sol.analysis_explanation = analysis["explanation"]
    sol.analysis_status = analysis["status"]
    sol.analyzed_code_hash = analysis["code_hash"]

    # Space complexity can update if not manually set, time complexity is left for user
    if not sol.manual_space_complexity:
        sol.space_complexity = analysis["space_complexity"]

    db.commit()
    db.refresh(sol)
    save_solution_mongo(sol)
    return sol

@router.delete("/{solution_id}")
def delete_solution(
    solution_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sol = db.query(Solution).join(Question).filter(
        Solution.id == solution_id,
        Question.user_id == current_user.id
    ).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solution not found")

    db.delete(sol)
    db.commit()
    delete_solution_mongo(solution_id)
    return {"message": "Solution deleted successfully", "id": solution_id}
