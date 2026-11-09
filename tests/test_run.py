import httpx
import pytest

from app.config import settings
from app.services import judge0


@pytest.fixture()
def judge0_on(monkeypatch):
    monkeypatch.setattr(settings, "JUDGE0_URL", "https://judge0.example.test")
    monkeypatch.setattr(settings, "JUDGE0_API_KEY", "k3y")
    monkeypatch.setattr(settings, "JUDGE0_API_HOST", None)


def _mock_post(monkeypatch, handler):
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(judge0.httpx, "Client", factory)


def test_run_requires_auth(client):
    assert client.get("/api/run/config").status_code == 401
    assert client.post("/api/run/judge0", json={"language": "cpp", "code": "x"}).status_code == 401


def test_config_and_501_when_unconfigured(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "JUDGE0_URL", None)
    cfg = client.get("/api/run/config", headers=auth).json()
    assert cfg == {"judge0_enabled": False, "languages": ["python", "javascript"]}
    r = client.post("/api/run/judge0", json={"language": "cpp", "code": "int main(){}"}, headers=auth)
    assert r.status_code == 501 and "JUDGE0_URL" in r.json()["detail"]


def test_success_mapping_and_headers(client, auth, judge0_on, monkeypatch):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("x-auth-token")
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"status": {"id": 3, "description": "Accepted"}, "stdout": "3\n",
                                         "stderr": None, "compile_output": None, "time": "0.01", "memory": 3200})

    _mock_post(monkeypatch, handler)
    assert client.get("/api/run/config", headers=auth).json()["languages"] == ["python", "javascript", "cpp", "java"]
    r = client.post("/api/run/judge0", json={"language": "cpp", "code": "int main(){}", "stdin": "1 2"}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "Accepted", "stdout": "3\n", "stderr": "", "compile_output": "", "time": "0.01", "memory": 3200}
    assert "base64_encoded=false" in seen["url"] and "wait=true" in seen["url"]
    assert seen["token"] == "k3y" and '"language_id":54' in seen["body"].replace(" ", "")


def test_rapidapi_headers(client, auth, judge0_on, monkeypatch):
    monkeypatch.setattr(settings, "JUDGE0_API_HOST", "judge0-ce.p.rapidapi.com")
    seen = {}

    def handler(request: httpx.Request):
        seen.update(request.headers)
        return httpx.Response(200, json={"status": {"description": "Accepted"}})

    _mock_post(monkeypatch, handler)
    assert client.post("/api/run/judge0", json={"language": "java", "code": "class Main{}"}, headers=auth).status_code == 200
    assert seen["x-rapidapi-key"] == "k3y" and seen["x-rapidapi-host"] == "judge0-ce.p.rapidapi.com"


@pytest.mark.parametrize("status", [401, 429, 500])
def test_upstream_errors_map_to_502(client, auth, judge0_on, monkeypatch, status):
    _mock_post(monkeypatch, lambda request: httpx.Response(status, json={}))
    r = client.post("/api/run/judge0", json={"language": "cpp", "code": "x"}, headers=auth)
    assert r.status_code == 502


def test_network_error_maps_to_502(client, auth, judge0_on, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("boom")

    _mock_post(monkeypatch, handler)
    assert client.post("/api/run/judge0", json={"language": "cpp", "code": "x"}, headers=auth).status_code == 502


def test_validation(client, auth):
    assert client.post("/api/run/judge0", json={"language": "rust", "code": "x"}, headers=auth).status_code == 422
    assert client.post("/api/run/judge0", json={"language": "cpp", "code": "x" * 100_001}, headers=auth).status_code == 422
