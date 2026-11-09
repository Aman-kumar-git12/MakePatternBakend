import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.database import Database

from app.db import get_db, new_id, now_iso, parse_dt, parse_tags, to_iso
from app.routers.auth import CurrentUser, get_current_user, user_filter
from app.routers.questions import apply_status
from app.schemas.leetcode import (
    DailyChallenge,
    ImportRequest,
    LeetCodeProblem,
    LeetCodeProfile,
    SyncRequest,
    SyncResponse,
    TrackedSummary,
)
from app.schemas.question import QuestionResponse
from app.schemas.user import LEETCODE_USERNAME_RE
from app.services import leetcode as lc
from app.services.leetcode_parse import slug_from_url
from app.services.repo import (
    get_owned_folder,
    get_owned_question,
    new_folder_doc,
    new_question_doc,
    new_test_case_doc,
    next_position,
    to_response,
)
from app.services.tracking import status_change_updates

from app.services.ratelimit import check_rate_limit


def _lc_rate_limit(current_user: CurrentUser = Depends(get_current_user)) -> None:
    # Protects our server IP from being throttled/blocked by LeetCode.
    check_rate_limit(f"leetcode:{current_user.id}", limit=60, window_seconds=60)


router = APIRouter(prefix="/leetcode", tags=["leetcode"], dependencies=[Depends(_lc_rate_limit)])

IMPORT_FOLDER_NAME = "LeetCode Imports"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tracked_slugs(db: Database, user_id: str) -> Dict[str, str]:
    """slug -> question_id for everything the user tracks (by leetcode_slug or LeetCode URL)."""
    out: Dict[str, str] = {}
    for q in db.questions.find({"user_id": user_id}, {"_id": 0, "id": 1, "leetcode_slug": 1, "problem_url": 1}):
        slug = q.get("leetcode_slug") or slug_from_url(q.get("problem_url"))
        if slug and slug not in out:
            out[slug] = q["id"]
    return out


def find_tracked(db: Database, user_id: str, slug: str) -> Optional[Dict[str, Any]]:
    doc = db.questions.find_one({"user_id": user_id, "leetcode_slug": slug}, {"_id": 0})
    if doc:
        return doc
    rx = {"$regex": rf"leetcode\.(com|cn)/problems/{re.escape(slug)}(/|$|\?|#)", "$options": "i"}
    return db.questions.find_one({"user_id": user_id, "problem_url": rx}, {"_id": 0})


def _resolve_folder(db: Database, user_id: str, folder_id: Optional[str]) -> Optional[str]:
    if not folder_id or not folder_id.strip():
        return None
    folder = get_owned_folder(db, user_id, folder_id.strip())
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder["id"]


def _imports_folder(db: Database, user_id: str) -> str:
    existing = db.folders.find_one({"user_id": user_id, "parent_id": None, "name": IMPORT_FOLDER_NAME}, {"_id": 0, "id": 1})
    if existing:
        return existing["id"]
    doc = new_folder_doc(user_id, IMPORT_FOLDER_NAME, None, next_position(db, "folders", {"user_id": user_id, "parent_id": None}),
                         description="Problems imported from your LeetCode account.")
    db.folders.insert_one(doc)
    return doc["id"]


def _example_test_cases(question_id: str, user_id: str, examples: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    return [
        new_test_case_doc(question_id, user_id, f"Example {i}", ex.get("input", ""), ex.get("output", ""), ex.get("explanation", ""), i - 1)
        for i, ex in enumerate(examples[:10], start=1)
    ]


def build_question_from_problem(
    db: Database,
    user_id: str,
    problem: Dict[str, Any],
    folder_id: Optional[str],
    initial_status: Optional[str],
    solved_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Insert a tracked question (and its example test cases) built from LeetCode data."""
    doc = new_question_doc(
        user_id,
        folder_id=folder_id,
        title=problem["title"],
        problem_url=problem["url"],
        problem_statement=problem.get("statement_html") or "",
        difficulty=problem["difficulty"] if problem["difficulty"] in ("Easy", "Medium", "Hard") else "Medium",
        tags=problem.get("tags") or [],
        position=next_position(db, "questions", {"user_id": user_id, "folder_id": folder_id}),
        leetcode_slug=problem["slug"],
        leetcode_id=problem.get("frontend_id") or None,
    )
    if initial_status and initial_status != "Not Started":
        if solved_at is not None and initial_status == "Solved":
            _mark_solved_at(db, user_id, doc, solved_at, persist=False)
        else:
            updates: Dict[str, Any] = {}
            apply_status(db, user_id, doc, initial_status, updates)
            doc.update(updates)
    db.questions.insert_one(doc)
    doc.pop("_id", None)
    tcs = _example_test_cases(doc["id"], user_id, problem.get("examples") or [])
    if tcs:
        db.test_cases.insert_many(tcs)
    return doc


def _mark_solved_at(db: Database, user_id: str, q: Dict[str, Any], solved_at: datetime, persist: bool = True) -> bool:
    """Mark Solved, using the real LeetCode submission time for solved_at/activity."""
    updates, newly_solved = status_change_updates(q, "Solved")
    if newly_solved:
        updates["solved_at"] = to_iso(solved_at)
        db.activity.insert_one({
            "id": new_id(), "user_id": user_id, "type": "solved", "question_id": q["id"], "minutes": 0, "at": to_iso(solved_at),
        })
    q.update(updates)
    if persist:
        updates["updated_at"] = now_iso()
        db.questions.update_one({"id": q["id"], "user_id": user_id}, {"$set": updates})
    return newly_solved


def _with_tracking(item: Dict[str, Any], tracked: Dict[str, str]) -> Dict[str, Any]:
    qid = tracked.get(item["slug"])
    return {**item, "already_tracked": qid is not None, "question_id": qid}


def _valid_username(username: Optional[str]) -> str:
    username = (username or "").strip()
    if not username or not LEETCODE_USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="Enter a valid LeetCode username.")
    return username


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/problem", response_model=LeetCodeProblem)
def get_problem(q: str = Query(..., min_length=1, max_length=500), db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    problem = lc.resolve_problem(q)
    existing = find_tracked(db, current_user.id, problem["slug"])
    return {**problem, "already_tracked": existing is not None, "question_id": existing["id"] if existing else None}


@router.post("/import", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
def import_problem(body: ImportRequest, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    folder_id = _resolve_folder(db, current_user.id, body.folder_id)
    problem = lc.resolve_problem(body.q)
    existing = find_tracked(db, current_user.id, problem["slug"])
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"message": f"You already track \"{existing.get('title') or problem['title']}\".", "question_id": existing["id"]},
        )
    doc = build_question_from_problem(db, current_user.id, problem, folder_id, body.status)
    return to_response(db, doc, current_user.id)


@router.post("/refresh/{question_id}", response_model=QuestionResponse)
def refresh_problem(question_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    q = get_owned_question(db, current_user.id, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    slug = q.get("leetcode_slug") or slug_from_url(q.get("problem_url"))
    if not slug:
        raise HTTPException(status_code=400, detail="This question isn't linked to a LeetCode problem. Add its LeetCode URL first.")
    problem = lc.get_problem(slug)

    existing_tags = parse_tags(q.get("tags"))
    merged_tags = existing_tags + [t for t in problem.get("tags", []) if t not in existing_tags]
    updates: Dict[str, Any] = {
        "leetcode_slug": problem["slug"],
        "leetcode_id": problem.get("frontend_id") or None,
        "difficulty": problem["difficulty"] if problem["difficulty"] in ("Easy", "Medium", "Hard") else q.get("difficulty") or "Medium",
        "tags": merged_tags[:30],
        "updated_at": now_iso(),
    }
    if problem.get("statement_html"):
        updates["problem_statement"] = problem["statement_html"]
    if not (q.get("title") or "").strip() or q.get("title") == "Untitled":
        updates["title"] = problem["title"]
    if not q.get("problem_url"):
        updates["problem_url"] = problem["url"]
    db.questions.update_one({"id": question_id, "user_id": current_user.id}, {"$set": updates})
    q.update(updates)

    if db.test_cases.count_documents({"question_id": question_id}) == 0:
        tcs = _example_test_cases(question_id, current_user.id, problem.get("examples") or [])
        if tcs:
            db.test_cases.insert_many(tcs)
    return to_response(db, q, current_user.id)


@router.get("/daily", response_model=DailyChallenge)
def daily_challenge(db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    daily = lc.get_daily()
    existing = find_tracked(db, current_user.id, daily["problem"]["slug"])
    return {**daily, "already_tracked": existing is not None, "question_id": existing["id"] if existing else None}


@router.get("/search", response_model=List[TrackedSummary])
def search(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(default=10, ge=1, le=25),
    db: Database = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    results = lc.search_problems(q, limit=limit)
    tracked = tracked_slugs(db, current_user.id)
    return [_with_tracking(r, tracked) for r in results]


@router.get("/profile/{username}", response_model=LeetCodeProfile)
def profile(username: str, current_user: CurrentUser = Depends(get_current_user)):
    return lc.get_profile(_valid_username(username))


@router.post("/sync", response_model=SyncResponse)
def sync(body: SyncRequest, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    username = _valid_username(body.username or current_user.leetcode_username)
    target_folder = _resolve_folder(db, current_user.id, body.folder_id) if body.folder_id else None

    prof = lc.get_profile(username)  # 404s for unknown users before we save anything
    canonical = prof.get("username") or username
    db.users.update_one(user_filter(current_user.id), {"$set": {"leetcode_username": canonical, "updated_at": now_iso()}})

    recent = lc.get_recent_accepted(canonical, limit=20)
    seen = set()
    unique_recent = []
    for s in recent:  # newest first; keep the latest accepted per problem
        if s["slug"] not in seen:
            seen.add(s["slug"])
            unique_recent.append(s)

    newly_solved: List[str] = []
    already_solved = 0
    imported = 0
    for sub in unique_recent:
        solved_at = datetime.fromtimestamp(sub["timestamp"], tz=timezone.utc) if sub["timestamp"] else datetime.now(timezone.utc)
        q = find_tracked(db, current_user.id, sub["slug"])
        if q:
            status_now = q.get("status") or "Not Started"
            if status_now == "Solved":
                already_solved += 1
                continue
            # A problem the user flagged for revision after this accepted submission must not
            # be flipped back to Solved; only a newer accepted submission counts.
            if status_now == "Needs Revision":
                last_review = parse_dt(q.get("last_reviewed_at"))
                if last_review and solved_at <= last_review:
                    already_solved += 1
                    continue
            _mark_solved_at(db, current_user.id, q, solved_at)
            newly_solved.append(q.get("title") or sub["title"])
            continue
        if not body.import_missing:
            continue
        try:
            problem = lc.get_problem(sub["slug"])
        except HTTPException as e:
            if e.status_code == 404:
                continue
            raise
        folder_id = target_folder or _imports_folder(db, current_user.id)
        target_folder = folder_id
        build_question_from_problem(db, current_user.id, problem, folder_id, "Solved", solved_at=solved_at)
        imported += 1
        newly_solved.append(problem["title"])

    return {
        "username": canonical,
        "profile": prof,
        "recent_accepted": recent,
        "newly_solved": newly_solved,
        "imported": imported,
        "already_solved": already_solved,
    }
