import logging
import secrets
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import pymongo
from pymongo.collection import Collection
from pymongo.database import Database
from app.config import settings

logger = logging.getLogger("dsa_tracker.mongodb")

_mongo_client: Optional[pymongo.MongoClient] = None

try:
    import certifi
    _CA_FILE = certifi.where()
except Exception:
    _CA_FILE = None

_last_mongo_error: Optional[str] = None

def get_last_mongo_error() -> Optional[str]:
    return _last_mongo_error

def get_mongo_client() -> Optional[pymongo.MongoClient]:
    global _mongo_client, _last_mongo_error
    if _mongo_client is None:
        try:
            mongo_uri = settings.mongo_connection_uri
            client_kwargs: Dict[str, Any] = {
                "serverSelectionTimeoutMS": 4000,
                "connectTimeoutMS": 4000,
                "socketTimeoutMS": 5000,
                "maxPoolSize": 20,
                "minPoolSize": 1,
                "maxIdleTimeMS": 45000,
            }
            if _CA_FILE and ("mongodb+srv" in mongo_uri or "ssl=true" in mongo_uri.lower() or "tls=true" in mongo_uri.lower()):
                client_kwargs["tlsCAFile"] = _CA_FILE

            _mongo_client = pymongo.MongoClient(
                mongo_uri,
                **client_kwargs
            )
            # Ping to verify active connection
            _mongo_client.admin.command('ping')
            _last_mongo_error = None
            logger.info("Successfully connected to MongoDB.")
        except Exception as e:
            logger.warning(f"MongoDB connection attempt with tlsCAFile failed: {e}. Trying fallback connection...")
            try:
                fallback_kwargs = {
                    "serverSelectionTimeoutMS": 5000,
                    "connectTimeoutMS": 5000,
                    "socketTimeoutMS": 10000,
                    "tlsAllowInvalidCertificates": True,
                }
                _mongo_client = pymongo.MongoClient(mongo_uri, **fallback_kwargs)
                _mongo_client.admin.command('ping')
                _last_mongo_error = None
                logger.info("Successfully connected to MongoDB via fallback.")
            except Exception as e2:
                _last_mongo_error = f"Fallback error: {type(e2).__name__}: {str(e2)} | Initial error: {type(e).__name__}: {str(e)}"
                logger.error(f"MongoDB connection failed completely: {_last_mongo_error}")
                _mongo_client = None
    return _mongo_client

def get_mongo_db() -> Optional[Database]:
    client = get_mongo_client()
    if client is not None:
        return client[settings.MONGODB_DB_NAME]
    return None

def get_users_collection() -> Optional[Collection]:
    db = get_mongo_db()
    if db is not None:
        return db["users"]
    return None

def get_folders_collection() -> Optional[Collection]:
    db = get_mongo_db()
    if db is not None:
        return db["folders"]
    return None

def get_questions_collection() -> Optional[Collection]:
    db = get_mongo_db()
    if db is not None:
        return db["questions"]
    return None

def get_solutions_collection() -> Optional[Collection]:
    db = get_mongo_db()
    if db is not None:
        return db["solutions"]
    return None

def get_test_cases_collection() -> Optional[Collection]:
    db = get_mongo_db()
    if db is not None:
        return db["test_cases"]
    return None

def get_bookmarks_collection() -> Optional[Collection]:
    db = get_mongo_db()
    if db is not None:
        return db["bookmarks"]
    return None

def init_mongodb():
    """
    Initializes MongoDB users collection, applies schema validation,
    and creates unique indexes on email and shared_patterns.share_id.
    """
    db = get_mongo_db()
    if db is None:
        logger.warning("MongoDB not available at init time; proceeding without blocking.")
        return

    try:
        collections = db.list_collection_names()
        user_schema_validator = {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["email", "hashed_password"],
                "properties": {
                    "email": {
                        "bsonType": "string",
                        "pattern": "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$",
                        "description": "must be a valid email string and is required"
                    },
                    "hashed_password": {
                        "bsonType": "string",
                        "description": "must be a string containing hashed password and is required"
                    },
                    "full_name": {
                        "bsonType": "string",
                        "description": "optional user full name"
                    },
                    "created_at": {
                        "bsonType": ["date", "string"],
                        "description": "timestamp of creation"
                    },
                    "shared_patterns": {
                        "bsonType": "array",
                        "description": "array of shareable pattern settings",
                        "items": {
                            "bsonType": "object",
                            "required": ["share_id", "folder_id", "is_active"],
                            "properties": {
                                "share_id": {
                                    "bsonType": "string",
                                    "description": "unique share token"
                                },
                                "folder_id": {
                                    "bsonType": "string",
                                    "description": "id of the pattern folder being shared"
                                },
                                "folder_name": {
                                    "bsonType": "string",
                                    "description": "cached display name of the folder"
                                },
                                "is_active": {
                                    "bsonType": "bool",
                                    "description": "whether sharing is currently enabled"
                                },
                                "created_at": {
                                    "bsonType": "string",
                                    "description": "timestamp when share was generated"
                                },
                                "updated_at": {
                                    "bsonType": "string",
                                    "description": "timestamp when share was modified"
                                }
                            }
                        }
                    }
                }
            }
        }

        if "users" not in collections:
            db.create_collection("users", validator=user_schema_validator)
            logger.info("Created MongoDB 'users' collection with schema validation.")
        else:
            try:
                db.command("collMod", "users", validator=user_schema_validator)
            except Exception as e:
                logger.debug(f"collMod note: {e}")

        # Ensure unique index on email field
        db.users.create_index("email", unique=True, name="unique_email_idx")
        logger.info("MongoDB unique index on users.email verified successfully.")

        # Ensure unique index on shared_patterns.share_id
        db.users.create_index("shared_patterns.share_id", unique=True, sparse=True, name="unique_share_id_idx")
        logger.info("MongoDB unique index on shared_patterns.share_id verified successfully.")

        # Ensure indexes on folders collection
        db.folders.create_index("id", unique=True, name="unique_folder_id_idx")
        db.folders.create_index("user_id", name="folder_user_id_idx")
        db.folders.create_index("parent_id", name="folder_parent_id_idx")

        # Ensure indexes on questions collection
        db.questions.create_index("id", unique=True, name="unique_question_id_idx")
        db.questions.create_index("user_id", name="question_user_id_idx")
        db.questions.create_index("folder_id", name="question_folder_id_idx")

        # Ensure indexes on solutions collection
        db.solutions.create_index("id", unique=True, name="unique_solution_id_idx")
        db.solutions.create_index("question_id", name="solution_question_id_idx")

        # Ensure indexes on test_cases collection
        db.test_cases.create_index("id", unique=True, name="unique_test_case_id_idx")
        db.test_cases.create_index("question_id", name="test_case_question_id_idx")

        # Ensure indexes on bookmarks collection
        db.bookmarks.create_index("id", unique=True, name="unique_bookmark_id_idx")
        db.bookmarks.create_index([("user_id", 1), ("question_id", 1)], unique=True, name="unique_user_question_bookmark_idx")
        logger.info("MongoDB indexes for folders, questions, solutions, test_cases, and bookmarks verified successfully.")
    except Exception as e:
        logger.error(f"Error initializing MongoDB collection or index: {e}", exc_info=True)

def find_user_by_email_mongo(email: str) -> Optional[Dict[str, Any]]:
    coll = get_users_collection()
    if coll is not None:
        return coll.find_one({"email": email.strip().lower()})
    return None

def find_user_by_id_mongo(user_id: str) -> Optional[Dict[str, Any]]:
    coll = get_users_collection()
    if coll is not None:
        return coll.find_one({"$or": [{"id": user_id}, {"_id": user_id}]})
    return None

def save_user_mongo(user_id: str, email: str, full_name: str, hashed_password: str) -> bool:
    """
    Persistently stores user into MongoDB with unique email validation.
    """
    coll = get_users_collection()
    if coll is None:
        return False

    normalized_email = email.strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    user_doc = {
        "id": user_id,
        "email": normalized_email,
        "full_name": full_name or "Aman Kumar",
        "hashed_password": hashed_password,
        "created_at": now_iso,
        "updated_at": now_iso
    }
    
    # Update or insert without overwriting shared_patterns if already set
    coll.update_one(
        {"$or": [{"id": user_id}, {"_id": user_id}]},
        {
            "$set": user_doc,
            "$setOnInsert": {"shared_patterns": []}
        },
        upsert=True
    )
    return True

def sync_all_sqlite_users_to_mongo(users: List[Any]) -> None:
    """Ensures every existing user from SQLite is registered in MongoDB."""
    coll = get_users_collection()
    if coll is None:
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    for u in users:
        try:
            normalized_email = (u.email or "").strip().lower()
            if not normalized_email:
                continue
            existing = coll.find_one({"$or": [{"id": u.id}, {"_id": u.id}, {"email": normalized_email}]})
            if not existing:
                coll.update_one(
                    {"_id": u.id},
                    {
                        "$set": {
                            "id": u.id,
                            "email": normalized_email,
                            "full_name": getattr(u, "full_name", "") or "Aman Kumar",
                            "hashed_password": getattr(u, "hashed_password", "") or "hashed_pwd_synced",
                            "created_at": getattr(u, "created_at", None).isoformat() if getattr(u, "created_at", None) else now_iso,
                            "updated_at": now_iso,
                        },
                        "$setOnInsert": {"shared_patterns": []}
                    },
                    upsert=True
                )
        except Exception as e:
            logger.warning(f"Error syncing user {getattr(u, 'id', None)} to MongoDB: {e}")

# =========================================================================
# Folders, Questions, Solutions, TestCases & Bookmarks Sync & CRUD Helpers
# =========================================================================

def folder_to_mongo_dict(f: Any) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(getattr(f, "id", "")),
        "user_id": str(getattr(f, "user_id", "")),
        "parent_id": str(getattr(f, "parent_id", "")) if getattr(f, "parent_id", None) else None,
        "name": getattr(f, "name", ""),
        "description": getattr(f, "description", "") or "",
        "tags": getattr(f, "tags", "[]") or "[]",
        "position": getattr(f, "position", 0) or 0,
        "created_at": getattr(f, "created_at", None).isoformat() if getattr(f, "created_at", None) else now_iso,
        "updated_at": getattr(f, "updated_at", None).isoformat() if getattr(f, "updated_at", None) else now_iso,
    }

def save_folder_mongo(folder: Any) -> bool:
    try:
        coll = get_folders_collection()
        if coll is None:
            return False
        doc = folder_to_mongo_dict(folder) if hasattr(folder, "id") else folder
        coll.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
        return True
    except Exception as e:
        logger.warning(f"Error saving folder to MongoDB: {e}")
        return False

def bulk_save_folders_mongo(folders: List[Any]) -> bool:
    try:
        coll = get_folders_collection()
        if coll is None or not folders:
            return False
        operations = []
        for f in folders:
            doc = folder_to_mongo_dict(f) if hasattr(f, "id") else f
            operations.append(pymongo.UpdateOne({"id": doc["id"]}, {"$set": doc}, upsert=True))
        if operations:
            coll.bulk_write(operations, ordered=False)
        return True
    except Exception as e:
        logger.warning(f"Error bulk saving folders to MongoDB: {e}")
        return False

def delete_folder_mongo(folder_id: str, descendant_ids: Optional[List[str]] = None) -> bool:
    try:
        db = get_mongo_db()
        if db is None:
            return False
        target_ids = [folder_id]
        if descendant_ids:
            target_ids.extend(descendant_ids)
        target_ids = list(set(target_ids))

        # Find questions under these folders to delete associated items
        qs = list(db.questions.find({"folder_id": {"$in": target_ids}}, {"id": 1}))
        q_ids = [q["id"] for q in qs]

        db.folders.delete_many({"id": {"$in": target_ids}})
        if q_ids:
            db.questions.delete_many({"id": {"$in": q_ids}})
            db.solutions.delete_many({"question_id": {"$in": q_ids}})
            db.test_cases.delete_many({"question_id": {"$in": q_ids}})
            db.bookmarks.delete_many({"question_id": {"$in": q_ids}})
        return True
    except Exception as e:
        logger.warning(f"Error deleting folder from MongoDB: {e}")
        return False

def question_to_mongo_dict(q: Any) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(getattr(q, "id", "")),
        "user_id": str(getattr(q, "user_id", "")),
        "folder_id": str(getattr(q, "folder_id", "")) if getattr(q, "folder_id", None) else None,
        "title": getattr(q, "title", ""),
        "problem_url": getattr(q, "problem_url", "") or "",
        "problem_statement": getattr(q, "problem_statement", "") or "",
        "notes": getattr(q, "notes", "") or "",
        "difficulty": getattr(q, "difficulty", "Medium") or "Medium",
        "status": getattr(q, "status", "Not Started") or "Not Started",
        "tags": getattr(q, "tags", "[]") or "[]",
        "position": getattr(q, "position", 0) or 0,
        "created_at": getattr(q, "created_at", None).isoformat() if getattr(q, "created_at", None) else now_iso,
        "updated_at": getattr(q, "updated_at", None).isoformat() if getattr(q, "updated_at", None) else now_iso,
    }

def save_question_mongo(question: Any) -> bool:
    try:
        coll = get_questions_collection()
        if coll is None:
            return False
        doc = question_to_mongo_dict(question) if hasattr(question, "id") else question
        coll.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
        return True
    except Exception as e:
        logger.warning(f"Error saving question to MongoDB: {e}")
        return False

def bulk_save_questions_mongo(questions: List[Any]) -> bool:
    try:
        coll = get_questions_collection()
        if coll is None or not questions:
            return False
        operations = []
        for q in questions:
            doc = question_to_mongo_dict(q) if hasattr(q, "id") else q
            operations.append(pymongo.UpdateOne({"id": doc["id"]}, {"$set": doc}, upsert=True))
        if operations:
            coll.bulk_write(operations, ordered=False)
        return True
    except Exception as e:
        logger.warning(f"Error bulk saving questions to MongoDB: {e}")
        return False

def delete_question_mongo(question_id: str) -> bool:
    try:
        db = get_mongo_db()
        if db is None:
            return False
        db.questions.delete_one({"id": question_id})
        db.solutions.delete_many({"question_id": question_id})
        db.test_cases.delete_many({"question_id": question_id})
        db.bookmarks.delete_many({"question_id": question_id})
        return True
    except Exception as e:
        logger.warning(f"Error deleting question from MongoDB: {e}")
        return False

def solution_to_mongo_dict(s: Any) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(getattr(s, "id", "")),
        "question_id": str(getattr(s, "question_id", "")),
        "title": getattr(s, "title", "Solution") or "Solution",
        "solution_type": getattr(s, "solution_type", "Optimized") or "Optimized",
        "language": getattr(s, "language", "cpp") or "cpp",
        "code": getattr(s, "code", "") or "",
        "explanation": getattr(s, "explanation", "") or "",
        "time_complexity": getattr(s, "time_complexity", "") or "",
        "space_complexity": getattr(s, "space_complexity", "") or "",
        "position": getattr(s, "position", 0) or 0,
        "created_at": getattr(s, "created_at", None).isoformat() if getattr(s, "created_at", None) else now_iso,
        "updated_at": getattr(s, "updated_at", None).isoformat() if getattr(s, "updated_at", None) else now_iso,
    }

def save_solution_mongo(solution: Any) -> bool:
    try:
        coll = get_solutions_collection()
        if coll is None:
            return False
        doc = solution_to_mongo_dict(solution) if hasattr(solution, "id") else solution
        coll.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
        return True
    except Exception as e:
        logger.warning(f"Error saving solution to MongoDB: {e}")
        return False

def delete_solution_mongo(solution_id: str) -> bool:
    try:
        coll = get_solutions_collection()
        if coll is None:
            return False
        coll.delete_one({"id": solution_id})
        return True
    except Exception as e:
        logger.warning(f"Error deleting solution from MongoDB: {e}")
        return False

def test_case_to_mongo_dict(tc: Any) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(getattr(tc, "id", "")),
        "question_id": str(getattr(tc, "question_id", "")),
        "title": getattr(tc, "title", "Test Case") or "Test Case",
        "input": getattr(tc, "input", "") or "",
        "expected_output": getattr(tc, "expected_output", "") or "",
        "notes": getattr(tc, "notes", "") or "",
        "position": getattr(tc, "position", 0) or 0,
        "created_at": getattr(tc, "created_at", None).isoformat() if getattr(tc, "created_at", None) else now_iso,
        "updated_at": getattr(tc, "updated_at", None).isoformat() if getattr(tc, "updated_at", None) else now_iso,
    }

def save_test_case_mongo(test_case: Any) -> bool:
    try:
        coll = get_test_cases_collection()
        if coll is None:
            return False
        doc = test_case_to_mongo_dict(test_case) if hasattr(test_case, "id") else test_case
        coll.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
        return True
    except Exception as e:
        logger.warning(f"Error saving test case to MongoDB: {e}")
        return False

def delete_test_case_mongo(test_case_id: str) -> bool:
    try:
        coll = get_test_cases_collection()
        if coll is None:
            return False
        coll.delete_one({"id": test_case_id})
        return True
    except Exception as e:
        logger.warning(f"Error deleting test case from MongoDB: {e}")
        return False

def bookmark_to_mongo_dict(b: Any) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(getattr(b, "id", "")),
        "user_id": str(getattr(b, "user_id", "")),
        "question_id": str(getattr(b, "question_id", "")),
        "created_at": getattr(b, "created_at", None).isoformat() if getattr(b, "created_at", None) else now_iso,
    }

def save_bookmark_mongo(bookmark: Any) -> bool:
    try:
        coll = get_bookmarks_collection()
        if coll is None:
            return False
        doc = bookmark_to_mongo_dict(bookmark) if hasattr(bookmark, "id") else bookmark
        coll.update_one(
            {"user_id": doc["user_id"], "question_id": doc["question_id"]},
            {"$set": doc},
            upsert=True
        )
        return True
    except Exception as e:
        logger.warning(f"Error saving bookmark to MongoDB: {e}")
        return False

def delete_bookmark_mongo(bookmark_id: Optional[str] = None, user_id: Optional[str] = None, question_id: Optional[str] = None) -> bool:
    try:
        coll = get_bookmarks_collection()
        if coll is None:
            return False
        query = {}
        if bookmark_id:
            query["id"] = bookmark_id
        if user_id:
            query["user_id"] = user_id
        if question_id:
            query["question_id"] = question_id
        if not query:
            return False
        coll.delete_one(query)
        return True
    except Exception as e:
        logger.warning(f"Error deleting bookmark from MongoDB: {e}")
        return False

def sync_all_sqlite_data_to_mongo(db: Any) -> Dict[str, int]:
    """
    Synchronizes all data from SQLite (users, folders, questions, solutions,
    test_cases, bookmarks) into MongoDB collections.
    """
    from app.models.user import User as SqlUser
    from app.models.folder import Folder as SqlFolder
    from app.models.question import Question as SqlQuestion
    from app.models.solution import Solution as SqlSolution
    from app.models.test_case import TestCase as SqlTestCase
    from app.models.bookmark import Bookmark as SqlBookmark

    stats = {"users": 0, "folders": 0, "questions": 0, "solutions": 0, "test_cases": 0, "bookmarks": 0}

    # 1. Users
    users = db.query(SqlUser).all()
    sync_all_sqlite_users_to_mongo(users)
    stats["users"] = len(users)

    # 2. Folders
    folders = db.query(SqlFolder).all()
    bulk_save_folders_mongo(folders)
    stats["folders"] = len(folders)

    # 3. Questions
    questions = db.query(SqlQuestion).all()
    bulk_save_questions_mongo(questions)
    stats["questions"] = len(questions)

    # 4. Solutions
    solutions = db.query(SqlSolution).all()
    for s in solutions:
        save_solution_mongo(s)
    stats["solutions"] = len(solutions)

    # 5. TestCases
    test_cases = db.query(SqlTestCase).all()
    for tc in test_cases:
        save_test_case_mongo(tc)
    stats["test_cases"] = len(test_cases)

    # 6. Bookmarks
    bookmarks = db.query(SqlBookmark).all()
    for b in bookmarks:
        save_bookmark_mongo(b)
    stats["bookmarks"] = len(bookmarks)

    logger.info(f"MongoDB Full Synchronization Complete: {stats}")
    return stats

def restore_all_data_from_mongo_to_sqlite(db: Any) -> Dict[str, int]:
    """
    If SQLite database is empty (e.g. running on Render's ephemeral filesystem or clean deploy),
    automatically restores all users, folders, questions, solutions, test cases, and bookmarks
    directly from MongoDB Atlas. This ensures MongoDB Atlas is the true, permanent cloud database.
    """
    from app.models.user import User as SqlUser
    from app.models.folder import Folder as SqlFolder
    from app.models.question import Question as SqlQuestion
    from app.models.solution import Solution as SqlSolution
    from app.models.test_case import TestCase as SqlTestCase
    from app.models.bookmark import Bookmark as SqlBookmark

    mongo_db = get_mongo_db()
    if mongo_db is None:
        logger.warning("MongoDB not connected; skipping restore.")
        return {}

    stats = {"users": 0, "folders": 0, "questions": 0, "solutions": 0, "test_cases": 0, "bookmarks": 0}

    logger.info("Restoring users, folders, questions, and curriculum from MongoDB Atlas...")

    # 1. Restore Users
    mongo_users = list(mongo_db.users.find({}))
    for u in mongo_users:
        uid = u.get("id") or str(u.get("_id"))
        email = u.get("email")
        if not email:
            continue
        
        # Reconcile if local SQLite has this email under a different id
        existing_local = db.query(SqlUser).filter(SqlUser.email == email).first()
        if existing_local and existing_local.id != uid:
            # Delete conflicting local user and orphan records
            db.query(SqlFolder).filter(SqlFolder.user_id == existing_local.id).delete()
            db.query(SqlQuestion).filter(SqlQuestion.user_id == existing_local.id).delete()
            db.delete(existing_local)
            db.commit()

        sql_u = SqlUser(
            id=uid,
            email=email,
            hashed_password=u.get("hashed_password"),
            full_name=u.get("full_name") or "Aman Kumar",
        )
        db.merge(sql_u)
        stats["users"] += 1
    db.commit()

    # 2. Restore Folders
    mongo_folders = list(mongo_db.folders.find({}))
    def folder_depth(f):
        d = 0
        pid = f.get("parent_id")
        visited = set()
        while pid and pid not in visited:
            visited.add(pid)
            parent = mongo_db.folders.find_one({"id": pid})
            if not parent:
                break
            pid = parent.get("parent_id")
            d += 1
        return d

    mongo_folders.sort(key=folder_depth)
    for f in mongo_folders:
        sql_f = SqlFolder(
            id=f.get("id") or str(f.get("_id")),
            user_id=f.get("user_id"),
            name=f.get("name"),
            description=f.get("description", ""),
            parent_id=f.get("parent_id"),
            position=f.get("position", 0),
            tags=f.get("tags", []),
        )
        db.merge(sql_f)
        stats["folders"] += 1
    db.commit()

    # 3. Restore Questions
    mongo_questions = list(mongo_db.questions.find({}))
    for q in mongo_questions:
        sql_q = SqlQuestion(
            id=q.get("id") or str(q.get("_id")),
            user_id=q.get("user_id"),
            folder_id=q.get("folder_id"),
            title=q.get("title"),
            difficulty=q.get("difficulty", "Medium"),
            status=q.get("status", "Not Started"),
            problem_url=q.get("problem_url"),
            position=q.get("position", 0),
        )
        db.merge(sql_q)
        stats["questions"] += 1
    db.commit()

    # 4. Restore Solutions
    mongo_solutions = list(mongo_db.solutions.find({}))
    for s in mongo_solutions:
        sql_s = SqlSolution(
            id=s.get("id") or str(s.get("_id")),
            question_id=s.get("question_id"),
            title=s.get("title") or "Optimized Approach",
            solution_type=s.get("solution_type") or s.get("approach_type") or "Optimized",
            code=s.get("code") or "",
            language=s.get("language", "cpp"),
            time_complexity=s.get("time_complexity") or "",
            space_complexity=s.get("space_complexity") or "O(1)",
            explanation=s.get("explanation") or s.get("notes") or "",
            position=s.get("position", 0),
        )
        db.merge(sql_s)
        stats["solutions"] += 1
    db.commit()

    # 5. Restore TestCases
    mongo_tc = list(mongo_db.test_cases.find({}))
    for tc in mongo_tc:
        sql_tc = SqlTestCase(
            id=tc.get("id") or str(tc.get("_id")),
            question_id=tc.get("question_id"),
            title=tc.get("title") or "Test Case",
            input=tc.get("input") or tc.get("input_data") or "",
            expected_output=tc.get("expected_output") or "",
            notes=tc.get("notes") or tc.get("explanation") or "",
            position=tc.get("position", 0),
        )
        db.merge(sql_tc)
        stats["test_cases"] += 1
    db.commit()

    # 6. Restore Bookmarks
    mongo_bm = list(mongo_db.bookmarks.find({}))
    for b in mongo_bm:
        sql_b = SqlBookmark(
            id=b.get("id") or str(b.get("_id")),
            user_id=b.get("user_id"),
            question_id=b.get("question_id"),
        )
        db.merge(sql_b)
    db.commit()

    logger.info(f"MongoDB Restore Complete: {stats}")
    return stats

def restore_user_data_from_mongo_to_sqlite(db: Session, user_id: str):
    """
    On-demand restore for a specific user's folders, questions, solutions, and bookmarks.
    """
    from app.models.folder import Folder as SqlFolder
    from app.models.question import Question as SqlQuestion
    from app.models.solution import Solution as SqlSolution
    from app.models.bookmark import Bookmark as SqlBookmark

    mongo_db = get_mongo_db()
    if mongo_db is None:
        return

    try:
        # Folders
        mongo_folders = list(mongo_db.folders.find({"user_id": user_id}))
        for f in mongo_folders:
            fid = f.get("id") or str(f.get("_id"))
            sql_f = SqlFolder(
                id=fid,
                user_id=user_id,
                name=f.get("name"),
                description=f.get("description", ""),
                parent_id=f.get("parent_id"),
                position=f.get("position", 0),
                tags=f.get("tags", []),
            )
            db.merge(sql_f)
        db.commit()

        # Questions
        mongo_questions = list(mongo_db.questions.find({"user_id": user_id}))
        q_ids = []
        for q in mongo_questions:
            qid = q.get("id") or str(q.get("_id"))
            q_ids.append(qid)
            sql_q = SqlQuestion(
                id=qid,
                user_id=user_id,
                folder_id=q.get("folder_id"),
                title=q.get("title"),
                difficulty=q.get("difficulty", "Medium"),
                status=q.get("status", "Not Started"),
                problem_url=q.get("problem_url"),
                position=q.get("position", 0),
            )
            db.merge(sql_q)
        db.commit()

        # Solutions
        if q_ids:
            mongo_solutions = list(mongo_db.solutions.find({"question_id": {"$in": q_ids}}))
            for s in mongo_solutions:
                sid = s.get("id") or str(s.get("_id"))
                sql_s = SqlSolution(
                    id=sid,
                    question_id=s.get("question_id"),
                    title=s.get("title") or "Optimized Approach",
                    solution_type=s.get("solution_type") or s.get("approach_type") or "Optimized",
                    code=s.get("code") or "",
                    language=s.get("language", "cpp"),
                    time_complexity=s.get("time_complexity") or "",
                    space_complexity=s.get("space_complexity") or "O(1)",
                    explanation=s.get("explanation") or s.get("notes") or "",
                    position=s.get("position", 0),
                )
                db.merge(sql_s)
            db.commit()

        # Bookmarks
        mongo_bm = list(mongo_db.bookmarks.find({"user_id": user_id}))
        for b in mongo_bm:
            bmid = b.get("id") or str(b.get("_id"))
            sql_b = SqlBookmark(
                id=bmid,
                user_id=user_id,
                question_id=b.get("question_id"),
            )
            db.merge(sql_b)
        db.commit()
    except Exception as e:
        logger.warning(f"Error in on-demand user data restore from Mongo: {e}")


# =========================================================================
# Pattern Sharing Persistence & Security Helpers
# =========================================================================

def generate_share_id() -> str:
    """Generates an unguessable, URL-safe random token for pattern sharing."""
    return secrets.token_urlsafe(16)

def get_share_for_folder_mongo(user_id: str, folder_id: str) -> Optional[Dict[str, Any]]:
    """Returns the sharing metadata for a specific folder owned by user."""
    coll = get_users_collection()
    if coll is None:
        return None

    user = coll.find_one(
        {"$or": [{"id": user_id}, {"_id": user_id}], "shared_patterns.folder_id": folder_id},
        {"shared_patterns.$": 1}
    )
    if user and "shared_patterns" in user and len(user["shared_patterns"]) > 0:
        return user["shared_patterns"][0]
    return None

def create_or_get_share_mongo(
    user_id: str,
    folder_id: str,
    folder_name: str,
    email: str = "",
    full_name: str = "",
    hashed_password: str = ""
) -> Dict[str, Any]:
    """
    Generates or retrieves persistent share configuration for a folder.
    Guarantees unique share_id stored in user's document in MongoDB.
    """
    coll = get_users_collection()
    if coll is None:
        raise RuntimeError("MongoDB connection is unavailable.")

    now_iso = datetime.now(timezone.utc).isoformat()

    # Ensure user document exists in MongoDB before modifying
    user_doc = coll.find_one({"$or": [{"id": user_id}, {"_id": user_id}]})
    if not user_doc:
        normalized_email = (email or f"user_{user_id[:8]}@example.com").strip().lower()
        coll.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "id": user_id,
                    "email": normalized_email,
                    "full_name": full_name or "Aman Kumar",
                    "hashed_password": hashed_password or "hashed_pwd_default",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                },
                "$setOnInsert": {"shared_patterns": []}
            },
            upsert=True
        )

    existing = get_share_for_folder_mongo(user_id, folder_id)

    if existing:
        # Re-activate if it was disabled
        if not existing.get("is_active"):
            coll.update_one(
                {"$or": [{"id": user_id}, {"_id": user_id}], "shared_patterns.folder_id": folder_id},
                {
                    "$set": {
                        "shared_patterns.$.is_active": True,
                        "shared_patterns.$.updated_at": now_iso
                    }
                }
            )
            existing["is_active"] = True
            existing["updated_at"] = now_iso
        return existing

    # Create new share entry
    share_id = generate_share_id()
    share_record = {
        "share_id": share_id,
        "folder_id": folder_id,
        "folder_name": folder_name,
        "is_active": True,
        "created_at": now_iso,
        "updated_at": now_iso
    }

    coll.update_one(
        {"$or": [{"id": user_id}, {"_id": user_id}]},
        {"$push": {"shared_patterns": share_record}}
    )
    return share_record

def update_share_status_mongo(user_id: str, folder_id: str, is_active: bool) -> Optional[Dict[str, Any]]:
    """Enables or disables sharing for an existing pattern."""
    coll = get_users_collection()
    if coll is None:
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    result = coll.update_one(
        {"$or": [{"id": user_id}, {"_id": user_id}], "shared_patterns.folder_id": folder_id},
        {
            "$set": {
                "shared_patterns.$.is_active": is_active,
                "shared_patterns.$.updated_at": now_iso
            }
        }
    )

    if result.matched_count > 0:
        return get_share_for_folder_mongo(user_id, folder_id)
    return None

def revoke_share_mongo(user_id: str, folder_id: str, regenerate_new: bool = False, folder_name: str = "") -> Optional[Dict[str, Any]]:
    """
    Revokes the existing share link.
    If regenerate_new is True, generates a completely new share_id, invalidating the old one immediately.
    If regenerate_new is False, sets is_active=False and marks revoked.
    """
    coll = get_users_collection()
    if coll is None:
        return None

    now_iso = datetime.now(timezone.utc).isoformat()

    if regenerate_new:
        new_share_id = generate_share_id()
        coll.update_one(
            {"$or": [{"id": user_id}, {"_id": user_id}], "shared_patterns.folder_id": folder_id},
            {
                "$set": {
                    "shared_patterns.$.share_id": new_share_id,
                    "shared_patterns.$.is_active": True,
                    "shared_patterns.$.updated_at": now_iso
                }
            }
        )
        return get_share_for_folder_mongo(user_id, folder_id)
    else:
        # Disable sharing
        coll.update_one(
            {"$or": [{"id": user_id}, {"_id": user_id}], "shared_patterns.folder_id": folder_id},
            {
                "$set": {
                    "shared_patterns.$.is_active": False,
                    "shared_patterns.$.updated_at": now_iso
                }
            }
        )
        return get_share_for_folder_mongo(user_id, folder_id)

def find_active_share_by_id_mongo(share_id: str) -> Optional[Dict[str, Any]]:
    """
    Public lookup: Finds the owner and share record for an active shareId.
    Enforces that is_active must be True.
    """
    coll = get_users_collection()
    if coll is None or not share_id:
        return None

    user = coll.find_one(
        {"shared_patterns.share_id": share_id, "shared_patterns.is_active": True},
        {"id": 1, "_id": 1, "full_name": 1, "shared_patterns.$": 1}
    )

    if not user or "shared_patterns" not in user or len(user["shared_patterns"]) == 0:
        return None

    share_record = user["shared_patterns"][0]
    if not share_record.get("is_active"):
        return None

    user_id = user.get("id") or str(user.get("_id"))
    return {
        "user_id": user_id,
        "owner_name": user.get("full_name") or "Aman Kumar",
        "share": share_record
    }

