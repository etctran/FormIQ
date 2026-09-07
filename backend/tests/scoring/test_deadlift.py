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

NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _hinge_trajectory_frames(hip_angles: list[float]) -> list[dict[int, tuple]]:
    """Overrides driving SHOULDER position (per side) so
    angle(shoulder,hip,knee) follows `hip_angles`, with HIP/KNEE fixed."""
    hip_l, knee_l = neutral_xy(L_HIP), neutral_xy(L_KNEE)
    hip_r, knee_r = neutral_xy(R_HIP), neutral_xy(R_KNEE)
    overrides_sequence = []
    for angle in hip_angles:
        shoulder_l = point_at_angle(hip_l, knee_l, angle, length=300.0)
        shoulder_r = point_at_angle(hip_r, knee_r, angle, length=300.0)
        overrides_sequence.append({L_SHOULDER: kp(*shoulder_l), R_SHOULDER: kp(*shoulder_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 80.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _hinge_trajectory_frames(angles)


def test_clean_deadlift_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.DEADLIFT, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_back_rounding_fires_when_nose_collapses_relative_to_shoulder() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 80.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    hip_l, knee_l = neutral_xy(L_HIP), neutral_xy(L_KNEE)
    active = set(active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0])
    overrides_sequence = []
    for local_i, angle in enumerate(angles):
        shoulder_l = point_at_angle(hip_l, knee_l, angle, length=300.0)
        shoulder_r = shoulder_l  # symmetric enough for this test
        overrides = {L_SHOULDER: kp(*shoulder_l), R_SHOULDER: kp(*shoulder_r)}
        if local_i in active:
            nose = point_at_angle(shoulder_l, hip_l, 140.0, length=150.0)
            overrides[NOSE] = kp(*nose)
        overrides_sequence.append(overrides)
    frames = make_frames(overrides_sequence)
    reps = analyze(Exercise.DEADLIFT, frames)
    assert len(reps) >= 1
    assert "back_rounding" in reps[0].faults


def test_bar_path_drift_fires_when_wrist_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    hip_x, hip_y = neutral_xy(L_HIP)
    for i in active:
        overrides[i][L_WRIST] = kp(hip_x + 150.0, hip_y + 50.0)  # bar drifting away from hip
    frames = make_frames(overrides)
    reps = analyze(Exercise.DEADLIFT, frames)
    assert len(reps) >= 1
    assert "bar_path_drift" in reps[0].faults


def test_hyperextension_lockout_fires_when_wrist_overridden_at_rest() -> None:
    overrides = _clean_overrides(num_reps=1)
    hip_x, hip_y = neutral_xy(L_HIP)
    for i in range(len(overrides)):  # whole sequence, incl. REST padding
        overrides[i][L_WRIST] = kp(hip_x + 150.0, hip_y + 50.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.DEADLIFT, frames)
    assert len(reps) >= 1
    assert "hyperextension_lockout" in reps[0].faults
