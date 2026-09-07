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
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_FOOT_INDEX, R_FOOT_INDEX = 31, 32

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _knee_trajectory_frames(knee_angles: list[float]) -> list[dict[int, tuple]]:
    """Both legs driven together (min_of(L, R) == the shared value), same
    construction as squat's. SHOULDER is also repositioned each frame,
    directly above the CURRENT (pivot-swept) HIP position, pinning
    horizontal_offset_metric(SHOULDER, HIP, ...) at 0 throughout: the
    single-DOF polar sweep of HIP around the KNEE pivot otherwise drags
    HIP sideways relative to a fixed-at-neutral SHOULDER, spuriously
    tripping torso_lean even in an otherwise clean rep."""
    knee_l, ankle_l = neutral_xy(L_KNEE), neutral_xy(L_ANKLE)
    knee_r, ankle_r = neutral_xy(R_KNEE), neutral_xy(R_ANKLE)
    overrides_sequence = []
    for angle in knee_angles:
        hip_l = point_at_angle(knee_l, ankle_l, angle, length=250.0)
        hip_r = point_at_angle(knee_r, ankle_r, angle, length=250.0)
        shoulder_l = (hip_l[0], hip_l[1] - 300.0)
        shoulder_r = (hip_r[0], hip_r[1] - 300.0)
        overrides_sequence.append(
            {
                L_HIP: kp(*hip_l),
                R_HIP: kp(*hip_r),
                L_SHOULDER: kp(*shoulder_l),
                R_SHOULDER: kp(*shoulder_r),
            }
        )
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _knee_trajectory_frames(angles)


def test_clean_lunge_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.LUNGE, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_insufficient_depth_fires_on_shallow_trajectory() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 130.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_knee_trajectory_frames(angles))
    reps = analyze(Exercise.LUNGE, frames)
    assert len(reps) >= 1
    assert "insufficient_depth" in reps[0].faults


def test_knee_over_toe_fires_when_foot_index_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    knee_l_x, knee_l_y = neutral_xy(L_KNEE)
    for i in active:
        overrides[i][L_FOOT_INDEX] = kp(knee_l_x - 200.0, knee_l_y + 20.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.LUNGE, frames)
    assert len(reps) >= 1
    assert "knee_over_toe" in reps[0].faults


def test_torso_lean_fires_when_shoulder_offset_relative_to_hip() -> None:
    # Built from the shared (now pivot-sweep-safe) clean trajectory, so the
    # only thing that can make torso_lean fire is the explicit shoulder
    # override below — not the underlying hip pivot sweep, which
    # _knee_trajectory_frames already cancels out by pinning SHOULDER
    # directly above HIP.
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    for i in active:
        hip_l = overrides[i][L_HIP][:2]
        hip_r = overrides[i][R_HIP][:2]
        overrides[i][L_SHOULDER] = kp(hip_l[0] + 150.0, hip_l[1] - 300.0)
        overrides[i][R_SHOULDER] = kp(hip_r[0] + 150.0, hip_r[1] - 300.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.LUNGE, frames)
    assert len(reps) >= 1
    assert "torso_lean" in reps[0].faults
