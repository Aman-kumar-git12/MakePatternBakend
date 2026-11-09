from datetime import timedelta
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.config import settings
from app.db import now_utc

MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_BYTES = 72  # bcrypt limit; longer passwords are rejected, never silently truncated


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    if not hashed_password or not hashed_password.startswith("$2"):
        return False
    try:
        pw = plain_password.encode("utf-8")
        if len(pw) > MAX_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(pw, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, token_version: int = 0, expires_minutes: Optional[int] = None) -> str:
    now = now_utc()
    payload = {
        "sub": user_id,
        "tv": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM], options={"require": ["sub", "exp"]})
    except jwt.PyJWTError:
        return None
