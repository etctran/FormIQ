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

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _elbow_trajectory_frames(raw_elbow_angles: list[float]) -> list[dict[int, tuple]]:
    """Overrides driving WRIST position so the RAW angle(shoulder,elbow,
    wrist) follows `raw_elbow_angles` (increasing toward peak for this
    exercise — the profile inverts it internally to get the primary
    signal)."""
    shoulder_l, elbow_l = neutral_xy(L_SHOULDER), neutral_xy(L_ELBOW)
    shoulder_r, elbow_r = neutral_xy(R_SHOULDER), neutral_xy(R_ELBOW)
    overrides_sequence = []
    for angle in raw_elbow_angles:
        wrist_l = point_at_angle(elbow_l, shoulder_l, angle, length=160.0)
        wrist_r = point_at_angle(elbow_r, shoulder_r, angle, length=160.0)
        overrides_sequence.append({L_WRIST: kp(*wrist_l), R_WRIST: kp(*wrist_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(60.0, 175.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=60.0, rest_frames=REST_FRAMES
    )
    return _elbow_trajectory_frames(angles)


def test_clean_overhead_press_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.OVERHEAD_PRESS, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_incomplete_lockout_fires_when_peak_never_reaches_extension() -> None:
    angles = repeat_trajectory(
        linspace_rep(60.0, 140.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=60.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.OVERHEAD_PRESS, frames)
    assert len(reps) >= 1
    assert "incomplete_lockout" in reps[0].faults


def test_excessive_back_lean_fires_when_shoulder_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    hip_x, hip_y = neutral_xy(L_HIP)
    for i in active:
        overrides[i][L_SHOULDER] = kp(hip_x + 150.0, hip_y - 300.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.OVERHEAD_PRESS, frames)
    assert len(reps) >= 1
    assert "excessive_back_lean" in reps[0].faults


def test_uneven_press_fires_when_one_wrist_offset_vertically() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    for i in active:
        x, y = overrides[i][R_WRIST][0], overrides[i][R_WRIST][1]
        overrides[i][R_WRIST] = kp(x, y + 100.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.OVERHEAD_PRESS, frames)
    assert len(reps) >= 1
    assert "uneven_press" in reps[0].faults
