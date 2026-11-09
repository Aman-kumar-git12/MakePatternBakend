"""MongoDB access layer. MongoDB is the single source of truth for all data."""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import pymongo
from fastapi import HTTPException
from pymongo.database import Database

from app.config import settings

logger = logging.getLogger("makepattern.db")

_client: Optional[pymongo.MongoClient] = None
_override_db: Optional[Database] = None  # used by tests (mongomock)

EPOCH_ISO = "1970-01-01T00:00:00.000000+00:00"


def set_database_override(db: Optional[Database]) -> None:
    """Point the app at a different database (tests use mongomock)."""
    global _override_db
    _override_db = db


def _connect() -> pymongo.MongoClient:
    uri = settings.mongo_connection_uri
    if not uri:
        raise RuntimeError("MONGODB_URI is not configured.")
    kwargs: Dict[str, Any] = {
        "serverSelectionTimeoutMS": 5000,
        "connectTimeoutMS": 5000,
        "socketTimeoutMS": 15000,
        "maxPoolSize": 20,
        "retryWrites": True,
    }
    try:
        import certifi

        if uri.startswith("mongodb+srv") or "tls=true" in uri.lower() or "ssl=true" in uri.lower():
            kwargs["tlsCAFile"] = certifi.where()
    except ImportError:
        pass
    return pymongo.MongoClient(uri, **kwargs)


def get_database() -> Database:
    global _client
    if _override_db is not None:
        return _override_db
    if _client is None:
        _client = _connect()
    return _client[settings.MONGODB_DB_NAME]


def get_db() -> Database:
    """FastAPI dependency."""
    try:
        return get_database()
    except Exception as e:  # pragma: no cover - only when misconfigured
        logger.error("Database unavailable: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable. Please try again shortly.")


def bulk_update(collection, pairs) -> None:
    """Apply many (filter, update) pairs in one round trip. mongomock (tests) can't run
    pymongo's UpdateOne in bulk_write, so it gets the equivalent sequential updates."""
    pairs = list(pairs)
    if not pairs:
        return
    if type(collection).__module__.startswith("mongomock"):
        for flt, upd in pairs:
            collection.update_one(flt, upd)
        return
    from pymongo import UpdateOne

    collection.bulk_write([UpdateOne(flt, upd) for flt, upd in pairs], ordered=False)


def _ensure_activity_client_id_unique(db) -> None:
    """Offline reviews are idempotent per (user_id, client_id). The old index was not unique, so
    replace it; if existing data has duplicates, keep running with the app-level check."""
    try:
        if "activity_client_id_idx" in db.activity.index_information():
            db.activity.drop_index("activity_client_id_idx")
    except Exception as e:  # pragma: no cover
        logger.warning("Could not drop old activity client_id index: %s", e)
    try:
        db.activity.create_index(
            [("user_id", 1), ("client_id", 1)],
            name="activity_client_id_unique",
            unique=True,
            partialFilterExpression={"client_id": {"$exists": True}},
        )
    except Exception as e:  # pragma: no cover - duplicates already in production data
        logger.warning("Unique activity client_id index not created (existing duplicates?): %s", e)


def ping() -> bool:
    try:
        db = get_database()
        db.command("ping")
        return True
    except Exception:
        return False


def init_indexes(db: Database) -> None:
    db.users.create_index("email", unique=True, name="unique_email_idx")
    db.users.create_index("id", name="user_id_idx")
    db.users.create_index("shared_patterns.share_id", unique=True, sparse=True, name="unique_share_id_idx")
    db.folders.create_index("id", unique=True, name="unique_folder_id_idx")
    db.folders.create_index("user_id", name="folder_user_id_idx")
    db.folders.create_index("parent_id", name="folder_parent_id_idx")
    db.questions.create_index("id", unique=True, name="unique_question_id_idx")
    db.questions.create_index("user_id", name="question_user_id_idx")
    db.questions.create_index("folder_id", name="question_folder_id_idx")
    db.questions.create_index([("user_id", 1), ("leetcode_slug", 1)], name="question_user_slug_idx")
    db.questions.create_index([("user_id", 1), ("next_review_at", 1)], name="question_user_review_idx")
    db.solutions.create_index("id", unique=True, name="unique_solution_id_idx")
    db.solutions.create_index("question_id", name="solution_question_id_idx")
    db.test_cases.create_index("id", unique=True, name="unique_test_case_id_idx")
    db.test_cases.create_index("question_id", name="test_case_question_id_idx")
    db.bookmarks.create_index("id", unique=True, name="unique_bookmark_id_idx")
    db.bookmarks.create_index([("user_id", 1), ("question_id", 1)], unique=True, name="unique_user_question_bookmark_idx")
    db.share_snapshots.create_index("share_id", unique=True, name="unique_snapshot_share_id")
    db.share_snapshots.create_index([("user_id", 1), ("folder_id", 1)], name="snapshot_user_folder_idx")
    db.activity.create_index([("user_id", 1), ("at", 1)], name="activity_user_at_idx")
    _ensure_activity_client_id_unique(db)
    db.trash.create_index("id", unique=True, name="unique_trash_id_idx")
    db.trash.create_index([("user_id", 1), ("deleted_at", -1)], name="trash_user_idx")
    db.trash.create_index("expires_at", expireAfterSeconds=0, name="trash_ttl_idx")


# ---------------------------------------------------------------------------
# Small helpers shared by routers/services
# ---------------------------------------------------------------------------

def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def now_iso() -> str:
    return to_iso(now_utc())


def parse_dt(value: Any) -> Optional[datetime]:
    """Parse an ISO string / datetime stored in Mongo into an aware UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def ts(doc: Dict[str, Any], key: str) -> datetime:
    """Timestamp that is always present (legacy docs may miss created_at)."""
    return parse_dt(doc.get(key)) or parse_dt(doc.get("created_at")) or parse_dt(EPOCH_ISO)  # type: ignore[return-value]


def parse_tags(value: Any) -> List[str]:
    """Tags were historically stored as JSON strings; new docs store lists."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(t) for t in value if t is not None and str(t).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(t) for t in parsed if t is not None and str(t).strip()]
            return [str(parsed)]
        except (ValueError, TypeError):
            return [value]
    return []


def strip_mongo_id(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


def ids_of(docs: Iterable[Dict[str, Any]]) -> List[str]:
    return [d["id"] for d in docs if d.get("id")]
