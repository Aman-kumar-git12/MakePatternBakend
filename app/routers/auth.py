import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.db import get_db, new_id, now_iso, parse_dt, strip_mongo_id, EPOCH_ISO
from app.schemas.user import (
    AccountDelete,
    ImportResult,
    Preferences,
    PreferencesUpdate,
    PasswordChange,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from app.services.ratelimit import check_rate_limit, client_ip
from app.services.repo import delete_user_cascade
from app.services.security import create_access_token, decode_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


@dataclass
class CurrentUser:
    id: str
    email: str
    full_name: Optional[str]
    hashed_password: str
    leetcode_username: Optional[str]
    token_version: int
    created_at: Any

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "CurrentUser":
        return cls(
            id=doc.get("id") or str(doc.get("_id")),
            email=doc.get("email") or "",
            full_name=doc.get("full_name"),
            hashed_password=doc.get("hashed_password") or "",
            leetcode_username=doc.get("leetcode_username"),
            token_version=int(doc.get("token_version") or 0),
            created_at=doc.get("created_at"),
        )

    @property
    def display_name(self) -> str:
        return self.full_name or default_name(self.email)


def default_name(email: str) -> str:
    return email.split("@")[0].replace(".", " ").replace("_", " ").title() or "Learner"


def user_filter(user_id: str) -> Dict[str, Any]:
    return {"$or": [{"id": user_id}, {"_id": user_id}]}


def to_user_response(u: CurrentUser) -> UserResponse:
    return UserResponse(
        id=u.id,
        email=u.email,
        full_name=u.full_name or default_name(u.email),
        leetcode_username=u.leetcode_username,
        created_at=parse_dt(u.created_at) or parse_dt(EPOCH_ISO),
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Database = Depends(get_db)) -> CurrentUser:
    if not token:
        raise _unauthorized("Not authenticated. Valid Bearer token required.")
    payload = decode_access_token(token)
    if not payload:
        raise _unauthorized("Invalid or expired token")
    doc = db.users.find_one(user_filter(str(payload["sub"])))
    if not doc:
        raise _unauthorized("User not found")
    user = CurrentUser.from_doc(doc)
    if int(payload.get("tv", 0)) != user.token_version:
        raise _unauthorized("Session expired. Please log in again.")
    return user


# Kept for backwards compatibility with older imports.
get_authenticated_user = get_current_user


def get_optional_user(token: Optional[str] = Depends(oauth2_scheme), db: Database = Depends(get_db)) -> Optional[CurrentUser]:
    if not token:
        return None
    try:
        return get_current_user(token, db)
    except HTTPException:
        return None


def _issue(user: CurrentUser) -> Token:
    return Token(
        access_token=create_access_token(user.id, user.token_version),
        token_type="bearer",
        user=to_user_response(user),
    )


def _create_user(db: Database, email: str, password: str, full_name: Optional[str]) -> CurrentUser:
    now = now_iso()
    user_id = new_id()
    doc = {
        "_id": user_id,
        "id": user_id,
        "email": email,
        "full_name": (full_name or "").strip() or default_name(email),
        "hashed_password": hash_password(password),
        "leetcode_username": None,
        "token_version": 0,
        "shared_patterns": [],
        "created_at": now,
        "updated_at": now,
    }
    try:
        db.users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="This email is already registered. Please log in.")
    return CurrentUser.from_doc(doc)


@router.post("/register", response_model=Token)
def register(user_in: UserCreate, request: Request, db: Database = Depends(get_db)):
    check_rate_limit(f"register:{client_ip(request)}", limit=10, window_seconds=3600)
    if db.users.find_one({"email": user_in.email}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="This email is already registered. Please log in.")
    return _issue(_create_user(db, user_in.email, user_in.password, user_in.full_name))


@router.post("/login", response_model=Token)
def login(credentials: UserLogin, request: Request, db: Database = Depends(get_db)):
    ip = client_ip(request)
    check_rate_limit(f"login-ip:{ip}", limit=30, window_seconds=300)
    check_rate_limit(f"login:{ip}:{credentials.email}", limit=10, window_seconds=300)
    # Per-account cap regardless of IP, so rotating addresses can't brute-force one account.
    check_rate_limit(f"login-email:{credentials.email}", limit=30, window_seconds=900)

    doc = db.users.find_one({"email": credentials.email})
    if doc:
        if not verify_password(credentials.password, doc.get("hashed_password")):
            raise HTTPException(status_code=401, detail="Incorrect password. Please verify your credentials.")
        return _issue(CurrentUser.from_doc(doc))

    # By design, any email (real or made up) can sign in: an unknown address creates
    # a new account on first login. Emails are never verified.
    if len(credentials.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters to create an account.")
    check_rate_limit(f"register:{ip}", limit=10, window_seconds=3600)
    return _issue(_create_user(db, credentials.email, credentials.password, None))


@router.get("/me", response_model=UserResponse)
def get_me(current_user: CurrentUser = Depends(get_current_user)):
    return to_user_response(current_user)


@router.put("/me", response_model=UserResponse)
def update_me(body: UserUpdate, current_user: CurrentUser = Depends(get_current_user), db: Database = Depends(get_db)):
    updates: Dict[str, Any] = {"updated_at": now_iso()}
    if body.full_name is not None:
        updates["full_name"] = body.full_name.strip() or default_name(current_user.email)
    if body.leetcode_username is not None:
        updates["leetcode_username"] = body.leetcode_username or None
    db.users.update_one(user_filter(current_user.id), {"$set": updates})
    return to_user_response(CurrentUser.from_doc(db.users.find_one(user_filter(current_user.id))))


@router.post("/change-password")
def change_password(body: PasswordChange, request: Request, current_user: CurrentUser = Depends(get_current_user), db: Database = Depends(get_db)):
    check_rate_limit(f"pwcheck:{current_user.id}", limit=10, window_seconds=3600)
    # 400, not 401: the session is valid, only the typed password is wrong (401 signs the client out).
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    new_version = current_user.token_version + 1
    db.users.update_one(
        user_filter(current_user.id),
        {"$set": {"hashed_password": hash_password(body.new_password), "token_version": new_version, "updated_at": now_iso()}},
    )
    return {"message": "Password updated. Other sessions have been signed out.", "access_token": create_access_token(current_user.id, new_version)}


@router.post("/logout-all")
def logout_all(current_user: CurrentUser = Depends(get_current_user), db: Database = Depends(get_db)):
    db.users.update_one(user_filter(current_user.id), {"$inc": {"token_version": 1}})
    return {"message": "Signed out of all devices."}


@router.post("/delete-account")
def delete_account(body: AccountDelete, current_user: CurrentUser = Depends(get_current_user), db: Database = Depends(get_db)):
    check_rate_limit(f"pwcheck:{current_user.id}", limit=10, window_seconds=3600)
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is incorrect.")
    delete_user_cascade(db, current_user.id)
    return {"message": "Your account and all its data were deleted."}


@router.get("/export")
def export_data(current_user: CurrentUser = Depends(get_current_user), db: Database = Depends(get_db)):
    uid = current_user.id
    questions = [strip_mongo_id(q) for q in db.questions.find({"user_id": uid})]
    qids = [q["id"] for q in questions]
    payload = {
        "format": "makepattern-export",
        "version": 1,
        "exported_at": now_iso(),
        "user": {"email": current_user.email, "full_name": current_user.display_name, "leetcode_username": current_user.leetcode_username},
        "folders": [strip_mongo_id(f) for f in db.folders.find({"user_id": uid})],
        "questions": questions,
        "solutions": [strip_mongo_id(s) for s in db.solutions.find({"question_id": {"$in": qids}})],
        "test_cases": [strip_mongo_id(t) for t in db.test_cases.find({"question_id": {"$in": qids}})],
        "bookmarks": [strip_mongo_id(b) for b in db.bookmarks.find({"user_id": uid})],
        "activity": [strip_mongo_id(a) for a in db.activity.find({"user_id": uid})],
    }
    filename = f"makepattern-export-{date.today().isoformat()}.json"
    return Response(
        content=json.dumps(payload, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/preferences", response_model=Preferences)
def get_preferences(current_user: CurrentUser = Depends(get_current_user), db: Database = Depends(get_db)):
    doc = db.users.find_one(user_filter(current_user.id), {"preferences": 1}) or {}
    return Preferences(**{k: v for k, v in (doc.get("preferences") or {}).items() if k in Preferences.model_fields})


@router.put("/preferences", response_model=Preferences)
def update_preferences(body: PreferencesUpdate, current_user: CurrentUser = Depends(get_current_user), db: Database = Depends(get_db)):
    changes = body.model_dump(exclude_none=True)
    if changes:
        db.users.update_one(user_filter(current_user.id), {"$set": {f"preferences.{k}": v for k, v in changes.items()}})
    return get_preferences(current_user, db)


MAX_IMPORT_BYTES = 10 * 1024 * 1024


@router.post("/import", response_model=ImportResult)
async def import_data(request: Request, current_user: CurrentUser = Depends(get_current_user), db: Database = Depends(get_db)):
    check_rate_limit(f"import:{current_user.id}", limit=10, window_seconds=3600)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Import file is larger than 10 MB.")
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_IMPORT_BYTES:
            raise HTTPException(status_code=413, detail="Import file is larger than 10 MB.")
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError):
        raise HTTPException(status_code=400, detail="The file is not valid JSON.")
    from starlette.concurrency import run_in_threadpool
    from app.services.importer import import_export
    return await run_in_threadpool(import_export, db, current_user.id, payload)
