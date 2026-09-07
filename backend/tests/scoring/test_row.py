import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    active_frame_offsets,
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
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _elbow_trajectory_frames(elbow_angles: list[float]) -> list[dict[int, tuple]]:
    shoulder_l, elbow_l = neutral_xy(L_SHOULDER), neutral_xy(L_ELBOW)
    shoulder_r, elbow_r = neutral_xy(R_SHOULDER), neutral_xy(R_ELBOW)
    overrides_sequence = []
    for angle in elbow_angles:
        wrist_l = point_at_angle(elbow_l, shoulder_l, angle, length=160.0)
        wrist_r = point_at_angle(elbow_r, shoulder_r, angle, length=160.0)
        overrides_sequence.append({L_WRIST: kp(*wrist_l), R_WRIST: kp(*wrist_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _elbow_trajectory_frames(angles)


def test_clean_row_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.ROW, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_insufficient_pull_fires_on_shallow_trajectory() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 130.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.ROW, frames)
    assert len(reps) >= 1
    assert "insufficient_pull" in reps[0].faults


def test_back_rounding_fires_when_hip_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    for i in active:
        # (360, 500)/(410, 500) only bends angle(shoulder,hip,knee) to
        # ~168 deg -- nowhere near the <150 threshold. (500, 500)/(550,
        # 500) bends it to ~113 deg, clearing the threshold with margin.
        overrides[i][L_HIP] = kp(500.0, 500.0)  # breaks shoulder-hip-knee collinearity
        overrides[i][R_HIP] = kp(550.0, 500.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.ROW, frames)
    assert len(reps) >= 1
    assert "back_rounding" in reps[0].faults


def test_torso_swing_fires_when_hip_offset_horizontally() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    shoulder_x, shoulder_y = neutral_xy(L_SHOULDER)
    for i in active:
        overrides[i][L_HIP] = kp(shoulder_x + 200.0, shoulder_y + 300.0)
        overrides[i][R_HIP] = kp(shoulder_x + 200.0, shoulder_y + 300.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.ROW, frames)
    assert len(reps) >= 1
    assert "torso_swing" in reps[0].faults
