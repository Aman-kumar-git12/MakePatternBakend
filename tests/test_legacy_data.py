"""Documents shaped exactly as the old SQLite->Mongo sync layer wrote them must keep working."""
from bson import ObjectId

from app.services.security import hash_password


def seed_legacy(mdb):
    mdb.users.insert_one({
        "_id": ObjectId(), "id": "u-legacy", "email": "old@user.test", "full_name": "Old User",
        "hashed_password": hash_password("oldpass1"), "created_at": "2026-01-02T03:04:05.123456+00:00",
        "updated_at": "2026-01-02T03:04:05+00:00",
        "shared_patterns": [{"share_id": "legacyshare123", "folder_id": "f-root", "folder_name": "DSA", "is_active": True,
                             "created_at": "2026-01-02T00:00:00+00:00", "updated_at": "2026-01-02T00:00:00+00:00"}],
    })
    mdb.folders.insert_many([
        {"id": "f-root", "user_id": "u-legacy", "parent_id": None, "name": "DSA", "description": "", "tags": "[]", "position": 0,
         "created_at": "2026-01-02T00:00:00+00:00", "updated_at": "2026-01-02T00:00:00+00:00"},
        {"id": "f-arr", "user_id": "u-legacy", "parent_id": "f-root", "name": "Arrays", "description": "", "tags": "[\"easy\"]", "position": 0,
         "created_at": "2026-01-02T00:00:00", "updated_at": "2026-01-02T00:00:00"},
    ])
    mdb.questions.insert_one({
        "id": "q-legacy", "user_id": "u-legacy", "folder_id": "f-arr", "title": "Two Sum",
        "problem_url": "https://leetcode.com/problems/two-sum/description/", "problem_statement": "<p>Given nums...</p>",
        "notes": "use a hashmap", "difficulty": "Easy", "status": "Needs Revision", "tags": "[\"Array\", \"Hash Table\"]",
        "position": 0, "created_at": "2026-01-02T00:00:00+00:00", "updated_at": "2026-01-03T00:00:00+00:00",
    })
    mdb.solutions.insert_one({"id": "s-legacy", "question_id": "q-legacy", "title": "Hash", "solution_type": "Optimized",
                              "language": "cpp", "code": "int main(){}", "explanation": "", "time_complexity": "O(n)",
                              "space_complexity": "O(n)", "position": 0, "created_at": "2026-01-02T00:00:00+00:00",
                              "updated_at": "2026-01-02T00:00:00+00:00"})
    mdb.test_cases.insert_one({"id": "t-legacy", "question_id": "q-legacy", "title": "Case", "input": "[2,7]",
                               "expected_output": "[0,1]", "notes": "", "position": 0})
    mdb.bookmarks.insert_one({"id": "b-legacy", "user_id": "u-legacy", "question_id": "q-legacy"})


def test_legacy_documents_read_correctly(client, mdb):
    seed_legacy(mdb)
    from app.main import run_migrations
    run_migrations(mdb)

    r = client.post("/api/auth/login", json={"email": "old@user.test", "password": "oldpass1"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == "u-legacy"
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    tree = client.get("/api/folders/tree", headers=auth).json()
    assert tree[0]["subfolders"][0]["tags"] == ["easy"]
    q = client.get("/api/questions/q-legacy", headers=auth).json()
    assert q["tags"] == ["Array", "Hash Table"] and q["is_bookmarked"] is True
    assert q["folder_path"] == "DSA / Arrays"
    assert q["solutions"][0]["time_complexity"] == "O(n)" and q["test_cases"][0]["expected_output"] == "[0,1]"
    # Legacy "Needs Revision" questions are migrated into the review queue.
    assert client.get("/api/reviews/due", headers=auth).json()["due_count"] == 1
    # Edits keep working and tags are re-written as a list.
    client.put("/api/questions/q-legacy", json={"tags": ["Array"]}, headers=auth)
    assert mdb.questions.find_one({"id": "q-legacy"})["tags"] == ["Array"]
    assert client.get("/api/bookmarks/", headers=auth).status_code == 200
    assert client.get("/api/progress/summary", headers=auth).status_code == 200

    # Share created before snapshots existed is frozen on first public view, without the owner's id.
    pub = client.get("/api/shared/legacyshare123")
    assert pub.status_code == 200, pub.text
    sq = client.get("/api/shared/legacyshare123/questions/q-legacy").json()
    assert sq["user_id"] == "" and sq["notes"] == "use a hashmap"
    # Owner can manage the legacy share (positional update on an ObjectId user doc).
    off = client.patch("/api/folders/f-root/share", json={"is_active": False}, headers=auth)
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert client.get("/api/shared/legacyshare123").status_code == 404


def test_placeholder_password_cannot_log_in(client, mdb):
    mdb.users.insert_one({"_id": "u-x", "id": "u-x", "email": "synced@user.test", "hashed_password": "hashed_pwd_synced"})
    assert client.post("/api/auth/login", json={"email": "synced@user.test", "password": "hashed_pwd_synced"}).status_code == 401
