"""Document <-> response mapping and multi-document operations (batched, no N+1)."""
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set

from pymongo.database import Database

from app.db import new_id, now_iso, parse_dt, parse_tags, ts
from app.schemas.question import QuestionListItem, QuestionResponse
from app.schemas.solution import SolutionResponse
from app.schemas.test_case import TestCaseResponse


# ---------------------------------------------------------------------------
# Folder paths
# ---------------------------------------------------------------------------

class FolderPaths:
    """Resolves "A / B / C" folder paths from one query instead of one per ancestor."""

    def __init__(self, folders: Iterable[Dict[str, Any]]):
        self._folders = {f["id"]: f for f in folders if f.get("id")}
        self._cache: Dict[str, str] = {}

    @classmethod
    def for_user(cls, db: Database, user_id: str) -> "FolderPaths":
        return cls(db.folders.find({"user_id": user_id}, {"_id": 0, "id": 1, "name": 1, "parent_id": 1}))

    def path(self, folder_id: Optional[str]) -> str:
        if not folder_id:
            return ""
        if folder_id in self._cache:
            return self._cache[folder_id]
        names: List[str] = []
        seen: Set[str] = set()
        cur = folder_id
        while cur and cur not in seen and cur in self._folders:
            seen.add(cur)
            names.append(self._folders[cur].get("name") or "")
            cur = self._folders[cur].get("parent_id")
        result = " / ".join(reversed(names))
        self._cache[folder_id] = result
        return result


def bookmarked_ids(db: Database, user_id: str) -> Set[str]:
    return {b["question_id"] for b in db.bookmarks.find({"user_id": user_id}, {"_id": 0, "question_id": 1})}


# ---------------------------------------------------------------------------
# Question mapping
# ---------------------------------------------------------------------------

def _tracking_fields(q: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "leetcode_slug": q.get("leetcode_slug") or None,
        "leetcode_id": str(q["leetcode_id"]) if q.get("leetcode_id") else None,
        "solved_at": parse_dt(q.get("solved_at")),
        "attempts": int(q.get("attempts") or 0),
        "time_spent_minutes": int(q.get("time_spent_minutes") or 0),
        "next_review_at": parse_dt(q.get("next_review_at")),
        "last_reviewed_at": parse_dt(q.get("last_reviewed_at")),
        "review_count": int(q.get("review_count") or 0),
        "review_interval_days": int(q.get("review_interval_days") or 0),
    }


def to_list_item(q: Dict[str, Any], bookmarked: Set[str], paths: Optional[FolderPaths]) -> QuestionListItem:
    return QuestionListItem(
        id=q["id"],
        folder_id=q.get("folder_id") or None,
        title=q.get("title") or "Untitled",
        problem_url=q.get("problem_url") or "",
        difficulty=q.get("difficulty") or "Medium",
        status=q.get("status") or "Not Started",
        tags=parse_tags(q.get("tags")),
        is_bookmarked=q["id"] in bookmarked,
        folder_path=paths.path(q.get("folder_id")) if paths else "",
        position=int(q.get("position") or 0),
        created_at=ts(q, "created_at"),
        updated_at=ts(q, "updated_at"),
        **_tracking_fields(q),
    )


def to_solution(s: Dict[str, Any]) -> SolutionResponse:
    return SolutionResponse(
        id=s["id"],
        question_id=s["question_id"],
        title=s.get("title") or "Optimized Approach",
        solution_type=s.get("solution_type") or s.get("approach_type") or "Optimized",
        language=s.get("language") or "python",
        code=s.get("code") or "",
        explanation=s.get("explanation") or s.get("notes") or "",
        time_complexity_estimate=s.get("time_complexity_estimate") or "",
        space_complexity_estimate=s.get("space_complexity_estimate") or "O(1)",
        manual_time_complexity=s.get("manual_time_complexity"),
        manual_space_complexity=s.get("manual_space_complexity"),
        time_complexity=s.get("time_complexity") or "",
        space_complexity=s.get("space_complexity") or "O(1)",
        analysis_explanation=s.get("analysis_explanation") or "",
        analysis_status=s.get("analysis_status") or "Completed",
        analyzed_code_hash=s.get("analyzed_code_hash") or "",
        position=int(s.get("position") or 0),
        created_at=ts(s, "created_at"),
        updated_at=ts(s, "updated_at"),
    )


def to_test_case(tc: Dict[str, Any]) -> TestCaseResponse:
    return TestCaseResponse(
        id=tc["id"],
        question_id=tc["question_id"],
        title=tc.get("title") or "Test Case",
        input=tc.get("input") or tc.get("input_data") or "",
        expected_output=tc.get("expected_output") or "",
        notes=tc.get("notes") or tc.get("explanation") or "",
        position=int(tc.get("position") or 0),
        created_at=ts(tc, "created_at"),
        updated_at=ts(tc, "updated_at"),
    )


def _sort_children(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(docs, key=lambda d: (int(d.get("position") or 0), str(d.get("created_at") or "")))


def to_responses(
    db: Database,
    questions: List[Dict[str, Any]],
    bookmarked: Set[str],
    paths: Optional[FolderPaths],
) -> List[QuestionResponse]:
    """Full question responses for many questions with 2 extra queries total."""
    qids = [q["id"] for q in questions]
    sols: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    tcs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if qids:
        for s in db.solutions.find({"question_id": {"$in": qids}}, {"_id": 0}):
            sols[s["question_id"]].append(s)
        for tc in db.test_cases.find({"question_id": {"$in": qids}}, {"_id": 0}):
            tcs[tc["question_id"]].append(tc)

    out = []
    for q in questions:
        out.append(
            QuestionResponse(
                id=q["id"],
                user_id=q.get("user_id") or "",
                folder_id=q.get("folder_id") or None,
                title=q.get("title") or "Untitled",
                problem_url=q.get("problem_url") or "",
                problem_statement=q.get("problem_statement") or "",
                notes=q.get("notes") or "",
                difficulty=q.get("difficulty") or "Medium",
                status=q.get("status") or "Not Started",
                tags=parse_tags(q.get("tags")),
                position=int(q.get("position") or 0),
                is_bookmarked=q["id"] in bookmarked,
                folder_path=paths.path(q.get("folder_id")) if paths else "",
                solutions=[to_solution(s) for s in _sort_children(sols[q["id"]])],
                test_cases=[to_test_case(t) for t in _sort_children(tcs[q["id"]])],
                created_at=ts(q, "created_at"),
                updated_at=ts(q, "updated_at"),
                **_tracking_fields(q),
            )
        )
    return out


def to_response(db: Database, q: Dict[str, Any], user_id: str) -> QuestionResponse:
    is_bm = db.bookmarks.find_one({"user_id": user_id, "question_id": q["id"]}, {"_id": 1}) is not None
    paths = FolderPaths.for_user(db, user_id) if q.get("folder_id") else None
    return to_responses(db, [q], {q["id"]} if is_bm else set(), paths)[0]


# ---------------------------------------------------------------------------
# Lookups with ownership checks
# ---------------------------------------------------------------------------

def get_owned_question(db: Database, user_id: str, question_id: str) -> Optional[Dict[str, Any]]:
    return db.questions.find_one({"id": question_id, "user_id": user_id}, {"_id": 0})


def get_owned_folder(db: Database, user_id: str, folder_id: str) -> Optional[Dict[str, Any]]:
    return db.folders.find_one({"id": folder_id, "user_id": user_id}, {"_id": 0})


def next_position(db: Database, collection: str, query: Dict[str, Any]) -> int:
    doc = db[collection].find_one(query, {"_id": 0, "position": 1}, sort=[("position", -1)])
    return int(doc.get("position") or 0) + 1 if doc else 0


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def new_question_doc(user_id: str, **fields: Any) -> Dict[str, Any]:
    now = now_iso()
    doc = {
        "id": new_id(),
        "user_id": user_id,
        "folder_id": None,
        "title": "Untitled",
        "problem_url": "",
        "problem_statement": "",
        "notes": "",
        "difficulty": "Medium",
        "status": "Not Started",
        "tags": [],
        "position": 0,
        "leetcode_slug": None,
        "leetcode_id": None,
        "solved_at": None,
        "attempts": 0,
        "time_spent_minutes": 0,
        "next_review_at": None,
        "last_reviewed_at": None,
        "review_count": 0,
        "review_step": -1,
        "review_interval_days": 0,
        "created_at": now,
        "updated_at": now,
    }
    doc.update(fields)
    return doc


def new_folder_doc(user_id: str, name: str, parent_id: Optional[str], position: int, description: str = "", tags: Optional[List[str]] = None) -> Dict[str, Any]:
    now = now_iso()
    return {
        "id": new_id(),
        "user_id": user_id,
        "parent_id": parent_id,
        "name": name,
        "description": description or "",
        "tags": tags or [],
        "position": position,
        "created_at": now,
        "updated_at": now,
    }


def new_test_case_doc(question_id: str, user_id: str, title: str, input_: str, expected: str, notes: str = "", position: int = 0) -> Dict[str, Any]:
    now = now_iso()
    return {
        "id": new_id(),
        "question_id": question_id,
        "user_id": user_id,
        "title": title,
        "input": input_,
        "expected_output": expected,
        "notes": notes,
        "position": position,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Cascading deletes (children first so a partial failure never orphans data)
# ---------------------------------------------------------------------------

def delete_questions_cascade(db: Database, question_ids: List[str]) -> None:
    if not question_ids:
        return
    db.solutions.delete_many({"question_id": {"$in": question_ids}})
    db.test_cases.delete_many({"question_id": {"$in": question_ids}})
    db.bookmarks.delete_many({"question_id": {"$in": question_ids}})
    db.questions.delete_many({"id": {"$in": question_ids}})


def descendant_folder_ids(folders: List[Dict[str, Any]], root_id: str) -> Set[str]:
    children: Dict[str, List[str]] = defaultdict(list)
    for f in folders:
        if f.get("parent_id"):
            children[f["parent_id"]].append(f["id"])
    out: Set[str] = set()
    stack = [root_id]
    while stack:
        cur = stack.pop()
        for c in children.get(cur, []):
            if c not in out:
                out.add(c)
                stack.append(c)
    return out


def delete_folder_cascade(db: Database, user_id: str, folder_id: str) -> Set[str]:
    folders = list(db.folders.find({"user_id": user_id}, {"_id": 0, "id": 1, "parent_id": 1}))
    target = descendant_folder_ids(folders, folder_id) | {folder_id}
    qids = [q["id"] for q in db.questions.find({"user_id": user_id, "folder_id": {"$in": list(target)}}, {"_id": 0, "id": 1})]
    delete_questions_cascade(db, qids)
    db.folders.delete_many({"user_id": user_id, "id": {"$in": list(target)}})
    return target


def delete_user_cascade(db: Database, user_id: str) -> None:
    qids = [q["id"] for q in db.questions.find({"user_id": user_id}, {"_id": 0, "id": 1})]
    delete_questions_cascade(db, qids)
    db.folders.delete_many({"user_id": user_id})
    db.bookmarks.delete_many({"user_id": user_id})
    db.activity.delete_many({"user_id": user_id})
    db.share_snapshots.delete_many({"user_id": user_id})
    db.trash.delete_many({"user_id": user_id})
    db.users.delete_many({"$or": [{"id": user_id}, {"_id": user_id}]})
