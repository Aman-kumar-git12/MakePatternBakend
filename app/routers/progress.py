import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.question import Question
from app.models.folder import Folder
from app.models.bookmark import Bookmark
from app.models.user import User
from app.schemas.progress import (
    OverallProgressResponse,
    DifficultyBreakdown,
    FolderProgressItem
)
from app.schemas.question import QuestionListItem
from app.routers.auth import get_current_user
from app.services.folder_service import get_folder_path_string, get_all_descendant_folder_ids

router = APIRouter(prefix="/progress", tags=["progress"])

@router.get("/summary", response_model=OverallProgressResponse)
def get_progress_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    all_questions = db.query(Question).filter(Question.user_id == current_user.id).all()
    bookmarked_ids = {b.question_id for b in db.query(Bookmark).filter(Bookmark.user_id == current_user.id).all()}

    total_q = len(all_questions)
    solved_q = sum(1 for q in all_questions if q.status == "Solved")
    in_progress_q = sum(1 for q in all_questions if q.status == "In Progress")
    needs_revision_q = sum(1 for q in all_questions if q.status == "Needs Revision")
    not_started_q = sum(1 for q in all_questions if q.status == "Not Started")

    overall_pct = round((solved_q / total_q) * 100, 1) if total_q > 0 else 0.0

    # Difficulty breakdown
    diff_map = {
        "Easy": DifficultyBreakdown(),
        "Medium": DifficultyBreakdown(),
        "Hard": DifficultyBreakdown()
    }
    for q in all_questions:
        d = q.difficulty if q.difficulty in diff_map else "Medium"
        diff_map[d].total += 1
        if q.status == "Solved":
            diff_map[d].solved += 1

    # Priority questions matching reference screenshot: Two Sum, Merge Sort, Binary Tree Traversal, Longest Increasing Subsequence
    priority_titles = ["Two Sum", "Merge Sort", "Binary Tree Traversal", "Longest Increasing Subsequence"]
    
    # Recent questions (featured reference items first, then others)
    all_user_questions = db.query(Question).filter(Question.user_id == current_user.id).all()
    q_by_title = {q.title: q for q in all_user_questions}
    
    featured_q = [q_by_title[t] for t in priority_titles if t in q_by_title]
    remaining_recent = [q for q in all_user_questions if q.title not in priority_titles]
    recent_db_q = (featured_q + remaining_recent)[:6]

    def format_item(q: Question) -> QuestionListItem:
        tags_list = []
        try:
            tags_list = json.loads(q.tags) if q.tags else []
        except Exception:
            tags_list = [q.tags] if q.tags else []

        return QuestionListItem(
            id=q.id,
            folder_id=q.folder_id,
            title=q.title,
            difficulty=q.difficulty,
            status=q.status,
            tags=tags_list,
            is_bookmarked=(q.id in bookmarked_ids),
            folder_path=get_folder_path_string(db, q.folder_id),
            updated_at=q.updated_at
        )

    recent_items = [format_item(q) for q in recent_db_q]

    # Continue learning: priority items first, then others
    continue_q = featured_q if len(featured_q) >= 4 else (featured_q + [q for q in all_user_questions if q.status in ["In Progress", "Needs Revision", "Solved"] and q not in featured_q])[:4]
    continue_items = [format_item(q) for q in continue_q]

    # Top folders overview
    root_folders = db.query(Folder).filter(
        Folder.user_id == current_user.id,
        Folder.parent_id == None
    ).order_by(Folder.position).all()

    folder_overview = []
    # If there are subfolders under root (e.g. Arrays, Sorting under DSA), show those top subfolders
    display_folders = []
    dsa_root = next((f for f in root_folders if f.name == "DSA"), None)
    if dsa_root:
        display_folders = db.query(Folder).filter(
            Folder.parent_id == dsa_root.id
        ).order_by(Folder.position).all()
    else:
        display_folders = root_folders

    preferred_order = ["Arrays", "Sorting", "Dynamic Programming"]
    display_folders = sorted(display_folders, key=lambda f: preferred_order.index(f.name) if f.name in preferred_order else 99)

    for f in display_folders:
        sub_ids = get_all_descendant_folder_ids(db, f.id)
        all_ids = sub_ids | {f.id}

        f_questions = db.query(Question).filter(
            Question.folder_id.in_(all_ids),
            Question.user_id == current_user.id
        ).all()

        f_total = len(f_questions)
        f_solved = sum(1 for q in f_questions if q.status == "Solved")
        f_pct = round((f_solved / f_total) * 100, 1) if f_total > 0 else 0.0

        folder_overview.append(
            FolderProgressItem(
                folder_id=f.id,
                folder_name=f.name,
                total_questions=f_total,
                solved_questions=f_solved,
                progress_percentage=f_pct
            )
        )

    all_user_folders = db.query(Folder).filter(Folder.user_id == current_user.id).all()
    total_topics = sum(1 for f in all_user_folders if f.parent_id is None)
    total_subtopics = sum(1 for f in all_user_folders if f.parent_id is not None)

    return OverallProgressResponse(
        total_topics=total_topics,
        total_subtopics=total_subtopics,
        total_questions=total_q,
        solved_questions=solved_q,
        in_progress_questions=in_progress_q,
        needs_revision_questions=needs_revision_q,
        not_started_questions=not_started_q,
        overall_percentage=overall_pct,
        difficulty_breakdown=diff_map,
        recent_questions=recent_items,
        continue_learning=continue_items,
        folder_overview=folder_overview
    )
