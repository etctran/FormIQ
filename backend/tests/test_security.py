"""The shared-secret guard: off when FORMIQ_API_KEY is unset, enforced on
every guarded route when it's set, /health open either way."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_no_key_configured_leaves_routes_open(monkeypatch) -> None:
    monkeypatch.delenv("FORMIQ_API_KEY", raising=False)
    assert client.get("/history").status_code == 200


def test_health_stays_open_when_key_configured(monkeypatch) -> None:
    monkeypatch.setenv("FORMIQ_API_KEY", "s3cret")
    assert client.get("/health").status_code == 200


def test_guarded_routes_reject_missing_and_wrong_key(monkeypatch) -> None:
    monkeypatch.setenv("FORMIQ_API_KEY", "s3cret")
    assert client.get("/history").status_code == 401
    assert client.get("/history", headers={"X-API-Key": "nope"}).status_code == 401
    assert client.delete("/history/1", headers={"X-API-Key": "nope"}).status_code == 401
    assert client.post("/analyze/squat", headers={"X-API-Key": "nope"}).status_code == 401


def test_correct_key_is_accepted(monkeypatch) -> None:
    monkeypatch.setenv("FORMIQ_API_KEY", "s3cret")
    assert client.get("/history", headers={"X-API-Key": "s3cret"}).status_code == 200
