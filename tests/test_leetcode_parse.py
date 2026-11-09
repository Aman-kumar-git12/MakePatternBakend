"""Offline tests for LeetCode parsing, the client wrapper (mocked) and import/sync logic."""
import mongomock
import pytest
from fastapi import HTTPException

from app.services import leetcode as lc
from app.services.leetcode_parse import classify_query, html_to_text, parse_examples, slug_from_url

CLASSIC_PRE = """<p>Given an array of integers <code>nums</code>&nbsp;and an integer <code>target</code>...</p>
<p>&nbsp;</p>
<p><strong class="example">Example 1:</strong></p>
<pre>
<strong>Input:</strong> nums = [2,7,11,15], target = 9
<strong>Output:</strong> [0,1]
<strong>Explanation:</strong> Because nums[0] + nums[1] == 9, we return [0, 1].
</pre>
<p><strong class="example">Example 2:</strong></p>
<pre>
<strong>Input:</strong> nums = [3,2,4], target = 6
<strong>Output:</strong> [1,2]
</pre>
<p>&nbsp;</p>
<p><strong>Constraints:</strong></p>
<ul><li><code>2 &lt;= nums.length &lt;= 10<sup>4</sup></code></li></ul>
"""

EXAMPLE_BLOCK = """<p>Return the minimum moves.</p>
<p><strong class="example">Example 1:</strong></p>
<div class="example-block">
<p><strong>Input:</strong> <span class="example-io">nums = [2,1,3]</span></p>
<p><strong>Output:</strong> <span class="example-io">3</span></p>
<p><strong>Explanation:</strong></p>
<ul>
\t<li>Increase <code>nums[0] = 2</code> by 1.</li>
</ul>
</div>
<p><strong class="example">Example 2:</strong></p>
<div class="example-block">
<p><strong>Input:</strong> <span class="example-io">s = &quot;a&lt;b&quot;</span></p>
<p><strong>Output:</strong> <span class="example-io">true</span></p>
</div>
<p><strong>Constraints:</strong></p>
"""


def test_parse_classic_pre_examples():
    ex = parse_examples(CLASSIC_PRE)
    assert ex == [
        {"input": "nums = [2,7,11,15], target = 9", "output": "[0,1]", "explanation": "Because nums[0] + nums[1] == 9, we return [0, 1]."},
        {"input": "nums = [3,2,4], target = 6", "output": "[1,2]", "explanation": ""},
    ]


def test_parse_example_block_style_and_entities():
    ex = parse_examples(EXAMPLE_BLOCK)
    assert len(ex) == 2
    assert ex[0]["input"] == "nums = [2,1,3]"
    assert ex[0]["output"] == "3"
    assert "Increase nums[0] = 2 by 1." in ex[0]["explanation"]
    assert ex[1] == {"input": 's = "a<b"', "output": "true", "explanation": ""}


def test_parse_falls_back_to_example_testcases():
    ex = parse_examples("<p>No examples here</p>", ["[1,2]\n3", "  "])
    assert ex == [{"input": "[1,2]\n3", "output": "", "explanation": ""}]
    assert parse_examples(None) == []


def test_html_to_text():
    assert html_to_text("<p>a &lt; b&nbsp;c</p><ul><li>x</li></ul>") == "a < b c\n- x"


@pytest.mark.parametrize("q,expected", [
    ("https://leetcode.com/problems/two-sum/description/", ("slug", "two-sum")),
    ("leetcode.com/problems/3sum", ("slug", "3sum")),
    ("two-sum", ("slug", "two-sum")),
    ("0015", ("number", "15")),
    ("  1 ", ("number", "1")),
    ("Two Sum", ("search", "Two Sum")),
    ("subsets", ("search", "subsets")),
])
def test_classify_query(q, expected):
    assert classify_query(q) == expected


def test_slug_from_url():
    assert slug_from_url("https://leetcode.com/problems/LRU-Cache/") == "lru-cache"
    assert slug_from_url("https://example.com/problems/x") is None
    assert slug_from_url(None) is None


# ---------------------------------------------------------------------------
# Client wrapper with mocked GraphQL
# ---------------------------------------------------------------------------

def _q(fid, slug, title, diff="Easy", **extra):
    return {"questionFrontendId": fid, "title": title, "titleSlug": slug, "difficulty": diff,
            "acRate": 50.0, "isPaidOnly": False, "topicTags": [{"name": "Array"}], **extra}


@pytest.fixture
def fake_gql(monkeypatch):
    lc.cache.clear()
    calls = []

    def fake(query, variables=None):
        calls.append((query, variables))
        if "questionList" in query:
            k = variables["k"]
            return {"questionList": {"data": [_q("115", "distinct-subsequences", "Distinct Subsequences", "Hard"),
                                              _q("15", "3sum", "3Sum", "Medium")] if k in ("15", "3sum") else
                                     [_q("1", "two-sum", "Two Sum"), _q("167", "two-sum-ii", "Two Sum II", "Medium")]}}
        if "question(titleSlug" in query:
            slug = variables["slug"]
            if slug == "missing":
                return {"question": None}
            return {"question": _q("1" if slug == "two-sum" else "15", slug, "Two Sum" if slug == "two-sum" else "3Sum",
                                   content=CLASSIC_PRE, hints=["h1", None], exampleTestcaseList=[], stats='{"acRate": "51.2%"}')}
        if "activeDailyCodingChallengeQuestion" in query:
            return {"activeDailyCodingChallengeQuestion": {"date": "2026-11-03", "question": _q("1", "two-sum", "Two Sum")}}
        if "matchedUser" in query:
            if variables["u"] == "ghost":
                return {"matchedUser": None, "allQuestionsCount": []}
            return {"matchedUser": {"username": "Alice", "profile": {"realName": "A", "ranking": 7, "userAvatar": ""},
                                    "submitStatsGlobal": {"acSubmissionNum": [{"difficulty": "All", "count": 3}, {"difficulty": "Easy", "count": 3}]}},
                    "allQuestionsCount": [{"difficulty": "All", "count": 100}]}
        if "recentAcSubmissionList" in query:
            return {"recentAcSubmissionList": [
                {"id": "9", "title": "Two Sum", "titleSlug": "two-sum", "timestamp": "1700000000"},
                {"id": "8", "title": "3Sum", "titleSlug": "3sum", "timestamp": "1690000000"},
                {"id": "7", "title": "Two Sum", "titleSlug": "two-sum", "timestamp": "1680000000"},
            ]}
        raise AssertionError(query)

    monkeypatch.setattr(lc, "_gql", fake)
    return calls


def test_resolve_by_number_slug_and_title(fake_gql):
    assert lc.resolve_problem("15")["slug"] == "3sum"
    p = lc.resolve_problem("https://leetcode.com/problems/two-sum/")
    assert p["frontend_id"] == "1" and p["hints"] == ["h1"] and len(p["examples"]) == 2
    assert p["url"] == "https://leetcode.com/problems/two-sum/"
    assert lc.resolve_problem("two sum")["slug"] == "two-sum"
    with pytest.raises(HTTPException) as e:
        lc.resolve_problem("no such title")
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        lc.get_problem("missing")
    assert e.value.status_code == 404


def test_problem_is_cached(fake_gql):
    lc.get_problem("two-sum")
    lc.get_problem("two-sum")
    assert sum(1 for q, _ in fake_gql if "question(titleSlug" in q) == 1


def test_profile_and_unknown_user(fake_gql):
    prof = lc.get_profile("alice")
    assert prof["username"] == "Alice" and prof["solved"]["Easy"] == 3 and prof["solved"]["Hard"] == 0
    assert prof["total"]["All"] == 100
    with pytest.raises(HTTPException) as e:
        lc.get_profile("ghost")
    assert e.value.status_code == 404


def test_network_error_maps_to_502(monkeypatch):
    import httpx

    class Boom:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(lc.httpx, "Client", Boom)
    lc.cache.clear()
    with pytest.raises(HTTPException) as e:
        lc.get_daily()
    assert e.value.status_code == 502


def test_ttl_cache_bounded():
    c = lc.TTLCache(maxsize=3)
    for i in range(5):
        c.set(str(i), i, ttl=60)
    assert c.get("4") == 4 and c.get("0") is None


# ---------------------------------------------------------------------------
# Import / refresh / sync logic against an in-memory Mongo
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    return mongomock.MongoClient().db


@pytest.fixture
def user(db):
    from app.routers.auth import CurrentUser
    db.users.insert_one({"_id": "u1", "id": "u1", "email": "a@b.co", "hashed_password": "x", "token_version": 0})
    return CurrentUser.from_doc(db.users.find_one({"id": "u1"}))


def test_import_creates_question_and_tests_then_409(fake_gql, db, user):
    from app.routers import leetcode as r
    from app.schemas.leetcode import ImportRequest

    resp = r.import_problem(ImportRequest(q="two-sum", status="Solved"), db=db, current_user=user)
    assert resp.title == "Two Sum" and resp.leetcode_slug == "two-sum" and resp.leetcode_id == "1"
    assert resp.status == "Solved" and resp.solved_at is not None
    assert [t.title for t in resp.test_cases] == ["Example 1", "Example 2"]
    assert resp.test_cases[0].expected_output == "[0,1]"
    with pytest.raises(HTTPException) as e:
        r.import_problem(ImportRequest(q="1"), db=db, current_user=user)
    assert e.value.status_code == 409 and e.value.detail["question_id"] == resp.id


def test_refresh_fills_statement_without_touching_notes(fake_gql, db, user):
    from app.routers import leetcode as r
    from app.services.repo import new_question_doc

    doc = new_question_doc("u1", title="My 3sum", problem_url="https://leetcode.com/problems/3sum/", notes="mine", tags=["custom"])
    db.questions.insert_one(doc)
    resp = r.refresh_problem(doc["id"], db=db, current_user=user)
    assert resp.notes == "mine" and resp.title == "My 3sum"
    assert "Example 1" in resp.problem_statement and resp.leetcode_slug == "3sum"
    assert resp.tags == ["custom", "Array"]
    assert len(resp.test_cases) == 2
    r.refresh_problem(doc["id"], db=db, current_user=user)
    assert db.test_cases.count_documents({"question_id": doc["id"]}) == 2

    plain = new_question_doc("u1", title="Custom")
    db.questions.insert_one(plain)
    with pytest.raises(HTTPException) as e:
        r.refresh_problem(plain["id"], db=db, current_user=user)
    assert e.value.status_code == 400


def test_sync_marks_tracked_solved_and_imports_missing(fake_gql, db, user):
    from app.routers import leetcode as r
    from app.schemas.leetcode import SyncRequest
    from app.services.repo import new_question_doc

    tracked = new_question_doc("u1", title="Two Sum", problem_url="https://leetcode.com/problems/two-sum/")
    db.questions.insert_one(tracked)

    res = r.sync(SyncRequest(username="alice", import_missing=False), db=db, current_user=user)
    assert res["newly_solved"] == ["Two Sum"] and res["imported"] == 0
    q = db.questions.find_one({"id": tracked["id"]})
    assert q["status"] == "Solved" and q["solved_at"].startswith("2023-11-14")
    assert db.users.find_one({"id": "u1"})["leetcode_username"] == "Alice"

    from app.routers.auth import CurrentUser
    user = CurrentUser.from_doc(db.users.find_one({"id": "u1"}))  # each request re-loads the user
    res = r.sync(SyncRequest(import_missing=True), db=db, current_user=user)  # uses saved username
    assert res["already_solved"] == 1 and res["imported"] == 1 and res["newly_solved"] == ["3Sum"]
    folder = db.folders.find_one({"user_id": "u1", "name": "LeetCode Imports"})
    assert folder and db.questions.find_one({"leetcode_slug": "3sum"})["folder_id"] == folder["id"]
    assert db.activity.count_documents({"user_id": "u1", "type": "solved"}) == 2


def test_sync_requires_username(fake_gql, db, user):
    from app.routers import leetcode as r
    from app.schemas.leetcode import SyncRequest

    with pytest.raises(HTTPException) as e:
        r.sync(SyncRequest(), db=db, current_user=user)
    assert e.value.status_code == 400
