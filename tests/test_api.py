from datetime import datetime, timedelta, timezone

from tests.conftest import register


def H(token):
    return {"Authorization": f"Bearer {token}"}


def make_folder(client, auth, name="Arrays", parent_id=None, **extra):
    r = client.post("/api/folders/", json={"name": name, "parent_id": parent_id, **extra}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def make_question(client, auth, title="Two Sum", **extra):
    r = client.post("/api/questions/", json={"title": title, **extra}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_fake_email_register_and_login(client):
    data = register(client, email="nobody@made-up-domain.zzz")
    assert data["user"]["full_name"] == "Nobody"  # derived from email, never a hardcoded name
    r = client.post("/api/auth/login", json={"email": "NOBODY@made-up-domain.zzz", "password": "secret123"})
    assert r.status_code == 200
    assert r.json()["user"]["id"] == data["user"]["id"]


def test_login_unknown_email_creates_account(client):
    r = client.post("/api/auth/login", json={"email": "brand.new@fake.test", "password": "hunter22"})
    assert r.status_code == 200
    assert r.json()["user"]["full_name"] == "Brand New"
    again = client.post("/api/auth/login", json={"email": "brand.new@fake.test", "password": "hunter22"})
    assert again.json()["user"]["id"] == r.json()["user"]["id"]


def test_login_wrong_password_and_short_password(client):
    register(client)
    assert client.post("/api/auth/login", json={"email": "learner@fake.test", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/register", json={"email": "x@y.zz", "password": "123"}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "not-an-email", "password": "123456"}).status_code == 422


def test_login_rate_limited(client):
    register(client)
    codes = [client.post("/api/auth/login", json={"email": "learner@fake.test", "password": "wrong"}).status_code for _ in range(12)]
    assert codes[-1] == 429


def test_requires_auth_and_rejects_forged_token(client):
    assert client.get("/api/folders/tree").status_code == 401
    import jwt
    forged = jwt.encode({"sub": "someone", "exp": 9999999999}, "dsa_tracker_super_secret_jwt_key_2026_change_in_production", algorithm="HS256")
    assert client.get("/api/folders/tree", headers=H(forged)).status_code == 401


def test_change_password_revokes_old_tokens(client):
    data = register(client)
    old = H(data["access_token"])
    r = client.post("/api/auth/change-password", json={"current_password": "secret123", "new_password": "newsecret1"}, headers=old)
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert client.get("/api/auth/me", headers=H(r.json()["access_token"])).status_code == 200
    assert client.post("/api/auth/login", json={"email": "learner@fake.test", "password": "newsecret1"}).status_code == 200


def test_logout_all(client):
    data = register(client)
    tok = H(data["access_token"])
    assert client.post("/api/auth/logout-all", headers=tok).status_code == 200
    assert client.get("/api/auth/me", headers=tok).status_code == 401


def test_update_profile(client, auth):
    r = client.put("/api/auth/me", json={"full_name": "Ada", "leetcode_username": "ada_l"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Ada" and r.json()["leetcode_username"] == "ada_l"
    assert client.put("/api/auth/me", json={"leetcode_username": "bad name!"}, headers=auth).status_code == 422


def test_export_and_delete_account(client, mdb):
    data = register(client)
    tok = H(data["access_token"])
    f = make_folder(client, tok)
    make_question(client, tok, folder_id=f["id"])
    exp = client.get("/api/auth/export", headers=tok)
    assert exp.status_code == 200 and "attachment" in exp.headers["content-disposition"]
    body = exp.json()
    assert len(body["questions"]) == 1 and len(body["folders"]) == 1
    assert "hashed_password" not in exp.text
    assert client.post("/api/auth/delete-account", json={"password": "wrong"}, headers=tok).status_code == 400
    assert client.post("/api/auth/delete-account", json={"password": "secret123"}, headers=tok).status_code == 200
    assert mdb.questions.count_documents({}) == 0 and mdb.folders.count_documents({}) == 0 and mdb.users.count_documents({}) == 0


def test_health_does_not_leak(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert set(r.json().keys()) == {"status", "version"}


# ---------------------------------------------------------------------------
# Folders & questions
# ---------------------------------------------------------------------------

def test_folder_tree_counts_and_paths(client, auth):
    root = make_folder(client, auth, "DSA")
    arrays = make_folder(client, auth, "Arrays", root["id"])
    make_question(client, auth, "A", folder_id=arrays["id"], status="Solved")
    make_question(client, auth, "B", folder_id=arrays["id"])
    tree = client.get("/api/folders/tree", headers=auth).json()
    assert tree[0]["question_count"] == 2 and tree[0]["solved_count"] == 1
    assert tree[0]["subfolders"][0]["progress_percentage"] == 50.0
    lst = client.get("/api/questions/", headers=auth).json()
    assert {q["folder_path"] for q in lst} == {"DSA / Arrays"}


def test_position_zero_is_honored(client, auth):
    make_folder(client, auth, "First")
    f = make_folder(client, auth, "Inserted at top", position=0)
    assert f["position"] == 0
    q1 = make_question(client, auth, "q1")
    q2 = make_question(client, auth, "q2")
    assert (q1["position"], q2["position"]) == (0, 1)
    q0 = make_question(client, auth, "q0", position=0)
    assert q0["position"] == 0


def test_enum_validation(client, auth):
    assert client.post("/api/questions/", json={"title": "x", "difficulty": "Impossible"}, headers=auth).status_code == 422
    q = make_question(client, auth)
    assert client.put(f"/api/questions/{q['id']}", json={"status": "Done-ish"}, headers=auth).status_code == 422
    assert client.post("/api/questions/", json={"title": "x" * 301}, headers=auth).status_code == 422


def test_move_question_to_no_folder(client, auth):
    f = make_folder(client, auth)
    q = make_question(client, auth, folder_id=f["id"])
    r = client.put(f"/api/questions/{q['id']}", json={"folder_id": ""}, headers=auth)
    assert r.status_code == 200 and r.json()["folder_id"] is None
    r = client.post(f"/api/questions/{q['id']}/move", json={"target_folder_id": f["id"]}, headers=auth)
    assert r.json()["folder_id"] == f["id"]
    r = client.post(f"/api/questions/{q['id']}/move", json={"target_folder_id": None}, headers=auth)
    assert r.json()["folder_id"] is None


def test_circular_folder_move_rejected(client, auth):
    a = make_folder(client, auth, "A")
    b = make_folder(client, auth, "B", a["id"])
    assert client.post(f"/api/folders/{a['id']}/move", json={"target_parent_id": b["id"]}, headers=auth).status_code == 400


def test_delete_folder_cascades(client, auth, mdb):
    a = make_folder(client, auth, "A")
    b = make_folder(client, auth, "B", a["id"])
    q = make_question(client, auth, folder_id=b["id"])
    client.post(f"/api/solutions/question/{q['id']}", json={"code": "print(1)"}, headers=auth)
    client.post(f"/api/test-cases/question/{q['id']}", json={"input": "1", "expected_output": "1"}, headers=auth)
    client.post(f"/api/bookmarks/{q['id']}/toggle", headers=auth)
    assert client.delete(f"/api/folders/{a['id']}", headers=auth).status_code == 200
    for coll in ("folders", "questions", "solutions", "test_cases", "bookmarks"):
        assert mdb[coll].count_documents({}) == 0, coll


def test_users_are_isolated(client, auth):
    q = make_question(client, auth)
    other = H(register(client, email="other@fake.test")["access_token"])
    assert client.get(f"/api/questions/{q['id']}", headers=other).status_code == 404
    assert client.put(f"/api/questions/{q['id']}", json={"title": "pwn"}, headers=other).status_code == 404
    assert client.post(f"/api/solutions/question/{q['id']}", json={"code": "x"}, headers=other).status_code == 404
    assert client.get("/api/questions/", headers=other).json() == []


def test_solution_and_test_case_crud(client, auth):
    q = make_question(client, auth)
    s = client.post(f"/api/solutions/question/{q['id']}", json={"code": "for i in range(n):\n  for j in range(n):\n    pass", "language": "python"}, headers=auth).json()
    assert s["time_complexity_estimate"]
    s2 = client.put(f"/api/solutions/{s['id']}", json={"manual_time_complexity": "O(n^2)"}, headers=auth).json()
    assert s2["time_complexity"] == "O(n^2)"
    tc = client.post(f"/api/test-cases/question/{q['id']}", json={"input": "[1,2]", "expected_output": "3"}, headers=auth).json()
    tc2 = client.put(f"/api/test-cases/{tc['id']}", json={"notes": "edge"}, headers=auth).json()
    assert tc2["notes"] == "edge" and tc2["input"] == "[1,2]"
    full = client.get(f"/api/questions/{q['id']}", headers=auth).json()
    assert len(full["solutions"]) == 1 and len(full["test_cases"]) == 1


def test_bookmarks_and_search(client, auth):
    f = make_folder(client, auth, "Graphs")
    q = make_question(client, auth, "Course Schedule", folder_id=f["id"], notes="topological sort")
    assert client.post(f"/api/bookmarks/{q['id']}/toggle", headers=auth).json()["is_bookmarked"] is True
    bms = client.get("/api/bookmarks/", headers=auth).json()
    assert bms[0]["question"]["folder_path"] == "Graphs"
    res = client.get("/api/search/", params={"q": "topological"}, headers=auth).json()
    assert res["questions"][0]["id"] == q["id"]
    assert client.get("/api/search/", params={"q": ".*("}, headers=auth).status_code == 200  # regex-safe


# ---------------------------------------------------------------------------
# Tracking: solved_at, reviews, attempts, progress
# ---------------------------------------------------------------------------

def test_solving_schedules_review_and_logs_activity(client, auth):
    q = make_question(client, auth)
    r = client.put(f"/api/questions/{q['id']}", json={"status": "Solved"}, headers=auth).json()
    assert r["solved_at"] and r["next_review_at"] and r["review_interval_days"] == 1
    act = client.get("/api/progress/activity", params={"days": 7}, headers=auth).json()
    assert act["days"][-1]["solved"] == 1 and act["current_streak"] == 1


def test_review_queue_flow(client, auth, mdb):
    q = make_question(client, auth)
    client.put(f"/api/questions/{q['id']}", json={"status": "Needs Revision"}, headers=auth)
    due = client.get("/api/reviews/due", headers=auth).json()
    assert due["due_count"] == 1 and due["due"][0]["id"] == q["id"]
    r = client.post(f"/api/reviews/{q['id']}", json={"rating": "good"}, headers=auth).json()
    assert r["status"] == "Solved" and r["review_count"] == 1 and r["review_interval_days"] == 1
    due = client.get("/api/reviews/due", headers=auth).json()
    assert due["due_count"] == 0 and due["reviewed_today"] == 1 and len(due["upcoming"]) == 1
    r = client.post(f"/api/reviews/{q['id']}", json={"rating": "again"}, headers=auth).json()
    assert r["status"] == "Needs Revision" and r["review_interval_days"] == 1
    assert client.post(f"/api/reviews/{q['id']}", json={"rating": "meh"}, headers=auth).status_code == 422


def test_attempt_logging(client, auth):
    q = make_question(client, auth)
    r = client.post(f"/api/questions/{q['id']}/attempt", json={"minutes": 25}, headers=auth).json()
    assert r["attempts"] == 1 and r["time_spent_minutes"] == 25 and r["status"] == "In Progress"
    r = client.post(f"/api/questions/{q['id']}/attempt", json={"minutes": 10, "solved": True}, headers=auth).json()
    assert r["attempts"] == 2 and r["time_spent_minutes"] == 35 and r["status"] == "Solved"
    assert client.post(f"/api/questions/{q['id']}/attempt", json={"minutes": 9999}, headers=auth).status_code == 422


def test_progress_summary_recent_is_by_updated_at(client, auth):
    a = make_question(client, auth, "Two Sum")
    b = make_question(client, auth, "Zeta")
    client.put(f"/api/questions/{b['id']}", json={"notes": "touched"}, headers=auth)
    s = client.get("/api/progress/summary", headers=auth).json()
    assert s["recent_questions"][0]["id"] == b["id"]
    client.put(f"/api/questions/{a['id']}", json={"status": "Solved"}, headers=auth)
    s = client.get("/api/progress/summary", headers=auth).json()
    assert s["recent_questions"][0]["id"] == a["id"]
    assert s["solved_questions"] == 1 and s["solved_this_week"] == 1 and s["current_streak"] == 1


def test_streak_computation():
    from datetime import date
    from app.services.tracking import streaks
    today = date(2026, 11, 3)
    days = [date(2026, 11, 2), date(2026, 11, 1), date(2026, 10, 31), date(2026, 10, 20), date(2026, 10, 21)]
    assert streaks(days, today) == (3, 3)
    assert streaks([date(2026, 10, 30)], today) == (0, 1)
    assert streaks([], today) == (0, 0)


def test_timezone_header_controls_day_boundaries(client, auth, mdb):
    q = make_question(client, auth)
    # Activity at 23:30 UTC is "tomorrow" in Asia/Kolkata (UTC+5:30).
    late = datetime.now(timezone.utc).replace(hour=23, minute=30) - timedelta(days=1)
    uid = mdb.users.find_one({})["id"]
    mdb.activity.insert_one({"id": "a1", "user_id": uid, "type": "solved", "question_id": q["id"], "at": late.isoformat(timespec="microseconds")})
    utc = client.get("/api/progress/activity", params={"days": 7}, headers=auth).json()
    ist = client.get("/api/progress/activity", params={"days": 7}, headers={**auth, "X-Timezone": "Asia/Kolkata"}).json()
    utc_day = next(d["date"] for d in utc["days"] if d["count"])
    ist_day = next(d["date"] for d in ist["days"] if d["count"])
    assert utc_day != ist_day


# ---------------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------------

def _shared_setup(client, auth):
    f = make_folder(client, auth, "Sliding Window")
    sub = make_folder(client, auth, "Variable", f["id"])
    q = make_question(client, auth, "Longest Substring", folder_id=sub["id"], notes="my notes", status="Solved")
    client.post(f"/api/solutions/question/{q['id']}", json={"code": "print('hi there friend')"}, headers=auth)
    share = client.post(f"/api/folders/{f['id']}/share", headers=auth).json()
    return f, q, share


def test_share_snapshot_is_public_frozen_and_anonymous(client, auth):
    f, q, share = _shared_setup(client, auth)
    pub = client.get(f"/api/shared/{share['share_id']}")
    assert pub.status_code == 200
    body = pub.json()
    assert body["pattern"]["user_id"] == "" and body["pattern"]["subfolders"][0]["questions"][0]["status"] == "Not Started"
    sq = client.get(f"/api/shared/{share['share_id']}/questions/{q['id']}").json()
    assert sq["user_id"] == "" and sq["notes"] == "my notes" and len(sq["solutions"]) == 1
    # Later edits by the owner don't change the snapshot.
    client.put(f"/api/questions/{q['id']}", json={"title": "Renamed"}, headers=auth)
    assert client.get(f"/api/shared/{share['share_id']}/questions/{q['id']}").json()["title"] == "Longest Substring"


def test_revoke_kills_old_link(client, auth):
    f, q, share = _shared_setup(client, auth)
    new = client.post(f"/api/folders/{f['id']}/share/revoke", headers=auth).json()
    assert new["share_id"] != share["share_id"]
    assert client.get(f"/api/shared/{share['share_id']}").status_code == 404
    assert client.get(f"/api/shared/{share['share_id']}/questions/{q['id']}").status_code == 404
    assert client.get(f"/api/shared/{new['share_id']}").status_code == 200


def test_disable_and_reenable_share(client, auth):
    f, q, share = _shared_setup(client, auth)
    assert client.patch(f"/api/folders/{f['id']}/share", json={"is_active": False}, headers=auth).json()["is_active"] is False
    assert client.get(f"/api/shared/{share['share_id']}").status_code == 404
    assert client.patch(f"/api/folders/{f['id']}/share", json={"is_active": True}, headers=auth).json()["is_active"] is True
    assert client.get(f"/api/shared/{share['share_id']}").status_code == 200
    assert client.delete(f"/api/folders/{f['id']}/share", headers=auth).status_code == 200
    assert client.get(f"/api/shared/{share['share_id']}").status_code == 404


def test_fork_shared_pattern(client, auth):
    f, q, share = _shared_setup(client, auth)
    other = H(register(client, email="viewer@fake.test")["access_token"])
    assert client.post(f"/api/shared/{share['share_id']}/fork").status_code == 401
    r = client.post(f"/api/shared/{share['share_id']}/fork", headers=other)
    assert r.status_code == 200, r.text
    assert r.json()["questions_imported"] == 1
    tree = client.get("/api/folders/tree", headers=other).json()
    assert tree[0]["name"].startswith("Sliding Window (from ")
    copied = tree[0]["subfolders"][0]["questions"][0]
    full = client.get(f"/api/questions/{copied['id']}", headers=other).json()
    assert full["notes"] == "my notes" and len(full["solutions"]) == 1 and full["status"] == "Not Started"
    assert full["id"] != q["id"]


def test_cannot_share_someone_elses_folder(client, auth):
    f = make_folder(client, auth)
    other = H(register(client, email="other@fake.test")["access_token"])
    assert client.post(f"/api/folders/{f['id']}/share", headers=other).status_code == 404
