from datetime import date, timedelta
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from app.db import get_db
from app.routers.auth import CurrentUser, get_current_user
from app.schemas.progress import (
    ActivityDay,
    ActivityResponse,
    DifficultyBreakdown,
    FolderProgressItem,
    OverallProgressResponse,
)
from app.services.folder_service import build_tree_for_user
from app.services.repo import FolderPaths, bookmarked_ids, to_list_item
from app.services.tracking import (
    all_active_dates,
    daily_activity,
    end_of_local_day_iso,
    get_user_tz,
    local_today,
    start_of_local_day_iso,
    streaks,
)

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/summary", response_model=OverallProgressResponse)
def get_progress_summary(
    db: Database = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    tz: ZoneInfo = Depends(get_user_tz),
):
    uid = current_user.id
    questions: List[Dict[str, Any]] = list(db.questions.find({"user_id": uid}, {"_id": 0, "problem_statement": 0, "notes": 0}))
    bm = bookmarked_ids(db, uid)
    paths = FolderPaths.for_user(db, uid)

    counts = {s: 0 for s in ("Solved", "In Progress", "Needs Revision", "Not Started")}
    diff = {d: DifficultyBreakdown() for d in ("Easy", "Medium", "Hard")}
    for q in questions:
        st = q.get("status") or "Not Started"
        counts[st if st in counts else "Not Started"] += 1
        d = q.get("difficulty") if q.get("difficulty") in diff else "Medium"
        diff[d].total += 1
        if st == "Solved":
            diff[d].solved += 1
    total = len(questions)

    by_recent = sorted(questions, key=lambda q: str(q.get("updated_at") or ""), reverse=True)
    recent = [to_list_item(q, bm, paths) for q in by_recent[:6]]
    continue_q = [q for q in by_recent if q.get("status") in ("In Progress", "Needs Revision")][:4]
    if len(continue_q) < 4:
        continue_q += [q for q in by_recent if q.get("status") == "Not Started"][: 4 - len(continue_q)]
    continue_items = [to_list_item(q, bm, paths) for q in continue_q]

    # Overview: top-level topics; if everything lives under a single root, show its children.
    trees = build_tree_for_user(db, uid)
    display = trees[0].subfolders if len(trees) == 1 and trees[0].subfolders else trees
    folder_overview = [
        FolderProgressItem(folder_id=f.id, folder_name=f.name, total_questions=f.question_count,
                           solved_questions=f.solved_count, progress_percentage=f.progress_percentage)
        for f in display
    ]
    folder_count = db.folders.count_documents({"user_id": uid})
    root_count = db.folders.count_documents({"user_id": uid, "parent_id": None})

    today = local_today(tz)
    current, longest = streaks(all_active_dates(db, uid, tz), today)
    week_start = start_of_local_day_iso(tz, today - timedelta(days=6))
    # solved_at is kept when a question leaves Solved, so also require it to still be Solved.
    solved_this_week = sum(
        1 for q in questions
        if q.get("status") == "Solved" and q.get("solved_at") and str(q["solved_at"]) >= week_start
    )
    due_cutoff = end_of_local_day_iso(tz)
    due = sum(1 for q in questions if q.get("next_review_at") and str(q["next_review_at"]) <= due_cutoff)
    active_days = len(daily_activity(db, uid, tz, 365))

    return OverallProgressResponse(
        total_topics=root_count,
        total_subtopics=folder_count - root_count,
        total_questions=total,
        solved_questions=counts["Solved"],
        in_progress_questions=counts["In Progress"],
        needs_revision_questions=counts["Needs Revision"],
        not_started_questions=counts["Not Started"],
        overall_percentage=round(counts["Solved"] / total * 100, 1) if total else 0.0,
        difficulty_breakdown=diff,
        recent_questions=recent,
        continue_learning=continue_items,
        folder_overview=folder_overview,
        current_streak=current,
        longest_streak=longest,
        solved_this_week=solved_this_week,
        due_reviews=due,
        total_time_minutes=sum(int(q.get("time_spent_minutes") or 0) for q in questions),
        active_days=active_days,
    )


@router.get("/activity", response_model=ActivityResponse)
def get_activity(
    days: int = Query(default=365, ge=7, le=730),
    db: Database = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    tz: ZoneInfo = Depends(get_user_tz),
):
    buckets = daily_activity(db, current_user.id, tz, days)
    today = local_today(tz)
    out = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        b = buckets.get(d, {})
        out.append(ActivityDay(date=d, count=b.get("count", 0), solved=b.get("solved", 0), reviewed=b.get("reviewed", 0)))
    current, longest = streaks(all_active_dates(db, current_user.id, tz), today)
    return ActivityResponse(days=out, current_streak=current, longest_streak=longest, total_active_days=len(buckets))
