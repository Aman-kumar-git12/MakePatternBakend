import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LEETCODE_USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-.]{1,40}$")


def _normalize_email(v: str) -> str:
    v = (v or "").strip().lower()
    # Any syntactically valid address is accepted; emails are never verified by design.
    if len(v) > 254 or not EMAIL_RE.match(v):
        raise ValueError("Enter an email in the form name@example.com")
    return v



def _bcrypt_safe(v: str) -> str:
    """bcrypt only uses the first 72 BYTES (and bcrypt 5 rejects longer input). The character
    limit allows multi-byte passwords that exceed it, so check the UTF-8 length too."""
    if len(v.encode("utf-8")) > 72:
        raise ValueError("Password is too long (max 72 bytes; non-English characters count as 2-4).")
    return v

class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=72)

    @field_validator('password')
    @classmethod
    def _password_bytes(cls, v: str) -> str:
        return _bcrypt_safe(v)
    full_name: Optional[str] = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _normalize_email(v)


class UserLogin(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=72)

    @field_validator('password')
    @classmethod
    def _password_bytes(cls, v: str) -> str:
        return _bcrypt_safe(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _normalize_email(v)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=100)
    leetcode_username: Optional[str] = Field(default=None, max_length=40)

    @field_validator("leetcode_username")
    @classmethod
    def validate_lc(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if v and not LEETCODE_USERNAME_RE.match(v):
            raise ValueError("Invalid LeetCode username")
        return v


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=6, max_length=72)

    @field_validator('current_password', 'new_password')
    @classmethod
    def _password_bytes(cls, v: str) -> str:
        return _bcrypt_safe(v)


class AccountDelete(BaseModel):
    password: str = Field(min_length=1, max_length=72)

    @field_validator('password')
    @classmethod
    def _password_bytes(cls, v: str) -> str:
        return _bcrypt_safe(v)


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    leetcode_username: Optional[str] = None
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class Preferences(BaseModel):
    theme: Literal["dark", "light", "system"] = "dark"
    editor_theme: Literal["vs-dark", "vs", "hc-black", "hc-light"] = "vs-dark"
    editor_font_size: int = Field(default=14, ge=10, le=28)
    ui_scale: Literal["sm", "md", "lg"] = "md"
    font_family: Literal["default", "readable", "dyslexic"] = "default"
    high_contrast: bool = False
    reduced_motion: bool = False
    focus_mode: bool = False
    shortcuts_enabled: bool = True


class PreferencesUpdate(BaseModel):
    theme: Optional[Literal["dark", "light", "system"]] = None
    editor_theme: Optional[Literal["vs-dark", "vs", "hc-black", "hc-light"]] = None
    editor_font_size: Optional[int] = Field(default=None, ge=10, le=28)
    ui_scale: Optional[Literal["sm", "md", "lg"]] = None
    font_family: Optional[Literal["default", "readable", "dyslexic"]] = None
    high_contrast: Optional[bool] = None
    reduced_motion: Optional[bool] = None
    focus_mode: Optional[bool] = None
    shortcuts_enabled: Optional[bool] = None


class ImportResult(BaseModel):
    root_folder_id: str
    root_folder_name: str
    folders: int
    questions: int
    solutions: int
    test_cases: int
