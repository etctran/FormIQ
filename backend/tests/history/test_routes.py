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
