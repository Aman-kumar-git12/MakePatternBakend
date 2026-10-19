import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, SessionLocal
from app.services.seed_service import seed_demo_data
from app.services.security import hash_password
from app.models.user import User

TEST_EMAIL = "test_runner_ci@makepattern.dev"
TEST_PASSWORD = "password123"

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = db.query(User).filter(User.email == TEST_EMAIL).first()
    if not user:
        user = User(
            email=TEST_EMAIL,
            full_name="Test Runner",
            hashed_password=hash_password(TEST_PASSWORD)
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    from app.models.folder import Folder
    if db.query(Folder).filter(Folder.user_id == user.id).count() == 0:
        seed_demo_data(db, user)
    db.close()

@pytest.fixture
def client():
    with TestClient(app) as c:
        login_res = c.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_progress_summary(client):
    response = client.get("/api/progress/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_questions"] >= 0
    assert "difficulty_breakdown" in data
    assert "folder_overview" in data

def test_folder_tree_recursive(client):
    response = client.get("/api/folders/tree")
    assert response.status_code == 200
    tree = response.json()
    assert len(tree) > 0
    dsa_root = next((f for f in tree if f["name"] == "DSA"), None)
    assert dsa_root is not None
    sub_names = [sf["name"] for sf in dsa_root["subfolders"]]
    assert "Arrays" in sub_names

def test_create_and_move_folder_and_put_circular_prevention(client):
    # 1. Create hierarchy: f1 -> f2 -> f3
    res1 = client.post("/api/folders/", json={"name": "Test Algorithms", "position": 99})
    assert res1.status_code == 201
    f1 = res1.json()

    res2 = client.post("/api/folders/", json={"name": "Sub Level 1", "parent_id": f1["id"]})
    assert res2.status_code == 201
    f2 = res2.json()

    res3 = client.post("/api/folders/", json={"name": "Sub Level 2", "parent_id": f2["id"]})
    assert res3.status_code == 201
    f3 = res3.json()

    # 2. Circular move prevention via POST /move
    res_move_circular = client.post(f"/api/folders/{f1['id']}/move", json={"target_parent_id": f3["id"]})
    assert res_move_circular.status_code == 400

    # 3. Circular hierarchy prevention via PUT /folders/{id} (Item 2 fix verification)
    res_put_circular = client.put(f"/api/folders/{f1['id']}", json={"parent_id": f3["id"]})
    assert res_put_circular.status_code == 400
    assert "circular hierarchy" in res_put_circular.text

    # Moving into itself directly
    res_put_self = client.put(f"/api/folders/{f1['id']}", json={"parent_id": f1["id"]})
    assert res_put_self.status_code == 400

    # 4. Cleanup
    del_res = client.delete(f"/api/folders/{f1['id']}")
    assert del_res.status_code == 200

def test_unauthenticated_request_is_rejected():
    with TestClient(app) as unauth_client:
        # Protected route without token MUST return 401 (Item 1 fix verification)
        res = unauth_client.get("/api/folders/tree")
        assert res.status_code == 401
        assert "Not authenticated" in res.json()["detail"] or "Valid Bearer token required" in res.json()["detail"]

        # Invalid token MUST return 401
        unauth_client.headers.update({"Authorization": "Bearer invalid_or_forged_token"})
        res_invalid = unauth_client.get("/api/folders/tree")
        assert res_invalid.status_code == 401

def test_bookmark_toggle(client):
    questions_res = client.get("/api/questions/")
    assert questions_res.status_code == 200
    questions = questions_res.json()
    assert len(questions) > 0
    q_id = questions[0]["id"]

    toggle1 = client.post(f"/api/bookmarks/{q_id}/toggle")
    assert toggle1.status_code == 200
    res1 = toggle1.json()
    assert "is_bookmarked" in res1

    toggle2 = client.post(f"/api/bookmarks/{q_id}/toggle")
    assert toggle2.status_code == 200
    res2 = toggle2.json()
    assert res2["is_bookmarked"] != res1["is_bookmarked"]

def test_global_search(client):
    res = client.get("/api/search/?q=Two")
    assert res.status_code == 200
    data = res.json()
    assert "questions" in data
    assert any("Two" in q["title"] for q in data["questions"])

def test_mongodb_sync_integration(client):
    from app.mongodb import (
        get_folders_collection,
        get_questions_collection,
        get_solutions_collection,
        get_test_cases_collection,
        get_bookmarks_collection
    )
    folders_col = get_folders_collection()
    questions_col = get_questions_collection()
    solutions_col = get_solutions_collection()
    test_cases_col = get_test_cases_collection()
    bookmarks_col = get_bookmarks_collection()

    if folders_col is None:
        pytest.skip("MongoDB not running in test environment")

    # 1. Test Folder MongoDB sync
    f_res = client.post("/api/folders/", json={"name": "Mongo Sync Test Folder", "position": 100})
    assert f_res.status_code == 201
    f_data = f_res.json()
    f_id = f_data["id"]
    mongo_folder = folders_col.find_one({"id": f_id})
    assert mongo_folder is not None
    assert mongo_folder["name"] == "Mongo Sync Test Folder"

    # 2. Test Question MongoDB sync
    q_res = client.post("/api/questions/", json={
        "folder_id": f_id,
        "title": "Mongo Sync Test Question",
        "difficulty": "Hard",
        "status": "In Progress"
    })
    assert q_res.status_code == 201
    q_data = q_res.json()
    q_id = q_data["id"]
    mongo_q = questions_col.find_one({"id": q_id})
    assert mongo_q is not None
    assert mongo_q["title"] == "Mongo Sync Test Question"
    assert mongo_q["difficulty"] == "Hard"

    # 3. Test Solution MongoDB sync
    sol_res = client.post(f"/api/solutions/question/{q_id}", json={
        "title": "Mongo Optimized Solution",
        "language": "python",
        "code": "def solve(): return 42"
    })
    assert sol_res.status_code == 201
    sol_data = sol_res.json()
    sol_id = sol_data["id"]
    mongo_sol = solutions_col.find_one({"id": sol_id})
    assert mongo_sol is not None
    assert mongo_sol["title"] == "Mongo Optimized Solution"

    # 4. Test TestCase MongoDB sync
    tc_res = client.post(f"/api/test-cases/question/{q_id}", json={
        "title": "Sample TC 1",
        "input": "[1, 2, 3]",
        "expected_output": "6"
    })
    assert tc_res.status_code == 201
    tc_data = tc_res.json()
    tc_id = tc_data["id"]
    mongo_tc = test_cases_col.find_one({"id": tc_id})
    assert mongo_tc is not None
    assert mongo_tc["input"] == "[1, 2, 3]"

    # 5. Test Bookmark MongoDB sync
    bm_res = client.post(f"/api/bookmarks/{q_id}/toggle")
    assert bm_res.status_code == 200
    mongo_bm = bookmarks_col.find_one({"question_id": q_id})
    assert mongo_bm is not None

    bm_untoggle = client.post(f"/api/bookmarks/{q_id}/toggle")
    assert bm_untoggle.status_code == 200
    mongo_bm_after = bookmarks_col.find_one({"question_id": q_id})
    assert mongo_bm_after is None

    # 6. Cleanup via folder delete (which cascades to question, solutions, test cases)
    del_folder = client.delete(f"/api/folders/{f_id}")
    assert del_folder.status_code == 200
    assert folders_col.find_one({"id": f_id}) is None
    assert questions_col.find_one({"id": q_id}) is None
    assert solutions_col.find_one({"id": sol_id}) is None
    assert test_cases_col.find_one({"id": tc_id}) is None

