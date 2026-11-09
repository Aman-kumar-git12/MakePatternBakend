"""Tests run against an in-memory MongoDB (mongomock). They never touch a real database."""
import os

os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["MONGODB_URI"] = "mongodb://invalid-test-host.invalid:1"  # any accidental real connection fails
os.environ["MONGODB_DB_NAME"] = "makepattern_test"

import mongomock  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db as db_module  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ratelimit import reset_rate_limits  # noqa: E402


@pytest.fixture()
def mdb():
    database = mongomock.MongoClient()["makepattern_test"]
    db_module.set_database_override(database)
    reset_rate_limits()
    yield database
    db_module.set_database_override(None)


@pytest.fixture()
def client(mdb):
    with TestClient(app) as c:
        yield c


def register(client, email="learner@fake.test", password="secret123", name=None):
    body = {"email": email, "password": password}
    if name:
        body["full_name"] = name
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def auth(client):
    data = register(client)
    return {"Authorization": f"Bearer {data['access_token']}"}
