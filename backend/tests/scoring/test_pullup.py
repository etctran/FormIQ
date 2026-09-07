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
    fixed. The right wrist reuses the SAME elbow->wrist offset vector as
    the left (translated to the right elbow) rather than an independent
    point_at_angle rotation from its own shoulder reference: NEUTRAL_POSE's
    left/right shoulder-elbow vectors aren't exact mirror images of each
    other, so rotating each side by the identical raw angle leaves a
    small residual mismatch between wrists that shows up as extra drift
    in the combined (midpoint-based) elbow-angle signal — enough to trip
    incomplete_lockout_bottom's REST-phase check even on an otherwise
    clean rep (same fix as bench_press/overhead_press's
    _elbow_trajectory_frames)."""
    shoulder_l, elbow_l = neutral_xy(L_SHOULDER), neutral_xy(L_ELBOW)
    elbow_r = neutral_xy(R_ELBOW)
    overrides_sequence = []
    for angle in elbow_angles:
        wrist_l = point_at_angle(elbow_l, shoulder_l, angle, length=160.0)
        dx, dy = wrist_l[0] - elbow_l[0], wrist_l[1] - elbow_l[1]
        wrist_r = (elbow_r[0] + dx, elbow_r[1] + dy)
        overrides_sequence.append({L_WRIST: kp(*wrist_l), R_WRIST: kp(*wrist_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _elbow_trajectory_frames(angles)


def test_clean_pullup_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.PULLUP, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_incomplete_rom_top_fires_on_shallow_trajectory() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 110.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.PULLUP, frames)
    assert len(reps) >= 1
    assert "incomplete_rom_top" in reps[0].faults


def test_kipping_swing_fires_when_hip_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    shoulder_x, shoulder_y = neutral_xy(L_SHOULDER)
    for i in active:
        overrides[i][L_HIP] = kp(shoulder_x + 150.0, shoulder_y + 300.0)
        overrides[i][R_HIP] = kp(shoulder_x + 150.0, shoulder_y + 300.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.PULLUP, frames)
    assert len(reps) >= 1
    assert "kipping_swing" in reps[0].faults


def test_incomplete_lockout_bottom_fires_when_rest_stays_bent() -> None:
    angles = repeat_trajectory(
        linspace_rep(150.0, 70.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=150.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.PULLUP, frames)
    assert len(reps) >= 1
    assert "incomplete_lockout_bottom" in reps[0].faults
