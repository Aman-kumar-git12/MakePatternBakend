"""Optional Judge0 client for running C++/Java (and Python/JS) on a sandbox server."""
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException

from app.config import settings

# Judge0 CE language ids (stable across CE/RapidAPI/self-hosted installs).
LANGUAGE_IDS = {
    "cpp": 54,         # C++ (GCC 9.2.0)
    "java": 62,        # Java (OpenJDK 13.0.1)
    "javascript": 63,  # JavaScript (Node.js 12.14.0)
    "python": 71,      # Python (3.8.1)
}

TIMEOUT_SECONDS = 30.0


def _headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.JUDGE0_API_KEY:
        if settings.JUDGE0_API_HOST:
            headers["X-RapidAPI-Key"] = settings.JUDGE0_API_KEY
            headers["X-RapidAPI-Host"] = settings.JUDGE0_API_HOST
        else:
            headers["X-Auth-Token"] = settings.JUDGE0_API_KEY
    return headers


def run_submission(language: str, code: str, stdin: str, client: Optional[httpx.Client] = None) -> Dict[str, Any]:
    if not settings.judge0_enabled:
        raise HTTPException(
            status_code=501,
            detail="Server-side code execution is not configured. Set JUDGE0_URL (and JUDGE0_API_KEY) on the backend to run C++/Java.",
        )
    url = settings.JUDGE0_URL.rstrip("/") + "/submissions"  # type: ignore[union-attr]
    payload = {
        "language_id": LANGUAGE_IDS[language],
        "source_code": code,
        "stdin": stdin,
        "cpu_time_limit": 5,
        "wall_time_limit": 10,
        "memory_limit": 256000,
    }
    own_client = client is None
    http = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        resp = http.post(url, params={"base64_encoded": "false", "wait": "true"}, json=payload, headers=_headers())
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="The code execution service is unreachable right now.")
    finally:
        if own_client:
            http.close()

    if resp.status_code in (401, 403):
        raise HTTPException(status_code=502, detail="The code execution service rejected the server's API key.")
    if resp.status_code == 429:
        raise HTTPException(status_code=502, detail="The code execution service quota is exhausted. Try again later.")
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"The code execution service returned an error ({resp.status_code}).")
    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="The code execution service returned an invalid response.")

    status = (data.get("status") or {}).get("description") or "Unknown"
    return {
        "status": status,
        "stdout": data.get("stdout") or "",
        "stderr": data.get("stderr") or "",
        "compile_output": data.get("compile_output") or "",
        "time": data.get("time"),
        "memory": data.get("memory"),
    }
