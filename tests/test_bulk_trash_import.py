from datetime import datetime, timedelta, timezone

from tests.conftest import register
from tests.test_api import H, make_folder, make_question


# ---------------------------------------------------------------------------
# Trash / undo
# ---------------------------------------------------------------------------

def test_delete_question_goes_to_trash_and_restores(client, auth, mdb):
    f = make_folder(client, auth)
    q = make_question(client, auth, folder_id=f["id"], notes="keep me")
    client.post(f"/api/solutions/question/{q['id']}", json={"code": "print('hello world!!')"}, headers=auth)
    client.post(f"/api/test-cases/question/{q['id']}", json={"input": "1", "expected_output": "1"}, headers=auth)
    client.post(f"/api/bookmarks/{q['id']}/toggle", headers=auth)

    r = client.delete(f"/api/questions/{q['id']}", headers=auth).json()
    assert r["trash_id"]
    assert client.get(f"/api/questions/{q['id']}", headers=auth).status_code == 404
    items = client.get("/api/trash", headers=auth).json()
    assert items[0]["kind"] == "question" and items[0]["title"] == "Two Sum" and items[0]["question_count"] == 1

    res = client.post(f"/api/trash/{r['trash_id']}/restore", headers=auth).json()
    assert res["question_ids"] == [q["id"]]
    full = client.get(f"/api/questions/{q['id']}", headers=auth).json()
    assert full["notes"] == "keep me" and full["is_bookmarked"] and len(full["solutions"]) == 1 and len(full["test_cases"]) == 1
    assert client.get("/api/trash", headers=auth).json() == []
    assert client.post(f"/api/trash/{r['trash_id']}/restore", headers=auth).status_code == 404


def test_folder_trash_restores_subtree_and_handles_missing_parent(client, auth):
    root = make_folder(client, auth, "Root")
    a = make_folder(client, auth, "A", root["id"])
    b = make_folder(client, auth, "B", a["id"])
    make_question(client, auth, "in B", folder_id=b["id"])
    r = client.delete(f"/api/folders/{a['id']}", headers=auth).json()
    client.delete(f"/api/folders/{root['id']}", headers=auth)  # original parent now also gone
    res = client.post(f"/api/trash/{r['trash_id']}/restore", headers=auth).json()
    assert res["restored_folders"] == 2 and res["restored_questions"] == 1 and res["folder_id"] == a["id"]
    tree = client.get("/api/folders/tree", headers=auth).json()
    assert tree[0]["name"] == "A" and tree[0]["parent_id"] is None  # restored at root
    assert tree[0]["subfolders"][0]["questions"][0]["title"] == "in B"


def test_trash_delete_forever_empty_and_expiry(client, auth, mdb):
    ids = [client.delete(f"/api/questions/{make_question(client, auth, f'q{i}')['id']}", headers=auth).json()["trash_id"] for i in range(3)]
    assert client.delete(f"/api/trash/{ids[0]}", headers=auth).status_code == 200
    mdb.trash.update_one({"id": ids[1]}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert [t["id"] for t in client.get("/api/trash", headers=auth).json()] == [ids[2]]
    assert client.delete("/api/trash", headers=auth).json()["deleted"] == 1


def test_trash_is_per_user(client, auth):
    tid = client.delete(f"/api/questions/{make_question(client, auth)['id']}", headers=auth).json()["trash_id"]
    other = H(register(client, email="other@fake.test")["access_token"])
    assert client.get("/api/trash", headers=other).json() == []
    assert client.post(f"/api/trash/{tid}/restore", headers=other).status_code == 404


def test_delete_keeps_activity_history(client, auth):
    q = make_question(client, auth, status="Solved")
    client.delete(f"/api/questions/{q['id']}", headers=auth)
    assert client.get("/api/progress/activity", params={"days": 7}, headers=auth).json()["current_streak"] == 1


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------

def test_bulk_actions(client, auth):
    f = make_folder(client, auth, "Target")
    qs = [make_question(client, auth, f"q{i}", tags=["old"]) for i in range(3)]
    ids = [q["id"] for q in qs]

    def bulk(**body):
        return client.post("/api/questions/bulk", json={"question_ids": ids, **body}, headers=auth)

    assert bulk(action="move", folder_id=f["id"]).json()["updated"] == 3
    assert {q["folder_id"] for q in client.get("/api/questions/", headers=auth).json()} == {f["id"]}
    bulk(action="move", folder_id=None)
    assert {q["folder_id"] for q in client.get("/api/questions/", headers=auth).json()} == {None}
    bulk(action="set_status", status="Solved")
    assert all(q["solved_at"] for q in client.get("/api/questions/", headers=auth).json())
    bulk(action="set_difficulty", difficulty="Hard")
    bulk(action="add_tags", tags=["dp", "old"])
    bulk(action="remove_tags", tags=["old"])
    bulk(action="bookmark")
    items = client.get("/api/questions/", headers=auth).json()
    assert all(q["difficulty"] == "Hard" and q["tags"] == ["dp"] and q["is_bookmarked"] for q in items)
    bulk(action="unbookmark")
    assert not any(q["is_bookmarked"] for q in client.get("/api/questions/", headers=auth).json())

    assert bulk(action="set_status").status_code == 422
    assert bulk(action="explode").status_code == 422

    r = bulk(action="delete").json()
    assert r["updated"] == 3 and r["trash_id"]
    assert client.get("/api/questions/", headers=auth).json() == []
    assert client.get("/api/trash", headers=auth).json()[0]["kind"] == "bulk"
    client.post(f"/api/trash/{r['trash_id']}/restore", headers=auth)
    assert len(client.get("/api/questions/", headers=auth).json()) == 3


def test_bulk_ignores_other_users_questions(client, auth):
    mine = make_question(client, auth)
    other = H(register(client, email="other@fake.test")["access_token"])
    theirs = make_question(client, other, "theirs")
    r = client.post("/api/questions/bulk", json={"question_ids": [mine["id"], theirs["id"]], "action": "delete"}, headers=auth).json()
    assert r["updated"] == 1
    assert client.get(f"/api/questions/{theirs['id']}", headers=other).status_code == 200


# ---------------------------------------------------------------------------
# JSON import (export round trip)
# ---------------------------------------------------------------------------

def test_export_import_round_trip_into_new_account(client, auth):
    root = make_folder(client, auth, "DSA")
    sub = make_folder(client, auth, "Graphs", root["id"])
    q = make_question(client, auth, "Course Schedule", folder_id=sub["id"], notes="topo sort", status="Solved", tags=["graph"])
    make_question(client, auth, "Loose one")
    client.post(f"/api/solutions/question/{q['id']}", json={"code": "print('solution code')", "language": "python"}, headers=auth)
    client.post(f"/api/test-cases/question/{q['id']}", json={"input": "2", "expected_output": "true"}, headers=auth)
    client.post(f"/api/bookmarks/{q['id']}/toggle", headers=auth)
    export = client.get("/api/auth/export", headers=auth).content

    other = H(register(client, email="restore@fake.test")["access_token"])
    r = client.post("/api/auth/import", content=export, headers={**other, "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert (res["folders"], res["questions"], res["solutions"], res["test_cases"]) == (2, 2, 1, 1)
    tree = client.get("/api/folders/tree", headers=other).json()
    assert tree[0]["name"].startswith("Imported ") and tree[0]["question_count"] == 2
    graphs = tree[0]["subfolders"][0]["subfolders"][0]
    assert graphs["name"] == "Graphs"
    copied = client.get(f"/api/questions/{graphs['questions'][0]['id']}", headers=other).json()
    assert copied["notes"] == "topo sort" and copied["status"] == "Solved" and copied["tags"] == ["graph"]
    assert copied["is_bookmarked"] and len(copied["solutions"]) == 1 and copied["id"] != q["id"]
    # Activity history restored into an empty account -> streak preserved.
    assert client.get("/api/progress/activity", params={"days": 7}, headers=other).json()["current_streak"] == 1

    # Importing twice never overwrites; it creates a second copy.
    client.post("/api/auth/import", content=export, headers={**other, "Content-Type": "application/json"})
    assert len(client.get("/api/folders/tree", headers=other).json()) == 2


def test_import_rejects_bad_files(client, auth):
    post = lambda body: client.post("/api/auth/import", content=body, headers={**auth, "Content-Type": "application/json"})
    assert post(b"not json").status_code == 400
    assert post(b'{"format": "something-else"}').status_code == 400
    assert post(b'{"format": "makepattern-export", "version": 9}').status_code == 400
    assert post(b'{"format": "makepattern-export", "version": 1, "questions": "nope"}').status_code == 400
    big = b'{"format":"makepattern-export","version":1,"x":"' + b"a" * (10 * 1024 * 1024) + b'"}'
    assert post(big).status_code == 413
    # Hostile values are coerced, not stored verbatim.
    weird = b'{"format":"makepattern-export","version":1,"questions":[{"id":"1","title":"t","status":"Hacked","difficulty":"Insane","attempts":"lots"}]}'
    assert post(weird).status_code == 200
    q = client.get("/api/questions/", headers=auth).json()[0]
    assert (q["status"], q["difficulty"], q["attempts"]) == ("Not Started", "Medium", 0)


# ---------------------------------------------------------------------------
# Offline review sync
# ---------------------------------------------------------------------------

def test_offline_review_batch_is_ordered_and_idempotent(client, auth):
    q = make_question(client, auth)
    client.put(f"/api/questions/{q['id']}", json={"status": "Needs Revision"}, headers=auth)
    now = datetime.now(timezone.utc)
    body = {"reviews": [
        {"client_id": "c2", "question_id": q["id"], "rating": "good", "reviewed_at": (now - timedelta(hours=1)).isoformat()},
        {"client_id": "c1", "question_id": q["id"], "rating": "again", "reviewed_at": (now - timedelta(hours=2)).isoformat()},
        {"client_id": "c3", "question_id": "missing", "rating": "good", "reviewed_at": now.isoformat()},
    ]}
    r = client.post("/api/reviews/batch", json=body, headers=auth).json()
    assert r["applied"] == 2 and [x["status"] for x in r["results"]] == ["applied", "applied", "not_found"]
    item = client.get(f"/api/questions/{q['id']}", headers=auth).json()
    assert item["status"] == "Solved" and item["review_count"] == 2  # again then good, in time order
    again = client.post("/api/reviews/batch", json=body, headers=auth).json()
    assert again["applied"] == 0 and {x["status"] for x in again["results"]} == {"duplicate", "not_found"}


def test_offline_review_older_than_latest_is_stale(client, auth):
    q = make_question(client, auth)
    client.post(f"/api/reviews/{q['id']}", json={"rating": "good"}, headers=auth)
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    r = client.post("/api/reviews/batch", json={"reviews": [{"client_id": "x", "question_id": q["id"], "rating": "again", "reviewed_at": old}]}, headers=auth).json()
    assert r["results"][0]["status"] == "stale"
    assert client.get(f"/api/questions/{q['id']}", headers=auth).json()["status"] == "Solved"


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def test_preferences_defaults_partial_update_and_validation(client, auth):
    p = client.get("/api/auth/preferences", headers=auth).json()
    assert p["theme"] == "dark" and p["editor_font_size"] == 14 and p["shortcuts_enabled"] is True
    p = client.put("/api/auth/preferences", json={"theme": "light", "font_family": "dyslexic"}, headers=auth).json()
    assert p["theme"] == "light" and p["font_family"] == "dyslexic" and p["editor_theme"] == "vs-dark"
    p = client.put("/api/auth/preferences", json={"high_contrast": True}, headers=auth).json()
    assert p["theme"] == "light" and p["high_contrast"] is True
    assert client.put("/api/auth/preferences", json={"editor_font_size": 99}, headers=auth).status_code == 422
    assert client.put("/api/auth/preferences", json={"theme": "neon"}, headers=auth).status_code == 422
