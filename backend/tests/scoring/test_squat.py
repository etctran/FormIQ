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

L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_SHOULDER, R_SHOULDER = 11, 12
L_HEEL, R_HEEL = 29, 30
L_FOOT_INDEX, R_FOOT_INDEX = 31, 32

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _knee_trajectory_frames(knee_angles: list[float]) -> list[dict[int, tuple]]:
    """Overrides driving HIP position (per side) so angle(hip,knee,ankle)
    follows `knee_angles`, with KNEE/ANKLE fixed at their neutral pose."""
    knee_l, ankle_l = neutral_xy(L_KNEE), neutral_xy(L_ANKLE)
    knee_r, ankle_r = neutral_xy(R_KNEE), neutral_xy(R_ANKLE)
    overrides_sequence = []
    for angle in knee_angles:
        hip_l = point_at_angle(knee_l, ankle_l, angle, length=250.0)
        hip_r = point_at_angle(knee_r, ankle_r, angle, length=250.0)
        overrides_sequence.append({L_HIP: kp(*hip_l), R_HIP: kp(*hip_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _knee_trajectory_frames(angles)


def test_clean_squat_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.SQUAT, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_insufficient_depth_fires_on_shallow_trajectory() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 130.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_knee_trajectory_frames(angles))
    reps = analyze(Exercise.SQUAT, frames)
    assert len(reps) >= 1
    assert "insufficient_depth" in reps[0].faults


def test_forward_knee_travel_fires_when_foot_index_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    knee_l_x, _ = neutral_xy(L_KNEE)
    knee_l_y = neutral_xy(L_KNEE)[1]
    for i in active:
        # Foot index placed far behind the knee (knee travels well past it).
        overrides[i][L_FOOT_INDEX] = kp(knee_l_x - 200.0, knee_l_y + 20.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.SQUAT, frames)
    assert len(reps) >= 1
    assert "forward_knee_travel" in reps[0].faults


def test_back_rounding_fires_when_shoulder_collapses_relative_to_hip() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    knee_l, ankle_l = neutral_xy(L_KNEE), neutral_xy(L_ANKLE)
    knee_r, ankle_r = neutral_xy(R_KNEE), neutral_xy(R_ANKLE)
    active = set(active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0])
    overrides_sequence = []
    for local_i, angle in enumerate(angles):
        hip_l = point_at_angle(knee_l, ankle_l, angle, length=250.0)
        hip_r = point_at_angle(knee_r, ankle_r, angle, length=250.0)
        overrides = {L_HIP: kp(*hip_l), R_HIP: kp(*hip_r)}
        if local_i in active:
            # Shoulder placed to make angle(shoulder, hip, knee) ~ 120 deg
            # (a collapsed torso), computed relative to the CURRENT hip
            # position so it doesn't depend on where in the trajectory we are.
            shoulder_l = point_at_angle(hip_l, knee_l, 120.0, length=200.0)
            shoulder_r = point_at_angle(hip_r, knee_r, 120.0, length=200.0)
            overrides[L_SHOULDER] = kp(*shoulder_l)
            overrides[R_SHOULDER] = kp(*shoulder_r)
        overrides_sequence.append(overrides)
    frames = make_frames(overrides_sequence)
    reps = analyze(Exercise.SQUAT, frames)
    assert len(reps) >= 1
    assert "back_rounding" in reps[0].faults


def test_heel_rise_fires_when_heel_lifted() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    ankle_l_x, ankle_l_y = neutral_xy(L_ANKLE)
    for i in active:
        overrides[i][L_HEEL] = kp(ankle_l_x, ankle_l_y - 100.0)  # heel well above ankle
    frames = make_frames(overrides)
    reps = analyze(Exercise.SQUAT, frames)
    assert len(reps) >= 1
    assert "heel_rise" in reps[0].faults
