"""LeetCode public GraphQL client with a small in-memory TTL cache."""
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException

from app.config import settings
from app.services.leetcode_parse import classify_query, parse_examples

logger = logging.getLogger("makepattern.leetcode")

HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com",
    "User-Agent": "Mozilla/5.0 (compatible; MakePatternTracker/1.0)",
}
TIMEOUT = httpx.Timeout(10.0)

TTL_PROBLEM = 24 * 3600
TTL_DAILY = 3600
TTL_SEARCH = 600
TTL_PROFILE = 300


class TTLCache:
    def __init__(self, maxsize: int = 2000):
        self.maxsize = maxsize
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            expires, value = item
            if expires < time.monotonic():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            if len(self._data) >= self.maxsize:
                now = time.monotonic()
                for k in [k for k, (exp, _) in self._data.items() if exp < now]:
                    self._data.pop(k, None)
                while len(self._data) >= self.maxsize:
                    self._data.pop(next(iter(self._data)))
            self._data[key] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


cache = TTLCache()


def problem_url(slug: str) -> str:
    return f"https://leetcode.com/problems/{slug}/"


def _gql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS) as client:
            resp = client.post(settings.LEETCODE_GRAPHQL_URL, json={"query": query, "variables": variables or {}})
    except httpx.HTTPError as e:
        logger.warning("LeetCode request failed: %s", e)
        raise HTTPException(status_code=502, detail="LeetCode is unreachable right now. Please try again later.")
    if resp.status_code == 429:
        raise HTTPException(status_code=502, detail="LeetCode is rate limiting requests right now. Please try again in a minute.")
    if resp.status_code >= 400:
        logger.warning("LeetCode returned HTTP %s", resp.status_code)
        raise HTTPException(status_code=502, detail="LeetCode is unreachable right now. Please try again later.")
    try:
        body = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="LeetCode returned an unexpected response.")
    data = body.get("data") or {}
    if body.get("errors") and not any(v for v in data.values()):
        msg = str(body["errors"][0].get("message", ""))
        if "not exist" in msg.lower() or "not found" in msg.lower():
            raise HTTPException(status_code=404, detail="Not found on LeetCode.")
        logger.warning("LeetCode GraphQL error: %s", msg)
        raise HTTPException(status_code=502, detail="LeetCode could not process the request.")
    return data


def _tags(raw: Optional[List[Dict[str, Any]]]) -> List[str]:
    return [t["name"] for t in (raw or []) if t and t.get("name")]


def _acceptance(ac_rate: Any = None, stats: Optional[str] = None) -> Optional[float]:
    if ac_rate is not None:
        try:
            return round(float(ac_rate), 1)
        except (TypeError, ValueError):
            pass
    if stats:
        try:
            raw = json.loads(stats).get("acRate")
            if raw is not None:
                return round(float(str(raw).rstrip("%")), 1)
        except (ValueError, TypeError, AttributeError):
            pass
    return None


def _summary(q: Dict[str, Any]) -> Dict[str, Any]:
    slug = q.get("titleSlug")
    return {
        "slug": slug,
        "frontend_id": str(q.get("questionFrontendId") or q.get("frontendQuestionId") or ""),
        "title": q.get("title") or slug,
        "difficulty": q.get("difficulty") or "Medium",
        "tags": _tags(q.get("topicTags")),
        "url": problem_url(slug),
        "acceptance_rate": _acceptance(q.get("acRate"), q.get("stats")),
        "is_paid_only": bool(q.get("isPaidOnly") or q.get("paidOnly")),
    }


# ---------------------------------------------------------------------------
# Problems
# ---------------------------------------------------------------------------

_PROBLEM_QUERY = """
query problem($slug: String!) {
  question(titleSlug: $slug) {
    questionFrontendId title titleSlug difficulty isPaidOnly content
    topicTags { name } hints exampleTestcaseList stats
  }
}"""

_SEARCH_QUERY = """
query search($k: String, $limit: Int) {
  questionList(categorySlug: "", limit: $limit, skip: 0, filters: {searchKeywords: $k}) {
    data { questionFrontendId title titleSlug difficulty acRate isPaidOnly topicTags { name } }
  }
}"""


def get_problem(slug: str) -> Dict[str, Any]:
    slug = slug.strip().lower()
    key = f"problem:{slug}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    q = _gql(_PROBLEM_QUERY, {"slug": slug}).get("question")
    if not q:
        raise HTTPException(status_code=404, detail=f"LeetCode problem '{slug}' was not found.")
    problem = _summary(q)
    content = q.get("content")
    problem.update({
        "statement_html": content or "",
        "hints": [h for h in (q.get("hints") or []) if h],
        "examples": parse_examples(content, q.get("exampleTestcaseList")),
    })
    cache.set(key, problem, TTL_PROBLEM)
    return problem


def search_problems(text: str, limit: int = 10) -> List[Dict[str, Any]]:
    text = (text or "").strip()[:100]
    if not text:
        return []
    limit = max(1, min(int(limit), 50))
    key = f"search:{text.lower()}:{limit}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = _gql(_SEARCH_QUERY, {"k": text, "limit": limit}).get("questionList") or {}
    results = [_summary(q) for q in (data.get("data") or []) if q and q.get("titleSlug")]
    cache.set(key, results, TTL_SEARCH)
    return results


def slug_for_number(number: str) -> str:
    number = str(int(number))
    for item in search_problems(number, limit=50):
        if item["frontend_id"] == number:
            return item["slug"]
    raise HTTPException(status_code=404, detail=f"LeetCode problem #{number} was not found.")


def resolve_problem(query: str) -> Dict[str, Any]:
    """Accepts a URL, slug, problem number or title and returns full problem details."""
    kind, value = classify_query(query)
    if not value:
        raise HTTPException(status_code=400, detail="Enter a LeetCode URL, problem number, slug or title.")
    if kind == "slug":
        return get_problem(value)
    if kind == "number":
        return get_problem(slug_for_number(value))
    results = search_problems(value, limit=10)
    wanted = value.strip().lower()
    exact = next((r for r in results if r["title"].lower() == wanted), None)
    if not exact:
        # A single-word title might also be a slug (e.g. "3sum", "subsets").
        if " " not in wanted:
            exact = next((r for r in results if r["slug"] == wanted), None)
    if not exact:
        raise HTTPException(status_code=404, detail=f"No LeetCode problem titled '{value}'. Try the URL or problem number.")
    return get_problem(exact["slug"])


# ---------------------------------------------------------------------------
# Daily challenge
# ---------------------------------------------------------------------------

_DAILY_QUERY = """
query daily {
  activeDailyCodingChallengeQuestion {
    date
    question { questionFrontendId title titleSlug difficulty acRate isPaidOnly topicTags { name } }
  }
}"""


def get_daily() -> Dict[str, Any]:
    cached = cache.get("daily")
    if cached is not None:
        return cached
    d = _gql(_DAILY_QUERY).get("activeDailyCodingChallengeQuestion")
    if not d or not d.get("question"):
        raise HTTPException(status_code=404, detail="LeetCode has no daily challenge right now.")
    result = {"date": d.get("date") or "", "problem": _summary(d["question"])}
    cache.set("daily", result, TTL_DAILY)
    return result


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

_PROFILE_QUERY = """
query profile($u: String!) {
  matchedUser(username: $u) {
    username
    profile { realName ranking userAvatar }
    submitStatsGlobal { acSubmissionNum { difficulty count } }
  }
  allQuestionsCount { difficulty count }
}"""

_RECENT_AC_QUERY = """
query recent($u: String!, $limit: Int!) {
  recentAcSubmissionList(username: $u, limit: $limit) { id title titleSlug timestamp }
}"""

_DIFFS = ("All", "Easy", "Medium", "Hard")


def get_profile(username: str) -> Dict[str, Any]:
    username = username.strip()
    key = f"profile:{username.lower()}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = _gql(_PROFILE_QUERY, {"u": username})
    user = data.get("matchedUser")
    if not user:
        raise HTTPException(status_code=404, detail=f"LeetCode user '{username}' was not found.")
    solved = {d: 0 for d in _DIFFS}
    for row in (user.get("submitStatsGlobal") or {}).get("acSubmissionNum") or []:
        if row.get("difficulty") in solved:
            solved[row["difficulty"]] = int(row.get("count") or 0)
    total = {d: 0 for d in _DIFFS}
    for row in data.get("allQuestionsCount") or []:
        if row.get("difficulty") in total:
            total[row["difficulty"]] = int(row.get("count") or 0)
    profile = user.get("profile") or {}
    result = {
        "username": user.get("username") or username,
        "real_name": profile.get("realName") or "",
        "ranking": profile.get("ranking"),
        "avatar": profile.get("userAvatar") or "",
        "solved": solved,
        "total": total,
    }
    cache.set(key, result, TTL_PROFILE)
    return result


def get_recent_accepted(username: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Most recent accepted submissions (LeetCode caps the public list at 20)."""
    data = _gql(_RECENT_AC_QUERY, {"u": username.strip(), "limit": max(1, min(limit, 20))})
    out = []
    for s in data.get("recentAcSubmissionList") or []:
        if not s or not s.get("titleSlug"):
            continue
        try:
            ts = int(s.get("timestamp") or 0)
        except (TypeError, ValueError):
            ts = 0
        out.append({"slug": s["titleSlug"], "title": s.get("title") or s["titleSlug"], "timestamp": ts})
    return out
