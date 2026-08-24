from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import AnalysisResponse, Exercise

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
    assert body["frames"] == []


def test_analyze_rejects_unknown_exercise() -> None:
    response = client.post(
        "/analyze/not-a-real-exercise",
        files={"video": ("clip.mp4", b"x", "video/mp4")},
    )
    assert response.status_code == 422


def test_analyze_real_video_converts_frames() -> None:
    """Regression test: verify pybind11 Frame objects convert to Pydantic models.

    This test ensures that real cv_engine.Frame/cv_engine.Keypoint objects
    (extracted from actual video) can be passed to AnalysisResponse without
    Pydantic validation errors. This requires model_config = ConfigDict(from_attributes=True)
    on both Frame and Keypoint in keypoint.py.
    """
    import cv_engine

    fixture_path = (
        Path(__file__).parent.parent.parent / "cv-engine/tests/fixtures/sample_clip.mp4"
    )
    if not fixture_path.exists():
        pytest.skip("sample_clip.mp4 fixture not available")

    # Extract real frames from fixture
    frames = cv_engine.KeypointExtractor().extract(str(fixture_path))
    assert len(frames) > 0, "sample_clip.mp4 should produce at least one frame"

    # This would fail without model_config = ConfigDict(from_attributes=True)
    resp = AnalysisResponse(
        exercise=Exercise.SQUAT, frame_count=len(frames), reps=[], frames=frames
    )

    # Verify structure is correct — conversion succeeded for every frame,
    # regardless of which frames had a detection (that's a model-quality
    # question, not a conversion-correctness one).
    assert resp.frame_count == len(frames)
    assert len(resp.frames) == len(frames)
    for frame in resp.frames:
        assert frame.timestamp_sec >= 0.0
        assert len(frame.landmarks) in (0, 33)
        for landmark in frame.landmarks:
            assert isinstance(landmark.x, float)
            assert isinstance(landmark.y, float)
            assert isinstance(landmark.z, float)
            assert isinstance(landmark.visibility, float)
