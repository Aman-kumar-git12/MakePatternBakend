from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from app.services.security import hash_password, verify_password
from app.database import get_db
from app.config import settings
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from typing import Optional

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.ALGORITHM)

def get_authenticated_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    # If a token is provided, strictly validate it (raises 401 on expired or invalid token)
    if token:
        return get_authenticated_user(token=token, db=db)

    # Explicitly restricted bypass: only permitted in local development if ALLOW_DEV_FALLBACK_AUTH is explicitly True
    if getattr(settings, "ENVIRONMENT", "production") == "development" and getattr(settings, "ALLOW_DEV_FALLBACK_AUTH", False):
        user = db.query(User).filter(User.email == "aman@makepattern.dev").first() or db.query(User).first()
        if user:
            return user

    # Reject unauthenticated requests
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Valid Bearer token required.",
        headers={"WWW-Authenticate": "Bearer"},
    )

import uuid
import logging
import pymongo.errors
from app.mongodb import (
    find_user_by_email_mongo, save_user_mongo, find_user_by_id_mongo,
    restore_user_data_from_mongo_to_sqlite
)

logger = logging.getLogger("dsa_tracker.auth")

@router.post("/register", response_model=Token)
def register(user_in: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    email = user_in.email.strip().lower()

    # 1. Quick duplicate check in SQLite
    sql_existing = db.query(User).filter(User.email == email).first()
    if sql_existing:
        raise HTTPException(status_code=400, detail="This email is already registered. Please log in.")

    # 2. Check MongoDB for existing account
    mongo_existing = find_user_by_email_mongo(email)
    if mongo_existing:
        raise HTTPException(status_code=400, detail="This email is already registered. Please log in.")

    # 3. Fast password hash with rounds=10 (~80ms)
    hashed_pw = hash_password(user_in.password)
    user_id = str(uuid.uuid4())
    full_name = user_in.full_name or email.split("@")[0].replace(".", " ").title()

    # 4. Save to local SQLite immediately for instant responsiveness
    user = User(
        id=user_id,
        email=email,
        full_name=full_name,
        hashed_password=hashed_pw
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 5. Persist to MongoDB in background without delaying HTTP response
    background_tasks.add_task(save_user_mongo, user_id, email, full_name, hashed_pw)

    token = create_access_token({"sub": user.id})
    return Token(access_token=token, token_type="bearer", user=UserResponse.model_validate(user))

@router.post("/login", response_model=Token)
def login(credentials: UserLogin, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    email = credentials.email.strip().lower()

    # 1. Look up in MongoDB Atlas FIRST to get canonical cloud user ID and data
    mongo_user = find_user_by_email_mongo(email)
    if mongo_user:
        if not verify_password(credentials.password, mongo_user["hashed_password"]):
            raise HTTPException(status_code=401, detail="Incorrect password. Please verify your credentials.")

        canonical_id = mongo_user.get("id") or str(mongo_user.get("_id"))

        # Reconcile local SQLite user if ID mismatch exists
        local_user = db.query(User).filter(User.email == email).first()
        if local_user and local_user.id != canonical_id:
            from app.models.folder import Folder as SqlFolder
            from app.models.question import Question as SqlQuestion
            db.query(SqlFolder).filter(SqlFolder.user_id == local_user.id).delete()
            db.query(SqlQuestion).filter(SqlQuestion.user_id == local_user.id).delete()
            db.delete(local_user)
            db.commit()
            local_user = None

        if not local_user:
            local_user = User(
                id=canonical_id,
                email=mongo_user["email"],
                full_name=mongo_user.get("full_name") or email.split("@")[0].replace(".", " ").title(),
                hashed_password=mongo_user["hashed_password"]
            )
            db.add(local_user)
            db.commit()
            db.refresh(local_user)

        # Restore user folders/questions/solutions/bookmarks into SQLite
        restore_user_data_from_mongo_to_sqlite(db, canonical_id)

        token = create_access_token({"sub": canonical_id})
        return Token(access_token=token, token_type="bearer", user=UserResponse.model_validate(local_user))

    # 2. If not in MongoDB, check SQLite
    user = db.query(User).filter(User.email == email).first()
    if user:
        if not verify_password(credentials.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Incorrect password. Please verify your credentials.")
        background_tasks.add_task(save_user_mongo, user.id, user.email, user.full_name, user.hashed_password)
    else:
        # Not present anywhere: auto-create user and save
        user_id = str(uuid.uuid4())
        full_name = email.split("@")[0].replace(".", " ").title()
        hashed_pw = hash_password(credentials.password)

        user = User(
            id=user_id,
            email=email,
            full_name=full_name,
            hashed_password=hashed_pw
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        background_tasks.add_task(save_user_mongo, user_id, email, full_name, hashed_pw)

    token = create_access_token({"sub": user.id})
    return Token(access_token=token, token_type="bearer", user=UserResponse.model_validate(user))

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_authenticated_user)):
    return UserResponse.model_validate(current_user)
