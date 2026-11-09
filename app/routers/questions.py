import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.database import Database

from app.db import bulk_update, get_db, new_id, now_iso, parse_tags
from app.routers.auth import CurrentUser, get_current_user
from app.schemas.folder import ReorderItem
from app.schemas.question import (
    AttemptLog,
    BulkAction,
    BulkActionResponse,
    Difficulty,
    QuestionCreate,
    QuestionListItem,
    QuestionMove,
    QuestionResponse,
    QuestionUpdate,
    Status,
)
from app.services.leetcode_parse import slug_from_url
from app.services.repo import (
    FolderPaths,
    bookmarked_ids,
    delete_questions_cascade,
    get_owned_folder,
    get_owned_question,
    new_question_doc,
    next_position,
    to_list_item,
    to_response,
)
from app.services.tracking import record_activity, status_change_updates
from app.services.trash import trash_questions

router = APIRouter(prefix="/questions", tags=["questions"])

LIST_PROJECTION = {"_id": 0, "problem_statement": 0, "notes": 0}


def format_question_response(db: Database, q: Dict[str, Any], user_id: str) -> QuestionResponse:
    return to_response(db, q, user_id)


def _search_filter(term: str) -> Dict[str, Any]:
    rx = {"$regex": re.escape(term[:200]), "$options": "i"}
    return {"$or": [{"title": rx}, {"problem_statement": rx}, {"notes": rx}, {"tags": rx}, {"leetcode_id": term.strip()}]}


def _resolve_folder(db: Database, user_id: str, folder_id: Optional[str]) -> Optional[str]:
    """'' / None -> unfiled; otherwise must be owned."""
    if not folder_id or not folder_id.strip():
        return None
    folder = get_owned_folder(db, user_id, folder_id.strip())
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder["id"]


def apply_status(db: Database, user_id: str, q: Dict[str, Any], new_status: str, updates: Dict[str, Any]) -> None:
    status_updates, newly_solved = status_change_updates(q, new_status)
    updates.update(status_updates)
    if newly_solved:
        record_activity(db, user_id, "solved", q["id"])


@router.get("/", response_model=List[QuestionListItem])
def list_questions(
    folder_id: Optional[str] = None,
    difficulty: Optional[Difficulty] = None,
    status: Optional[Status] = None,
    search: Optional[str] = Query(default=None, max_length=200),
    db: Database = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    query: Dict[str, Any] = {"user_id": current_user.id}
    if folder_id:
        query["folder_id"] = folder_id
    if difficulty:
        query["difficulty"] = difficulty
    if status:
        query["status"] = status
    if search:
        query.update(_search_filter(search))
    docs = list(db.questions.find(query, LIST_PROJECTION).sort([("position", 1), ("created_at", 1)]))
    paths = FolderPaths.for_user(db, current_user.id)
    bm = bookmarked_ids(db, current_user.id)
    return [to_list_item(q, bm, paths) for q in docs]


@router.get("/random", response_model=List[QuestionListItem])
def get_random_questions(
    count: int = Query(default=3, ge=1, le=5),
    only_revision: bool = Query(default=False),
    pool: Optional[str] = Query(default="all"),
    status: Optional[str] = Query(default=None),
    difficulty: Optional[str] = Query(default=None),
    db: Database = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    query: Dict[str, Any] = {"user_id": current_user.id}
    if pool == "revision" or only_revision or status == "Needs Revision":
        query["status"] = "Needs Revision"
    elif pool in ("not_revised", "unrevised", "unflagged"):
        query["status"] = {"$ne": "Needs Revision"}
    elif status:
        query["status"] = status
    if difficulty and difficulty != "all":
        query["difficulty"] = difficulty
    pipeline = [{"$match": query}, {"$sample": {"size": count}}, {"$project": LIST_PROJECTION}]
    try:
        docs = list(db.questions.aggregate(pipeline))
    except Exception:  # $sample unsupported (e.g. in-memory test db)
        import random
        all_docs = list(db.questions.find(query, LIST_PROJECTION))
        docs = random.sample(all_docs, min(count, len(all_docs)))
    paths = FolderPaths.for_user(db, current_user.id)
    bm = bookmarked_ids(db, current_user.id)
    return [to_list_item(q, bm, paths) for q in docs]


@router.get("/{question_id}", response_model=QuestionResponse)
def get_question(question_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    q = get_owned_question(db, current_user.id, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    return to_response(db, q, current_user.id)


@router.post("/", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
def create_question(q_in: QuestionCreate, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    folder_id = _resolve_folder(db, current_user.id, q_in.folder_id)
    position = q_in.position if q_in.position is not None else next_position(
        db, "questions", {"user_id": current_user.id, "folder_id": folder_id}
    )
    url = (q_in.problem_url or "").strip()
    doc = new_question_doc(
        current_user.id,
        folder_id=folder_id,
        title=q_in.title.strip(),
        problem_url=url,
        problem_statement=q_in.problem_statement or "",
        notes=q_in.notes or "",
        difficulty=q_in.difficulty or "Medium",
        tags=q_in.tags or [],
        position=position,
        leetcode_slug=slug_from_url(url),
    )
    initial_status = q_in.status or "Not Started"
    if initial_status != "Not Started":
        updates: Dict[str, Any] = {}
        apply_status(db, current_user.id, doc, initial_status, updates)
        doc.update(updates)
    db.questions.insert_one(doc)
    return to_response(db, doc, current_user.id)


@router.post("/bulk", response_model=BulkActionResponse)
def bulk_action(body: BulkAction, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    uid = current_user.id
    owned = list(db.questions.find({"user_id": uid, "id": {"$in": list(dict.fromkeys(body.question_ids))}}, {"_id": 0}))
    ids = [q["id"] for q in owned]
    now = now_iso()
    if not ids:
        raise HTTPException(status_code=404, detail="None of the selected questions were found")
    a = body.action
    if a == "delete":
        return BulkActionResponse(action=a, updated=len(ids), trash_id=trash_questions(db, uid, ids))
    if a == "move":
        target = _resolve_folder(db, uid, body.folder_id)
        start = next_position(db, "questions", {"user_id": uid, "folder_id": target})
        bulk_update(db.questions, [
            ({"id": qid, "user_id": uid}, {"$set": {"folder_id": target, "position": start + i, "updated_at": now}})
            for i, qid in enumerate(ids)
        ])
    elif a == "set_status":
        if not body.status:
            raise HTTPException(status_code=422, detail="status is required")
        ops = []
        for q in owned:
            updates: Dict[str, Any] = {"updated_at": now}
            apply_status(db, uid, q, body.status, updates)
            ops.append(({"id": q["id"], "user_id": uid}, {"$set": updates}))
        if ops:
            bulk_update(db.questions, ops)
    elif a == "set_difficulty":
        if not body.difficulty:
            raise HTTPException(status_code=422, detail="difficulty is required")
        db.questions.update_many({"user_id": uid, "id": {"$in": ids}}, {"$set": {"difficulty": body.difficulty, "updated_at": now}})
    elif a in ("add_tags", "remove_tags"):
        if not body.tags:
            raise HTTPException(status_code=422, detail="tags are required")
        ops = []
        for q in owned:
            tags = parse_tags(q.get("tags"))
            if a == "add_tags":
                tags = (tags + [t for t in body.tags if t not in tags])[:30]
            else:
                tags = [t for t in tags if t not in body.tags]
            ops.append(({"id": q["id"], "user_id": uid}, {"$set": {"tags": tags, "updated_at": now}}))
        if ops:
            bulk_update(db.questions, ops)
    elif a == "bookmark":
        existing = bookmarked_ids(db, uid)
        new = [{"id": new_id(), "user_id": uid, "question_id": qid, "created_at": now} for qid in ids if qid not in existing]
        if new:
            db.bookmarks.insert_many(new)
    elif a == "unbookmark":
        db.bookmarks.delete_many({"user_id": uid, "question_id": {"$in": ids}})
    return BulkActionResponse(action=a, updated=len(ids))


@router.post("/reorder")
def reorder_questions(items: List[ReorderItem], db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    now = now_iso()
    # One round trip instead of up to 2000 sequential updates.
    ops = [
        ({"id": item.id, "user_id": current_user.id}, {"$set": {"position": item.position, "updated_at": now}})
        for item in items[:2000]
    ]
    if ops:
        bulk_update(db.questions, ops)
    return {"message": "Questions reordered successfully"}


@router.put("/{question_id}", response_model=QuestionResponse)
def update_question(question_id: str, q_in: QuestionUpdate, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    q = get_owned_question(db, current_user.id, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    updates: Dict[str, Any] = {}
    if q_in.title is not None:
        updates["title"] = q_in.title.strip()
    if q_in.problem_url is not None:
        url = q_in.problem_url.strip()
        updates["problem_url"] = url
        # The LeetCode link follows the URL: a new or cleared URL must not keep the old problem's
        # slug, or refresh/sync/import would act on the wrong problem.
        slug = slug_from_url(url) or None
        if slug != q.get("leetcode_slug"):
            updates["leetcode_slug"] = slug
            updates["leetcode_id"] = None
    if q_in.folder_id is not None:
        updates["folder_id"] = _resolve_folder(db, current_user.id, q_in.folder_id)
    if q_in.problem_statement is not None:
        updates["problem_statement"] = q_in.problem_statement
    if q_in.notes is not None:
        updates["notes"] = q_in.notes
    if q_in.difficulty is not None:
        updates["difficulty"] = q_in.difficulty
    if q_in.tags is not None:
        updates["tags"] = q_in.tags
    if q_in.position is not None:
        updates["position"] = q_in.position
    if q_in.status is not None:
        apply_status(db, current_user.id, q, q_in.status, updates)

    if updates:
        updates["updated_at"] = now_iso()
        db.questions.update_one({"id": question_id, "user_id": current_user.id}, {"$set": updates})
        q.update(updates)
    return to_response(db, q, current_user.id)


@router.post("/{question_id}/attempt", response_model=QuestionResponse)
def log_attempt(question_id: str, body: AttemptLog, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    q = get_owned_question(db, current_user.id, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    updates: Dict[str, Any] = {
        "attempts": int(q.get("attempts") or 0) + 1,
        "time_spent_minutes": int(q.get("time_spent_minutes") or 0) + body.minutes,
        "updated_at": now_iso(),
    }
    if body.solved:
        apply_status(db, current_user.id, q, "Solved", updates)
    elif (q.get("status") or "Not Started") == "Not Started":
        updates["status"] = "In Progress"
    record_activity(db, current_user.id, "attempt", question_id, minutes=body.minutes)
    db.questions.update_one({"id": question_id, "user_id": current_user.id}, {"$set": updates})
    q.update(updates)
    return to_response(db, q, current_user.id)


@router.post("/{question_id}/move")
def move_question(question_id: str, move_in: QuestionMove, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    q = get_owned_question(db, current_user.id, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    target = _resolve_folder(db, current_user.id, move_in.target_folder_id)
    updates: Dict[str, Any] = {"folder_id": target, "updated_at": now_iso()}
    updates["position"] = move_in.new_position if move_in.new_position is not None else next_position(
        db, "questions", {"user_id": current_user.id, "folder_id": target}
    )
    db.questions.update_one({"id": question_id, "user_id": current_user.id}, {"$set": updates})
    return {"message": "Question moved successfully", "question_id": question_id, "folder_id": target}


@router.delete("/{question_id}")
def delete_question(question_id: str, db: Database = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    q = get_owned_question(db, current_user.id, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    trash_id = trash_questions(db, current_user.id, [question_id])
    return {"message": "Question moved to trash", "id": question_id, "trash_id": trash_id}
