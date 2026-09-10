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


def test_analyze_invalid_video_returns_empty_reps() -> None:
    video_bytes = b"not a real video"
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


def test_analyze_returns_real_reps_for_synthetic_squat_video(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.scoring.fixtures import (
        kp,
        linspace_rep,
        make_frames,
        neutral_xy,
        point_at_angle,
        repeat_trajectory,
    )

    L_HIP, R_HIP = 23, 24
    L_KNEE, R_KNEE = 25, 26
    L_ANKLE, R_ANKLE = 27, 28
    L_SHOULDER, R_SHOULDER = 11, 12

    angles = repeat_trajectory(linspace_rep(170.0, 70.0, 20, 20), 2, rest_value=170.0, rest_frames=5)
    knee_l, ankle_l = neutral_xy(L_KNEE), neutral_xy(L_ANKLE)
    knee_r, ankle_r = neutral_xy(R_KNEE), neutral_xy(R_ANKLE)
    overrides_sequence = []
    for angle in angles:
        hip_l = point_at_angle(knee_l, ankle_l, angle, length=250.0)
        hip_r = point_at_angle(knee_r, ankle_r, angle, length=250.0)
        # SHOULDER must be repositioned relative to the swept HIP each frame
        # (angle(shoulder,hip,knee) pinned near its neutral ~170 deg value) —
        # see tests/scoring/test_squat.py::_knee_trajectory_frames — otherwise
        # a fixed-at-neutral SHOULDER spuriously trips back_rounding even in
        # an otherwise clean rep.
        shoulder_l = point_at_angle(hip_l, knee_l, 170.0, length=200.0)
        shoulder_r = point_at_angle(hip_r, knee_r, 170.0, length=200.0)
        overrides_sequence.append(
            {
                L_HIP: kp(*hip_l),
                R_HIP: kp(*hip_r),
                L_SHOULDER: kp(*shoulder_l),
                R_SHOULDER: kp(*shoulder_r),
            }
        )
    synthetic_frames = make_frames(overrides_sequence)

    class FakeExtractor:
        def extract(self, path: str) -> list:
            return synthetic_frames

    monkeypatch.setattr("app.api.routes.cv_engine.KeypointExtractor", FakeExtractor)

    response = client.post(
        "/analyze/squat",
        files={"video": ("clip.mp4", b"x", "video/mp4")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["frame_count"] == len(synthetic_frames)
    assert len(body["reps"]) == 2
    for rep in body["reps"]:
        assert rep["faults"] == []
        assert rep["form_accuracy"] == pytest.approx(1.0)


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


def test_analyze_auto_logs_history_entry() -> None:
    video_bytes = b"not a real video, scaffolding stub"
    response = client.post(
        "/analyze/squat",
        files={"video": ("clip.mp4", video_bytes, "video/mp4")},
    )
    assert response.status_code == 200

    history_response = client.get("/history")
    assert history_response.status_code == 200
    entries = history_response.json()
    assert any(e["exercise"] == "squat" and e["source"] == "video" for e in entries)


def test_analyze_still_succeeds_if_history_logging_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import routes as routes_module

    def _raise(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(routes_module.service, "log_video_entry", _raise)

    response = client.post(
        "/analyze/squat",
        files={"video": ("clip.mp4", b"not a real video", "video/mp4")},
    )
    assert response.status_code == 200
    assert response.json()["exercise"] == "squat"
