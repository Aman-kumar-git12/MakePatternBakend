"""Spaced repetition, solve tracking and activity/streak computation."""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Header
from pymongo.database import Database

from app.db import new_id, now_utc, parse_dt, to_iso

# Review ladder in days. Each successful review climbs one rung.
REVIEW_LADDER = [1, 3, 7, 14, 30, 60, 120]


def get_user_tz(x_timezone: Optional[str] = Header(default=None)) -> ZoneInfo:
    """FastAPI dependency: the browser's IANA zone (X-Timezone header), default UTC."""
    if x_timezone:
        try:
            return ZoneInfo(x_timezone[:64])
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return ZoneInfo("UTC")


def local_today(tz: ZoneInfo) -> date:
    return now_utc().astimezone(tz).date()


def end_of_local_day_iso(tz: ZoneInfo, day: Optional[date] = None) -> str:
    day = day or local_today(tz)
    end_local = datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(days=1) - timedelta(microseconds=1)
    return to_iso(end_local)


def start_of_local_day_iso(tz: ZoneInfo, day: Optional[date] = None) -> str:
    day = day or local_today(tz)
    return to_iso(datetime(day.year, day.month, day.day, tzinfo=tz))


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

def status_change_updates(q: Dict[str, Any], new_status: str, now: Optional[datetime] = None) -> Tuple[Dict[str, Any], bool]:
    """Fields to set when a question's status changes. Returns (updates, newly_solved)."""
    now = now or now_utc()
    old = q.get("status") or "Not Started"
    updates: Dict[str, Any] = {"status": new_status}
    newly_solved = False
    if new_status == old:
        return updates, False
    if new_status == "Solved":
        if not q.get("solved_at"):
            updates["solved_at"] = to_iso(now)
            newly_solved = True
        if not q.get("next_review_at"):
            updates["next_review_at"] = to_iso(now + timedelta(days=REVIEW_LADDER[0]))
            updates["review_step"] = 0
            updates["review_interval_days"] = REVIEW_LADDER[0]
    elif new_status == "Needs Revision":
        updates["next_review_at"] = to_iso(now)  # due right away
    elif new_status in ("Not Started", "In Progress"):
        updates["next_review_at"] = None
    return updates, newly_solved


def review_updates(q: Dict[str, Any], rating: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or now_utc()
    step = q.get("review_step")
    top = len(REVIEW_LADDER) - 1
    step = min(int(step), top) if step is not None else -1
    if rating == "again":
        step = 0
    elif rating == "hard":
        step = max(step, 0)
    elif rating == "good":
        step = min(step + 1, top)
    else:  # easy
        step = min(step + 2, top)
    interval = REVIEW_LADDER[step]
    updates: Dict[str, Any] = {
        "review_step": step,
        "review_interval_days": interval,
        "next_review_at": to_iso(now + timedelta(days=interval)),
        "last_reviewed_at": to_iso(now),
        "review_count": int(q.get("review_count") or 0) + 1,
    }
    status = q.get("status") or "Not Started"
    if rating == "again":
        updates["status"] = "Needs Revision"
    elif status in ("Needs Revision", "Not Started", "In Progress"):
        updates["status"] = "Solved"
        if not q.get("solved_at"):
            updates["solved_at"] = to_iso(now)
    return updates


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

def record_activity(
    db: Database,
    user_id: str,
    kind: str,
    question_id: Optional[str] = None,
    minutes: int = 0,
    at: Optional[datetime] = None,
    client_id: Optional[str] = None,
) -> None:
    doc = {
        "id": new_id(),
        "user_id": user_id,
        "type": kind,  # solved | review | attempt
        "question_id": question_id,
        "minutes": minutes,
        "at": to_iso(at or now_utc()),
    }
    if client_id:
        doc["client_id"] = client_id
    db.activity.insert_one(doc)  # raises DuplicateKeyError for a repeated client_id


def daily_activity(db: Database, user_id: str, tz: ZoneInfo, days: int) -> Dict[str, Dict[str, int]]:
    today = local_today(tz)
    start = today - timedelta(days=days - 1)
    since = start_of_local_day_iso(tz, start)
    buckets: Dict[str, Dict[str, int]] = {}
    for a in db.activity.find({"user_id": user_id, "at": {"$gte": since}}, {"_id": 0, "type": 1, "at": 1}):
        at = parse_dt(a.get("at"))
        if not at:
            continue
        key = at.astimezone(tz).date().isoformat()
        b = buckets.setdefault(key, {"count": 0, "solved": 0, "reviewed": 0})
        b["count"] += 1
        if a.get("type") == "solved":
            b["solved"] += 1
        elif a.get("type") == "review":
            b["reviewed"] += 1
    return buckets


def streaks(active_dates: List[date], today: date) -> Tuple[int, int]:
    """(current, longest). Current streak survives until the end of today."""
    if not active_dates:
        return 0, 0
    s = sorted(set(active_dates))
    longest = run = 1
    for prev, cur in zip(s, s[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        longest = max(longest, run)
    active = set(s)
    cur_day = today if today in active else today - timedelta(days=1)
    current = 0
    while cur_day in active:
        current += 1
        cur_day -= timedelta(days=1)
    return current, longest


def all_active_dates(db: Database, user_id: str, tz: ZoneInfo) -> List[date]:
    out = []
    for a in db.activity.find({"user_id": user_id}, {"_id": 0, "at": 1}):
        at = parse_dt(a.get("at"))
        if at:
            out.append(at.astimezone(tz).date())
    return out


def utc_now_iso() -> str:
    return to_iso(datetime.now(timezone.utc))
