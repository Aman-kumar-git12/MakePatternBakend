"""Restore a MakePattern JSON export into the user's workspace (always as new items)."""
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pymongo.database import Database

from app.db import new_id, now_iso, parse_dt, parse_tags, to_iso
from app.services.leetcode_parse import slug_from_url
from app.services.repo import new_folder_doc, new_question_doc, next_position
from app.services.tracking import REVIEW_LADDER

MAX_QUESTIONS = 5000
MAX_FOLDERS = 2000
STATUSES = {"Not Started", "In Progress", "Solved", "Needs Revision"}
DIFFICULTIES = {"Easy", "Medium", "Hard"}


def _s(v: Any, limit: int, default: str = "") -> str:
    if v is None:
        return default
    return str(v)[:limit]


def _int(v: Any, lo: int = 0, hi: int = 10**9) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


def _dt(v: Any) -> Optional[str]:
    d = parse_dt(v)
    return to_iso(d) if d else None


def _list(payload: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    v = payload.get(key) or []
    if not isinstance(v, list):
        raise HTTPException(status_code=400, detail=f"Invalid export file: '{key}' must be a list.")
    return [d for d in v if isinstance(d, dict)]


def import_export(db: Database, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("format") != "makepattern-export":
        raise HTTPException(status_code=400, detail="This doesn't look like a MakePattern export file.")
    try:
        version = int(payload.get("version") or 0)
    except (TypeError, ValueError):
        version = -1
    if version != 1:
        raise HTTPException(status_code=400, detail="Unsupported export version.")

    folders_in = _list(payload, "folders")
    questions_in = _list(payload, "questions")
    if len(questions_in) > MAX_QUESTIONS or len(folders_in) > MAX_FOLDERS:
        raise HTTPException(status_code=413, detail=f"Import is limited to {MAX_QUESTIONS} questions and {MAX_FOLDERS} folders.")

    now = now_iso()
    root_name = f"Imported {date.today().isoformat()}"
    root = new_folder_doc(user_id, root_name, None, next_position(db, "folders", {"user_id": user_id, "parent_id": None}))

    # Folders: fresh ids, hierarchy preserved, top-level folders go under the import root.
    fmap: Dict[str, str] = {}
    for f in folders_in:
        if f.get("id"):
            fmap[str(f["id"])] = new_id()
    folders: List[Dict[str, Any]] = [root]
    for f in folders_in:
        old = str(f.get("id") or "")
        if old not in fmap:
            continue
        parent = fmap.get(str(f.get("parent_id") or ""))
        if parent == fmap[old]:
            parent = None
        folders.append({
            "id": fmap[old], "user_id": user_id, "parent_id": parent or root["id"],
            "name": _s(f.get("name"), 200, "Folder") or "Folder", "description": _s(f.get("description"), 20_000),
            "tags": parse_tags(f.get("tags"))[:30], "position": _int(f.get("position"), 0, 100_000),
            "created_at": _dt(f.get("created_at")) or now, "updated_at": now,
        })

    # A parent cycle (A -> B -> A) would detach those folders, and their questions, from the
    # tree. Re-attach any folder whose ancestor chain loops to the import root.
    by_id = {f["id"]: f for f in folders}
    for f in folders[1:]:
        seen = {f["id"]}
        cur = by_id.get(f["parent_id"])
        while cur is not None and cur["id"] != root["id"]:
            if cur["id"] in seen:
                f["parent_id"] = root["id"]
                break
            seen.add(cur["id"])
            cur = by_id.get(cur["parent_id"])

    # Questions
    qmap: Dict[str, str] = {}
    questions: List[Dict[str, Any]] = []
    for i, q in enumerate(questions_in):
        old = str(q.get("id") or f"_{i}")
        qmap[old] = new_id()
        url = _s(q.get("problem_url"), 500)
        status = q.get("status") if q.get("status") in STATUSES else "Not Started"
        questions.append(new_question_doc(
            user_id,
            id=qmap[old],
            folder_id=fmap.get(str(q.get("folder_id") or "")) or root["id"],
            title=_s(q.get("title"), 300, "Untitled") or "Untitled",
            problem_url=url,
            problem_statement=_s(q.get("problem_statement"), 100_000),
            notes=_s(q.get("notes"), 100_000),
            difficulty=q.get("difficulty") if q.get("difficulty") in DIFFICULTIES else "Medium",
            status=status,
            tags=parse_tags(q.get("tags"))[:30],
            position=_int(q.get("position"), 0, 100_000),
            leetcode_slug=_s(q.get("leetcode_slug"), 200) or slug_from_url(url),
            leetcode_id=_s(q.get("leetcode_id"), 20) or None,
            solved_at=_dt(q.get("solved_at")),
            attempts=_int(q.get("attempts"), 0, 100_000),
            time_spent_minutes=_int(q.get("time_spent_minutes"), 0, 10_000_000),
            next_review_at=_dt(q.get("next_review_at")),
            last_reviewed_at=_dt(q.get("last_reviewed_at")),
            review_count=_int(q.get("review_count"), 0, 100_000),
            review_step=_int(q.get("review_step"), -1, len(REVIEW_LADDER) - 1) if q.get("review_step") is not None else -1,
            review_interval_days=_int(q.get("review_interval_days"), 0, 1000),
            created_at=_dt(q.get("created_at")) or now,
            updated_at=now,
        ))

    def children(
        key: str, fields: Dict[str, int], legacy: Optional[Dict[str, str]] = None, optional: tuple = ()
    ) -> List[Dict[str, Any]]:
        out = []
        for d in _list(payload, key)[: MAX_QUESTIONS * 50]:
            qid = qmap.get(str(d.get("question_id") or ""))
            if not qid:
                continue
            # Older exports used different field names (the same fallbacks the API reads with).
            src = dict(d)
            for new, old in (legacy or {}).items():
                if src.get(new) in (None, "") and src.get(old) not in (None, ""):
                    src[new] = src[old]
            doc = {k: _s(src.get(k), limit) for k, limit in fields.items()}
            for k in optional:  # nullable fields: keep None rather than ""
                if src.get(k) in (None, ""):
                    doc[k] = None
            doc.update({"id": new_id(), "question_id": qid, "user_id": user_id,
                        "position": _int(d.get("position"), 0, 100_000),
                        "created_at": _dt(d.get("created_at")) or now, "updated_at": now})
            out.append(doc)
        return out

    solutions = children("solutions", {
        "title": 200, "solution_type": 50, "language": 30, "code": 100_000, "explanation": 100_000,
        "time_complexity": 100, "space_complexity": 100, "time_complexity_estimate": 100,
        "space_complexity_estimate": 100, "analysis_explanation": 20_000, "analysis_status": 50,
        "manual_time_complexity": 100, "manual_space_complexity": 100, "analyzed_code_hash": 128,
    }, legacy={"solution_type": "approach_type", "explanation": "notes"},
       optional=("manual_time_complexity", "manual_space_complexity", "analyzed_code_hash"))
    test_cases = children(
        "test_cases", {"title": 200, "input": 20_000, "expected_output": 20_000, "notes": 20_000},
        legacy={"input": "input_data", "notes": "explanation"},
    )
    bookmarks = [
        {"id": new_id(), "user_id": user_id, "question_id": qmap[str(b.get("question_id"))], "created_at": now}
        for b in _list(payload, "bookmarks") if str(b.get("question_id")) in qmap
    ]
    # Activity history is only restored into an account that has none (avoids double-counting).
    activity = []
    if not db.activity.find_one({"user_id": user_id}, {"_id": 1}):
        for a in _list(payload, "activity")[:200_000]:
            at = _dt(a.get("at"))
            if at and a.get("type") in ("solved", "review", "attempt"):
                activity.append({"id": new_id(), "user_id": user_id, "type": a["type"],
                                 "question_id": qmap.get(str(a.get("question_id") or "")),
                                 "minutes": _int(a.get("minutes"), 0, 600), "at": at})

    db.folders.insert_many(folders)
    for coll, docs in (("questions", questions), ("solutions", solutions), ("test_cases", test_cases),
                       ("bookmarks", list({b["question_id"]: b for b in bookmarks}.values())), ("activity", activity)):
        if docs:
            db[coll].insert_many(docs)

    return {
        "root_folder_id": root["id"],
        "root_folder_name": root_name,
        "folders": len(folders) - 1,
        "questions": len(questions),
        "solutions": len(solutions),
        "test_cases": len(test_cases),
    }
