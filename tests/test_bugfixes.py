"""Regression tests for bugs found in the 2026-11 audit. Each test failed before its fix."""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from pymongo.errors import DuplicateKeyError

from app.services import leetcode as lc
from app.services.share_service import resolve_public_snapshot
from tests.conftest import register
from tests.test_api import H, make_folder, make_question


def _import(client, headers, payload):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return client.post("/api/auth/import", content=body, headers={**headers, "Content-Type": "application/json"})


# --- validation -------------------------------------------------------------------------------

def test_huge_tag_list_is_rejected_fast(client, auth):
    tags = [f"t{i}" for i in range(50_000)]
    start = time.monotonic()
    r = client.post("/api/questions/", json={"title": "x", "tags": tags}, headers=auth)
    assert r.status_code == 422
    assert time.monotonic() - start < 2


def test_whitespace_only_names_rejected(client, auth):
    assert client.post("/api/folders/", json={"name": "   "}, headers=auth).status_code == 422
    assert client.post("/api/questions/", json={"title": "  "}, headers=auth).status_code == 422
    f = make_folder(client, auth)
    assert client.put(f"/api/folders/{f['id']}", json={"name": " "}, headers=auth).status_code == 422


def test_multibyte_password_over_72_bytes_is_422_not_500(client):
    pw = "é" * 40  # 40 chars, 80 bytes
    assert client.post("/api/auth/register", json={"email": "u@fake.test", "password": pw}).status_code == 422
    assert client.post("/api/auth/login", json={"email": "u@fake.test", "password": pw}).status_code == 422


# --- rate limiting ------------------------------------------------------------------------------

def test_spoofed_forwarded_for_does_not_bypass_login_limit(client):
    register(client, "victim@fake.test")
    codes = []
    for i in range(15):
        hdr = {"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7"}  # left part is client-controlled
        codes.append(client.post("/api/auth/login", json={"email": "victim@fake.test", "password": "wrong!!"}, headers=hdr).status_code)
    assert 429 in codes


def test_wrong_current_password_is_400_not_401(client, auth):
    r = client.post("/api/auth/change-password", json={"current_password": "nope!!", "new_password": "newsecret1"}, headers=auth)
    assert r.status_code == 400


# --- questions / LeetCode -----------------------------------------------------------------------

def test_changing_problem_url_clears_stale_slug(client, auth, mdb):
    q = make_question(client, auth, problem_url="https://leetcode.com/problems/two-sum/")
    assert mdb.questions.find_one({"id": q["id"]})["leetcode_slug"] == "two-sum"
    client.put(f"/api/questions/{q['id']}", json={"problem_url": "https://neetcode.io/problems/x"}, headers=auth)
    assert mdb.questions.find_one({"id": q["id"]})["leetcode_slug"] is None


def test_sync_does_not_undo_needs_revision(client, auth, mdb, monkeypatch):
    old_ac = int((datetime.now(timezone.utc) - timedelta(days=400)).timestamp())
    monkeypatch.setattr(lc, "get_profile", lambda u: {"username": u, "solved": {}, "total": {}})
    monkeypatch.setattr(lc, "get_recent_accepted", lambda u, limit=20: [
        {"slug": "two-sum", "title": "Two Sum", "timestamp": old_ac},
        {"slug": "3sum", "title": "3Sum", "timestamp": old_ac},
    ])
    flagged = make_question(client, auth, "Two Sum", problem_url="https://leetcode.com/problems/two-sum/")
    fresh = make_question(client, auth, "3Sum", problem_url="https://leetcode.com/problems/3sum/")
    client.post(f"/api/reviews/{flagged['id']}", json={"rating": "again"}, headers=auth)
    assert mdb.questions.find_one({"id": flagged["id"]})["status"] == "Needs Revision"

    r = client.post("/api/leetcode/sync", json={"username": "someone"}, headers=auth)
    assert r.status_code == 200, r.text
    assert mdb.questions.find_one({"id": flagged["id"]})["status"] == "Needs Revision"
    assert mdb.questions.find_one({"id": fresh["id"]})["status"] == "Solved"


# --- reviews ------------------------------------------------------------------------------------

def test_offline_batch_with_mixed_naive_and_aware_times(client, auth):
    q = make_question(client, auth)
    batch = {"reviews": [
        {"client_id": "a", "question_id": q["id"], "rating": "good", "reviewed_at": "2026-11-03T10:00:00Z"},
        {"client_id": "b", "question_id": q["id"], "rating": "good", "reviewed_at": "2026-11-03T11:00:00"},
    ]}
    r = client.post("/api/reviews/batch", json=batch, headers=auth)
    assert r.status_code == 200, r.text


def test_offline_client_id_is_unique(client, auth, mdb):
    mdb.activity.insert_one({"user_id": "u", "client_id": "same", "type": "review"})
    with pytest.raises(DuplicateKeyError):
        mdb.activity.insert_one({"user_id": "u", "client_id": "same", "type": "review"})
    # Rows without a client_id are unaffected.
    mdb.activity.insert_one({"user_id": "u", "type": "solved"})
    mdb.activity.insert_one({"user_id": "u", "type": "solved"})


def test_review_promotion_logs_solved_activity(client, auth, mdb):
    q = make_question(client, auth)
    client.post(f"/api/reviews/{q['id']}", json={"rating": "good"}, headers=auth)
    assert mdb.activity.count_documents({"question_id": q["id"], "type": "solved"}) == 1


# --- import -------------------------------------------------------------------------------------

def _export_payload(**over):
    payload = {"format": "makepattern-export", "version": 1, "folders": [], "questions": [], "solutions": [], "test_cases": []}
    payload.update(over)
    return payload


def test_import_bad_version_is_400(client, auth):
    assert _import(client, auth, _export_payload(version="abc")).status_code == 400
    assert _import(client, auth, "[" * 100_000 + "]" * 100_000).status_code == 400


def test_import_review_step_clamped_then_hard_review_works(client, auth):
    payload = _export_payload(questions=[{"id": "q1", "title": "Deep", "review_step": 9}])
    assert _import(client, auth, payload).status_code == 200
    qid = client.get("/api/questions/", headers=auth).json()[0]["id"]
    assert client.post(f"/api/reviews/{qid}", json={"rating": "hard"}, headers=auth).status_code == 200


def test_import_folder_cycle_stays_visible(client, auth):
    payload = _export_payload(
        folders=[{"id": "A", "name": "A", "parent_id": "B"}, {"id": "B", "name": "B", "parent_id": "A"}],
        questions=[{"id": "q1", "title": "Inside A", "folder_id": "A"}],
    )
    assert _import(client, auth, payload).status_code == 200
    tree = client.get("/api/folders/tree", headers=auth).json()
    assert sum(t["question_count"] for t in tree) == 1


def test_import_keeps_manual_complexity_and_legacy_fields(client, auth, mdb):
    payload = _export_payload(
        questions=[{"id": "q1", "title": "T"}],
        solutions=[{"question_id": "q1", "code": "x", "manual_space_complexity": "O(1)", "approach_type": "Optimal", "notes": "why"}],
        test_cases=[{"question_id": "q1", "input_data": "1 2", "expected_output": "3", "explanation": "sum"}],
    )
    assert _import(client, auth, payload).status_code == 200
    sol = mdb.solutions.find_one({})
    assert sol["manual_space_complexity"] == "O(1)" and sol["solution_type"] == "Optimal" and sol["explanation"] == "why"
    tc = mdb.test_cases.find_one({})
    assert tc["input"] == "1 2" and tc["notes"] == "sum"


# --- stats / solutions / folders ---------------------------------------------------------------

def test_solved_this_week_ignores_unsolved(client, auth):
    q = make_question(client, auth)
    client.put(f"/api/questions/{q['id']}", json={"status": "Solved"}, headers=auth)
    client.put(f"/api/questions/{q['id']}", json={"status": "Not Started"}, headers=auth)
    s = client.get("/api/progress/summary", headers=auth).json()
    assert s["solved_this_week"] == 0


def test_clearing_manual_time_complexity(client, auth, mdb):
    q = make_question(client, auth)
    sol = client.post(f"/api/solutions/question/{q['id']}", json={"code": "print(1)", "manual_time_complexity": "O(n^2)"}, headers=auth).json()
    client.put(f"/api/solutions/{sol['id']}", json={"manual_time_complexity": ""}, headers=auth)
    assert mdb.solutions.find_one({"id": sol["id"]})["time_complexity"] != "O(n^2)"


def test_folder_rename_returns_recursive_counts(client, auth):
    parent = make_folder(client, auth, "Parent")
    child = make_folder(client, auth, "Child", parent["id"])
    make_question(client, auth, folder_id=child["id"])
    r = client.put(f"/api/folders/{parent['id']}", json={"name": "Renamed"}, headers=auth).json()
    assert r["question_count"] == 1


# --- sharing ------------------------------------------------------------------------------------

def test_duplicate_share_records_are_all_revoked(client, auth, mdb):
    f = make_folder(client, auth)
    make_question(client, auth, folder_id=f["id"])
    first = client.post(f"/api/folders/{f['id']}/share", headers=auth).json()
    # Simulate the old double-click race: a second record for the same folder.
    dup = {**mdb.users.find_one({})["shared_patterns"][0], "share_id": "dup-share-id-123"}
    mdb.users.update_one({}, {"$push": {"shared_patterns": dup}})
    mdb.share_snapshots.insert_one({**mdb.share_snapshots.find_one({}, {"_id": 0}), "share_id": "dup-share-id-123"})

    client.delete(f"/api/folders/{f['id']}/share", headers=auth)
    assert client.get(f"/api/shared/{first['share_id']}").status_code == 404
    assert client.get("/api/shared/dup-share-id-123").status_code == 404


def test_double_share_creates_one_record(client, auth, mdb):
    f = make_folder(client, auth)
    client.post(f"/api/folders/{f['id']}/share", headers=auth)
    client.post(f"/api/folders/{f['id']}/share", headers=auth)
    assert len(mdb.users.find_one({})["shared_patterns"]) == 1


# --- infrastructure -----------------------------------------------------------------------------

def test_unhandled_error_has_cors_headers(client, monkeypatch):
    from app.routers import progress

    def boom(*a, **k):
        raise RuntimeError("boom")

    data = register(client, "e@fake.test")
    monkeypatch.setattr(progress, "build_tree_for_user", boom)
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/progress/summary", headers={**H(data["access_token"]), "Origin": "https://make-pattern-dev.vercel.app"})
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == "https://make-pattern-dev.vercel.app"
    assert "boom" not in r.text
