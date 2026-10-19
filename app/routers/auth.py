from fastapi import APIRouter, Depends, HTTPException, status
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
from app.mongodb import find_user_by_email_mongo, save_user_mongo, find_user_by_id_mongo

logger = logging.getLogger("dsa_tracker.auth")

@router.post("/register", response_model=Token)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    email = user_in.email.strip().lower()

    # 1. Duplicate check in MongoDB & SQL
    mongo_existing = find_user_by_email_mongo(email)
    sql_existing = db.query(User).filter(User.email.ilike(email)).first()
    if mongo_existing or sql_existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # 2. Hash password securely with bcrypt
    hashed_pw = hash_password(user_in.password)
    user_id = str(uuid.uuid4())
    full_name = user_in.full_name or "Aman Kumar"

    # 3. Persist in MongoDB with unique index enforcement
    try:
        save_user_mongo(
            user_id=user_id,
            email=email,
            full_name=full_name,
            hashed_password=hashed_pw
        )
    except pymongo.errors.DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        logger.warning(f"MongoDB save warning: {e}")

    # 4. Persist in SQL database for relational constraints
    user = User(
        id=user_id,
        email=email,
        full_name=full_name,
        hashed_password=hashed_pw
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.id})
    return Token(access_token=token, token_type="bearer", user=UserResponse.model_validate(user))

@router.post("/login", response_model=Token)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    email = credentials.email.strip().lower()

    # Look up in SQL
    user = db.query(User).filter(User.email.ilike(email)).first()

    # If not in SQL, check MongoDB
    if not user:
        mongo_user = find_user_by_email_mongo(email)
        if mongo_user and verify_password(credentials.password, mongo_user["hashed_password"]):
            user = User(
                id=mongo_user.get("id") or str(mongo_user.get("_id")),
                email=mongo_user["email"],
                full_name=mongo_user.get("full_name") or "Aman Kumar",
                hashed_password=mongo_user["hashed_password"]
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            raise HTTPException(status_code=401, detail="Invalid email or password")
    else:
        if not verify_password(credentials.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        # Ensure MongoDB has the user synced
        save_user_mongo(user.id, user.email, user.full_name, user.hashed_password)

    token = create_access_token({"sub": user.id})
    return Token(access_token=token, token_type="bearer", user=UserResponse.model_validate(user))

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_authenticated_user)):
    return UserResponse.model_validate(current_user)
