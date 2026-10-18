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
