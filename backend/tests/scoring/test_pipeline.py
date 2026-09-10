import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    kp,
    linspace_rep,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)

L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _pushup_elbow_overrides(elbow_angles: list[float]) -> list[dict[int, tuple]]:
    shoulder_l, elbow_l = neutral_xy(L_SHOULDER), neutral_xy(L_ELBOW)
    shoulder_r, elbow_r = neutral_xy(R_SHOULDER), neutral_xy(R_ELBOW)
    overrides_sequence = []
    for angle in elbow_angles:
        wrist_l = point_at_angle(elbow_l, shoulder_l, angle, length=160.0)
        wrist_r = point_at_angle(elbow_r, shoulder_r, angle, length=160.0)
        overrides_sequence.append({L_WRIST: kp(*wrist_l), R_WRIST: kp(*wrist_r)})
    return overrides_sequence


def test_too_few_frames_returns_empty() -> None:
    angles = [170.0] * 5  # under MIN_FRAMES
    frames = make_frames(_pushup_elbow_overrides(angles))
    assert analyze(Exercise.PUSHUP, frames) == []


def test_no_completed_rep_returns_empty() -> None:
    angles = [170.0] * 5 + linspace_rep(170.0, 70.0, 20, 20)[:20]  # descends, never returns
    frames = make_frames(_pushup_elbow_overrides(angles))
    assert analyze(Exercise.PUSHUP, frames) == []


def test_clean_two_rep_video_returns_two_reps() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), 2, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_pushup_elbow_overrides(angles))
    reps = analyze(Exercise.PUSHUP, frames)
    assert len(reps) == 2
    assert [r.rep_index for r in reps] == [0, 1]
    assert reps[0].end_sec <= reps[1].start_sec


def test_low_visibility_gap_still_detects_reps_around_it() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), 2, rest_value=170.0, rest_frames=REST_FRAMES
    )
    overrides = _pushup_elbow_overrides(angles)
    # Zero out wrist visibility for > 1s (30+ frames at 30fps) between the
    # two reps' rest padding.
    gap_start = REST_FRAMES + FRAMES_DOWN + FRAMES_UP
    for i in range(gap_start, gap_start + 32):
        overrides[i][L_WRIST] = (0.0, 0.0, 0.0, 0.0)
        overrides[i][R_WRIST] = (0.0, 0.0, 0.0, 0.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.PUSHUP, frames)
    assert len(reps) >= 1  # at least the first rep, unaffected by the later gap


def test_scoring_failure_is_caught_and_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scoring.pipeline as pipeline_module

    def _boom(exercise, frames):  # noqa: ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline_module, "_analyze", _boom)
    angles = repeat_trajectory(linspace_rep(170.0, 70.0, 20, 20), 1, rest_value=170.0, rest_frames=5)
    frames = make_frames(_pushup_elbow_overrides(angles))
    assert analyze(Exercise.PUSHUP, frames) == []
