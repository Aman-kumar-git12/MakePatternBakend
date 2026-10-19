import httpx
import uuid
import sys

BASE_URL = "http://localhost:8000/api"
client = httpx.Client()

def test_full_sharing_feature():
    print("=== STARTING FULL SHARING FEATURE E2E TESTS ===")
    
    # 1. Register User A
    user_a_email = f"user_{uuid.uuid4().hex[:6]}@example.com"
    user_a_pwd = "Password@1234"
    res = client.post(f"{BASE_URL}/auth/register", json={
        "email": user_a_email,
        "password": user_a_pwd,
        "full_name": "Alice Turing"
    })
    assert res.status_code == 200, f"Register A failed: {res.text}"
    token_a = res.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    print("✓ User A registered and logged in")

    # 2. Register User B (for cross-user ownership tests)
    user_b_email = f"user_{uuid.uuid4().hex[:6]}@example.com"
    res = client.post(f"{BASE_URL}/auth/register", json={
        "email": user_b_email,
        "password": "Password@1234",
        "full_name": "Bob Babbage"
    })
    assert res.status_code == 200, f"Register B failed: {res.text}"
    token_b = res.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}
    print("✓ User B registered and logged in")

    # 3. User A creates Topic -> Subtopic -> Question
    res = client.post(f"{BASE_URL}/folders/", json={
        "name": "Dynamic Programming",
        "description": "Mastering 1D and 2D DP patterns",
        "tags": ["DP", "Algorithms"]
    }, headers=headers_a)
    assert res.status_code == 201, f"Create Topic failed: {res.text}"
    topic_id = res.json()["id"]
    print(f"✓ Created Topic: {topic_id}")

    res = client.post(f"{BASE_URL}/folders/", json={
        "name": "1D DP",
        "parent_id": topic_id,
        "description": "Fibonacci, Climbing Stairs, House Robber"
    }, headers=headers_a)
    assert res.status_code == 201, f"Create Subtopic failed: {res.text}"
    subtopic_id = res.json()["id"]
    print(f"✓ Created Subtopic: {subtopic_id}")

    # Add question inside subtopic
    res = client.post(f"{BASE_URL}/questions/", json={
        "folder_id": subtopic_id,
        "title": "Climbing Stairs",
        "difficulty": "Easy",
        "status": "Solved",
        "problem_statement": "You are climbing a staircase. It takes n steps to reach the top.",
        "notes": "dp[i] = dp[i-1] + dp[i-2]",
        "tags": ["DP", "Easy"],
        "problem_url": "https://leetcode.com/problems/climbing-stairs/"
    }, headers=headers_a)
    assert res.status_code == 201, f"Create Question failed: {res.text}"
    q_id = res.json()["id"]
    print(f"✓ Created Question: {q_id}")

    # Add solution to question
    res = client.post(f"{BASE_URL}/solutions/question/{q_id}", json={
        "title": "Space-Optimized DP",
        "language": "python",
        "code": "def climbStairs(n):\n    a, b = 1, 1\n    for _ in range(n - 1):\n        a, b = b, a + b\n    return b",
        "time_complexity": "O(N)",
        "space_complexity": "O(1)",
        "explanation": "Only keeping last two states."
    }, headers=headers_a)
    assert res.status_code == 201, f"Create Solution failed: {res.text}"
    print("✓ Added Solution to Question")

    # Also add an unrelated private question in a separate folder for User A
    res = client.post(f"{BASE_URL}/folders/", json={
        "name": "Secret Folder",
        "description": "Should never be visible via DP share link"
    }, headers=headers_a)
    secret_folder_id = res.json()["id"]
    res = client.post(f"{BASE_URL}/questions/", json={
        "folder_id": secret_folder_id,
        "title": "Private Problem",
        "difficulty": "Hard",
        "status": "Not Started"
    }, headers=headers_a)
    secret_q_id = res.json()["id"]
    print("✓ Created separate unshared question in secret folder")

    # 4. Test Share Creation
    res = client.post(f"{BASE_URL}/folders/{topic_id}/share", headers=headers_a)
    assert res.status_code == 200, f"Share create failed: {res.text}"
    share_info = res.json()
    share_id = share_info["share_id"]
    assert share_info["is_active"] is True
    assert share_info["folder_name"] == "Dynamic Programming"
    print(f"✓ Share link created successfully: {share_id}")

    # 5. Test Ownership Enforcement
    # User B tries to view share settings of User A's topic -> 404 / 403
    res = client.get(f"{BASE_URL}/folders/{topic_id}/share", headers=headers_b)
    assert res.status_code in [403, 404], f"User B should not access User A's share settings! Got {res.status_code}"
    print("✓ Ownership verified: User B cannot access User A's share configuration")

    # User B tries to disable User A's share link
    res = client.patch(f"{BASE_URL}/folders/{topic_id}/share", json={"is_active": False}, headers=headers_b)
    assert res.status_code in [403, 404], f"User B should not be able to modify User A's share! Got {res.status_code}"
    print("✓ Ownership verified: User B cannot update User A's share status")

    # User B tries to revoke User A's share link
    res = client.post(f"{BASE_URL}/folders/{topic_id}/share/revoke", headers=headers_b)
    assert res.status_code in [403, 404], f"User B should not be able to revoke User A's share! Got {res.status_code}"
    print("✓ Ownership verified: User B cannot revoke User A's share link")

    # 6. Test Public Read-Only Access (Unauthenticated)
    # No Auth Header:
    res = client.get(f"{BASE_URL}/shared/{share_id}")
    assert res.status_code == 200, f"Public shared GET failed: {res.text}"
    public_data = res.json()
    assert public_data["share_id"] == share_id
    assert public_data["owner_name"] == "Alice Turing"
    # Ensure sensitive fields are NOT exposed
    assert "password" not in str(public_data).lower()
    assert "email" not in str(public_data).lower()
    
    # Check tree structure
    pattern = public_data["pattern"]
    assert pattern["name"] == "Dynamic Programming"
    assert len(pattern["subfolders"]) == 1
    subfolder = pattern["subfolders"][0]
    assert subfolder["name"] == "1D DP"
    assert len(subfolder["questions"]) == 1
    assert subfolder["questions"][0]["title"] == "Climbing Stairs"
    print("✓ Public read-only pattern retrieved with full topics/subtopics/questions hierarchy")

    # Test Public Read-Only Question Details
    res = client.get(f"{BASE_URL}/shared/{share_id}/questions/{q_id}")
    assert res.status_code == 200, f"Public question GET failed: {res.text}"
    q_data = res.json()
    assert q_data["title"] == "Climbing Stairs"
    assert len(q_data["solutions"]) == 1
    assert "climbStairs" in q_data["solutions"][0]["code"]
    print("✓ Public read-only question and solution details retrieved successfully")

    # Test Security: Attempt to fetch question outside of shared folder using this share_id
    res = client.get(f"{BASE_URL}/shared/{share_id}/questions/{secret_q_id}")
    assert res.status_code in [403, 404], f"Should forbid access to unshared question! Got {res.status_code}"
    print("✓ Strict scoping verified: Unshared question blocked under share_id")

    # 7. Test Disabling the Share Link
    res = client.patch(f"{BASE_URL}/folders/{topic_id}/share", json={"is_active": False}, headers=headers_a)
    assert res.status_code == 200
    assert res.json()["is_active"] is False
    print("✓ Owner disabled share link")

    # Verify public access is now BLOCKED
    res = client.get(f"{BASE_URL}/shared/{share_id}")
    assert res.status_code == 404, f"Disabled share link must return 404! Got {res.status_code}"
    res = client.get(f"{BASE_URL}/shared/{share_id}/questions/{q_id}")
    assert res.status_code == 404, f"Disabled share question access must return 404! Got {res.status_code}"
    print("✓ Verified: Disabled share link is rejected with 404")

    # 8. Test Re-enabling the Share Link
    res = client.patch(f"{BASE_URL}/folders/{topic_id}/share", json={"is_active": True}, headers=headers_a)
    assert res.status_code == 200
    assert res.json()["is_active"] is True
    res = client.get(f"{BASE_URL}/shared/{share_id}")
    assert res.status_code == 200
    print("✓ Re-enabled share link and verified restored access")

    # 9. Test Live Updates (No Data Duplication)
    # User A adds a new question to the pattern
    res = client.post(f"{BASE_URL}/questions/", json={
        "folder_id": subtopic_id,
        "title": "House Robber",
        "difficulty": "Medium",
        "status": "In Progress"
    }, headers=headers_a)
    assert res.status_code == 201

    # Check public view immediately sees it without any duplicate copy
    res = client.get(f"{BASE_URL}/shared/{share_id}")
    assert res.status_code == 200
    sub_questions = res.json()["pattern"]["subfolders"][0]["questions"]
    q_titles = [q["title"] for q in sub_questions]
    assert "House Robber" in q_titles, f"Expected House Robber in {q_titles}"
    print("✓ Live synchronization verified: Owner's addition immediately visible in shared link")

    # 10. Test Revocation
    res = client.post(f"{BASE_URL}/folders/{topic_id}/share/revoke", headers=headers_a)
    assert res.status_code == 200
    new_share_info = res.json()
    new_share_id = new_share_info["share_id"]
    assert new_share_id != share_id, "Revoked share must yield a new share_id"
    print(f"✓ Revoked old link {share_id}, new link issued: {new_share_id}")

    # Old share_id must now return 404
    res = client.get(f"{BASE_URL}/shared/{share_id}")
    assert res.status_code == 404, f"Old share_id must return 404! Got {res.status_code}"
    print("✓ Verified: Revoked old link is dead (404)")

    # New share_id works
    res = client.get(f"{BASE_URL}/shared/{new_share_id}")
    assert res.status_code == 200
    print("✓ Verified: New share link is live and accessible")

    # 11. Test Invalid Share Link
    res = client.get(f"{BASE_URL}/shared/invalid-fake-share-id-99999")
    assert res.status_code == 404
    print("✓ Verified: Invalid share link returns 404")

    # 12. Test Sharing the Whole List of Topics ("All Patterns")
    print("\n--- Testing Sharing Whole List of Topics (All Patterns) ---")
    res = client.post(f"{BASE_URL}/folders/all/share", headers=headers_a)
    assert res.status_code == 200, f"Share all failed: {res.text}"
    all_share_info = res.json()
    all_share_id = all_share_info["share_id"]
    assert all_share_info["folder_id"] == "all"
    assert all_share_info["folder_name"] == "All Patterns"
    assert all_share_info["is_active"] is True
    print(f"✓ Created Share link for all topics: {all_share_id}")

    # Public Unauthenticated Access to Whole List of Topics
    res = client.get(f"{BASE_URL}/shared/{all_share_id}")
    assert res.status_code == 200, f"Get all shared failed: {res.text}"
    all_public_data = res.json()
    assert all_public_data["share_id"] == all_share_id
    assert all_public_data["owner_name"] == "Alice Turing"
    assert all_public_data["share_type"] == "all"
    assert "patterns" in all_public_data
    # Alice has 'Dynamic Programming' and 'Secret Folder'
    pattern_names = [p["name"] for p in all_public_data["patterns"]]
    assert "Dynamic Programming" in pattern_names, f"Expected DP in {pattern_names}"
    assert "Secret Folder" in pattern_names, f"Expected Secret Folder in {pattern_names}"
    print(f"✓ Retrieved all topics in read-only public view: {pattern_names}")

    # Can inspect questions across any topic in the collection
    res = client.get(f"{BASE_URL}/shared/{all_share_id}/questions/{q_id}")
    assert res.status_code == 200
    assert res.json()["title"] == "Climbing Stairs"
    print("✓ Question inspection verified within all topics share link")

    # Disable all topics sharing
    res = client.patch(f"{BASE_URL}/folders/all/share", json={"is_active": False}, headers=headers_a)
    assert res.status_code == 200
    res = client.get(f"{BASE_URL}/shared/{all_share_id}")
    assert res.status_code == 404
    print("✓ Disabling all topics share link verified (404)")

    # Re-enable all topics sharing
    res = client.patch(f"{BASE_URL}/folders/all/share", json={"is_active": True}, headers=headers_a)
    assert res.status_code == 200
    res = client.get(f"{BASE_URL}/shared/{all_share_id}")
    assert res.status_code == 200
    print("✓ Re-enabling all topics share link verified (200)")

    # Revoke all topics share link
    res = client.post(f"{BASE_URL}/folders/all/share/revoke", headers=headers_a)
    assert res.status_code == 200
    new_all_share_id = res.json()["share_id"]
    assert new_all_share_id != all_share_id
    res = client.get(f"{BASE_URL}/shared/{all_share_id}")
    assert res.status_code == 404
    res = client.get(f"{BASE_URL}/shared/{new_all_share_id}")
    assert res.status_code == 200
    print("✓ Revocation for all topics share link verified")

    print("\n🎉 ALL SHARING FEATURE TESTS PASSED SUCCESSFULLY! 🎉\n")

if __name__ == "__main__":
    test_full_sharing_feature()

