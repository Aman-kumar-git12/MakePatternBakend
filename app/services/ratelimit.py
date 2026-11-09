"""Tiny in-process sliding-window rate limiter (good enough for a single instance)."""
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request

_lock = threading.Lock()
_hits: Dict[str, Deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    # The hosting proxy (Render) APPENDS the real client address to X-Forwarded-For, so the
    # right-most entry is the trustworthy one; anything to its left is client-supplied.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def check_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            retry = int(window_seconds - (now - q[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Too many attempts. Please wait {retry} seconds and try again.",
                headers={"Retry-After": str(retry)},
            )
        q.append(now)
        if len(_hits) > 50_000:  # bound memory: drop expired keys first, never active lockouts
            for k in [k for k, d in _hits.items() if not d or now - d[-1] > 3600][:20_000]:
                _hits.pop(k, None)


def reset_rate_limits() -> None:
    with _lock:
        _hits.clear()
