from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_stub_returns_empty_reps() -> None:
    video_bytes = b"not a real video, scaffolding stub"
    response = client.post(
        "/analyze/squat",
        files={"video": ("clip.mp4", video_bytes, "video/mp4")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exercise"] == "squat"
    assert body["reps"] == []
    assert body["frame_count"] == 0


def test_analyze_rejects_unknown_exercise() -> None:
    response = client.post(
        "/analyze/not-a-real-exercise",
        files={"video": ("clip.mp4", b"x", "video/mp4")},
    )
    assert response.status_code == 422
