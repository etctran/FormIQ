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


def _elbow_trajectory_frames(elbow_angles: list[float]) -> list[dict[int, tuple]]:
    """Overrides driving WRIST position (per side) so
    angle(shoulder,elbow,wrist) follows `elbow_angles`, SHOULDER/ELBOW
    fixed."""
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


def test_clean_bench_press_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.BENCH_PRESS, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_uneven_bar_path_fires_when_one_wrist_offset_vertically() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    for i in active:
        x, y = overrides[i][R_WRIST][0], overrides[i][R_WRIST][1]
        overrides[i][R_WRIST] = kp(x, y + 100.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.BENCH_PRESS, frames)
    assert len(reps) >= 1
    assert "uneven_bar_path" in reps[0].faults


def test_partial_lockout_fires_when_rest_never_reaches_extension() -> None:
    angles = repeat_trajectory(
        linspace_rep(150.0, 70.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=150.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.BENCH_PRESS, frames)
    assert len(reps) >= 1
    assert "partial_lockout" in reps[0].faults


def test_flared_elbows_fires_when_elbow_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    shoulder_x, shoulder_y = neutral_xy(L_SHOULDER)
    for i in active:
        overrides[i][L_ELBOW] = kp(shoulder_x - 250.0, shoulder_y + 100.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.BENCH_PRESS, frames)
    assert len(reps) >= 1
    assert "flared_elbows" in reps[0].faults
