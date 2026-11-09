import mongomock
import pytest
from fastapi import HTTPException

from app.services.curricula import CURRICULA, all_problems, import_curriculum, list_curricula


def test_curricula_integrity():
    ids = [c["id"] for c in CURRICULA]
    assert len(ids) == len(set(ids))
    for c in CURRICULA:
        probs = all_problems(c)
        slugs = [p[1] for p in probs]
        fids = [p[0] for p in probs]
        assert len(slugs) == len(set(slugs)), f"duplicate slug in {c['id']}"
        assert len(fids) == len(set(fids)), f"duplicate id in {c['id']}"
        for fid, slug, title, diff in probs:
            assert fid.isdigit() and slug and title
            assert diff in ("Easy", "Medium", "Hard")
        names = [n for n, _ in c["patterns"]]
        assert len(names) == len(set(names))
        assert all(problems for _, problems in c["patterns"])


def test_list_curricula_shape():
    info = {c["id"]: c for c in list_curricula()}
    assert info["core-interview-patterns"]["problem_count"] >= 80
    assert info["beginner-foundations"]["problem_count"] >= 30
    assert "Sliding Window" in info["core-interview-patterns"]["patterns"]


def test_import_creates_tree_and_skips_tracked():
    db = mongomock.MongoClient().db
    res = import_curriculum(db, "u1", "beginner-foundations", tracked={"fizz-buzz": "q-existing"})
    total = len(all_problems(next(c for c in CURRICULA if c["id"] == "beginner-foundations")))
    assert res["questions_imported"] == total - 1
    root = db.folders.find_one({"id": res["folder_id"]})
    assert root["parent_id"] is None and root["name"] == "Beginner Foundations"
    subs = list(db.folders.find({"parent_id": root["id"]}))
    assert len(subs) == 7
    q = db.questions.find_one({"leetcode_slug": "running-sum-of-1d-array"})
    assert q["leetcode_id"] == "1480" and q["problem_url"].endswith("/running-sum-of-1d-array/")
    assert q["user_id"] == "u1" and q["status"] == "Not Started"
    assert db.questions.find_one({"leetcode_slug": "fizz-buzz"}) is None

    # Second import of everything already tracked returns the existing root
    tracked = {q["leetcode_slug"]: q["id"] for q in db.questions.find()} | {"fizz-buzz": "q-existing"}
    again = import_curriculum(db, "u1", "beginner-foundations", tracked=tracked)
    assert again == {"folder_id": root["id"], "folder_name": "Beginner Foundations", "questions_imported": 0}


def test_import_unknown_curriculum():
    with pytest.raises(HTTPException) as e:
        import_curriculum(mongomock.MongoClient().db, "u1", "nope", {})
    assert e.value.status_code == 404
