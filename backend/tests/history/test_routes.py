import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_list_and_delete_round_trip() -> None:
    create_response = client.post(
        "/history",
        json={"exercise": "squat", "date": "2026-09-01", "sets": 3, "reps": 8, "weight": 100.0},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["exercise"] == "squat"
    assert created["source"] == "manual"
    entry_id = created["id"]

    list_response = client.get("/history")
    assert list_response.status_code == 200
    assert any(e["id"] == entry_id for e in list_response.json())

    delete_response = client.delete(f"/history/{entry_id}")
    assert delete_response.status_code == 204

    list_after_delete = client.get("/history")
    assert all(e["id"] != entry_id for e in list_after_delete.json())


def test_create_rejects_invalid_body() -> None:
    response = client.post(
        "/history", json={"exercise": "squat", "date": "2026-09-01", "sets": 0, "reps": 8}
    )
    assert response.status_code == 422


def test_delete_nonexistent_entry_returns_404() -> None:
    response = client.delete("/history/999999")
    assert response.status_code == 404


def test_list_is_empty_when_no_entries_exist() -> None:
    response = client.get("/history")
    assert response.status_code == 200
    assert response.json() == []


def test_update_manual_entry_returns_200_with_updated_fields() -> None:
    create_response = client.post(
        "/history",
        json={"exercise": "squat", "date": "2026-09-01", "sets": 3, "reps": 8},
    )
    entry_id = create_response.json()["id"]

    update_response = client.patch(f"/history/{entry_id}", json={"sets": 5})
    assert update_response.status_code == 200
    body = update_response.json()
    assert body["sets"] == 5
    assert body["reps"] == 8


def test_update_nonexistent_entry_returns_404() -> None:
    response = client.patch("/history/999999", json={"sets": 5})
    assert response.status_code == 404


def test_update_video_entry_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    video_bytes = b"not a real video"
    analyze_response = client.post(
        "/analyze/squat", files={"video": ("clip.mp4", video_bytes, "video/mp4")}
    )
    assert analyze_response.status_code == 200

    history = client.get("/history").json()
    video_entry_id = next(e["id"] for e in history if e["source"] == "video")

    response = client.patch(f"/history/{video_entry_id}", json={"sets": 5})
    assert response.status_code == 400


def test_update_manual_entry_rejects_invalid_body() -> None:
    create_response = client.post(
        "/history",
        json={"exercise": "squat", "date": "2026-09-01", "sets": 3, "reps": 8},
    )
    entry_id = create_response.json()["id"]

    response = client.patch(f"/history/{entry_id}", json={"sets": 0})
    assert response.status_code == 422
