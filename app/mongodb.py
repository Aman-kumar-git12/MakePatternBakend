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

def get_mongo_client() -> Optional[pymongo.MongoClient]:
    global _mongo_client
    if _mongo_client is None:
        try:
            _mongo_client = pymongo.MongoClient(
                settings.MONGODB_URL,
                serverSelectionTimeoutMS=2000
            )
            # Ping to verify active connection
            _mongo_client.admin.command('ping')
            logger.info("Successfully connected to MongoDB.")
        except Exception as e:
            logger.warning(f"MongoDB connection attempt failed: {e}. Falling back gracefully.")
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

