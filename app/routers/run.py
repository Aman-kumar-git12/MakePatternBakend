"""Code execution. Python/JavaScript run in the browser; Judge0 is an optional server-side backend."""
import threading
from typing import List, Literal, Optional, Set, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.routers.auth import CurrentUser, get_current_user
from app.services import judge0
from app.services.ratelimit import check_rate_limit

router = APIRouter(prefix="/run", tags=["run"])

# Each Judge0 run blocks a server worker thread for up to ~30 s. Cap them globally and per user
# so a few users looping `while(1);` can't starve every other endpoint (login included).
_RUN_SLOTS = threading.BoundedSemaphore(4)
_running_users: Set[str] = set()
_running_lock = threading.Lock()


class RunConfig(BaseModel):
    judge0_enabled: bool
    languages: List[str]


class Judge0Request(BaseModel):
    language: Literal["cpp", "java", "python", "javascript"]
    code: str = Field(min_length=1, max_length=100_000)
    stdin: str = Field(default="", max_length=20_000)


class Judge0Result(BaseModel):
    status: str
    stdout: str = ""
    stderr: str = ""
    compile_output: str = ""
    time: Optional[Union[str, float]] = None
    memory: Optional[Union[int, float]] = None


@router.get("/config", response_model=RunConfig)
def run_config(current_user: CurrentUser = Depends(get_current_user)):
    langs = ["python", "javascript"]
    if settings.judge0_enabled:
        langs += ["cpp", "java"]
    return RunConfig(judge0_enabled=settings.judge0_enabled, languages=langs)


@router.post("/judge0", response_model=Judge0Result)
def run_judge0(body: Judge0Request, current_user: CurrentUser = Depends(get_current_user)):
    check_rate_limit(f"judge0:{current_user.id}", limit=30, window_seconds=60)
    with _running_lock:
        if current_user.id in _running_users:
            raise HTTPException(status_code=429, detail="Your previous run is still in progress. Try again when it finishes.")
        _running_users.add(current_user.id)
    try:
        if not _RUN_SLOTS.acquire(timeout=2):
            raise HTTPException(status_code=429, detail="Too many code runs in progress. Try again shortly.")
        try:
            return judge0.run_submission(body.language, body.code, body.stdin)
        finally:
            _RUN_SLOTS.release()
    finally:
        with _running_lock:
            _running_users.discard(current_user.id)
