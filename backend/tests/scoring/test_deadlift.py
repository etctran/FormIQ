import pytest

from app.schemas.analysis import Exercise
from app.scoring.phases import Phase, segment_phases
from app.scoring.pipeline import analyze
from app.scoring.profiles.deadlift import PROFILE
from app.scoring.signal import build_signal_segments
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
    angle(shoulder,hip,knee) follows `hip_angles`, with HIP/KNEE fixed.
    NOSE is also repositioned each frame, relative to the CURRENT
    (pivot-swept) SHOULDER position, keeping angle(nose,shoulder,hip)
    pinned near its neutral ~170 deg value throughout: the single-DOF
    polar sweep of SHOULDER around the HIP pivot otherwise drags SHOULDER
    far enough relative to a fixed-at-neutral NOSE to spuriously collapse
    that angle and trip back_rounding even in an otherwise clean rep."""
    hip_l, knee_l = neutral_xy(L_HIP), neutral_xy(L_KNEE)
    hip_r, knee_r = neutral_xy(R_HIP), neutral_xy(R_KNEE)
    overrides_sequence = []
    for angle in hip_angles:
        shoulder_l = point_at_angle(hip_l, knee_l, angle, length=300.0)
        shoulder_r = point_at_angle(hip_r, knee_r, angle, length=300.0)
        nose = point_at_angle(shoulder_l, hip_l, 170.0, length=150.0)
        overrides_sequence.append(
            {
                L_SHOULDER: kp(*shoulder_l),
                R_SHOULDER: kp(*shoulder_r),
                NOSE: kp(*nose),
            }
        )
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
    # Built from the shared (now pivot-sweep-safe) clean trajectory, so the
    # only thing that can make back_rounding fire is the explicit collapsed-
    # angle override below — not the underlying shoulder pivot sweep, which
    # _hinge_trajectory_frames already cancels out via its own 170 deg pin.
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    hip_l = neutral_xy(L_HIP)  # HIP is never overridden by _hinge_trajectory_frames
    for i in active:
        shoulder_l = overrides[i][L_SHOULDER][:2]
        # Nose placed to make angle(nose, shoulder, hip) ~ 140 deg (a
        # collapsed/rounded back), computed relative to the CURRENT
        # shoulder position so it doesn't depend on where in the
        # trajectory we are.
        nose = point_at_angle(shoulder_l, hip_l, 140.0, length=150.0)
        overrides[i][NOSE] = kp(*nose)
    frames = make_frames(overrides)
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
        overrides[i][L_WRIST] = kp(hip_x + 230.0, hip_y + 50.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.DEADLIFT, frames)
    assert len(reps) >= 1
    assert "hyperextension_lockout" in reps[0].faults


def _rest_frame_indices_for_clean_rep(overrides: list[dict[int, tuple]]) -> list[int]:
    """The global frame indices the pipeline itself classifies as
    Phase.REST for the single rep in `overrides` (built from the clean,
    un-overridden hip-hinge trajectory, since the wrist is not part of
    the primary signal and so doesn't affect phase segmentation)."""
    base_frames = make_frames(overrides)
    raw_values = [PROFILE.primary_signal(f) for f in base_frames]
    timestamps = [f.timestamp_sec for f in base_frames]
    segments = build_signal_segments(raw_values, timestamps)
    rep_windows = [w for seg in segments for w in segment_phases(seg)]
    assert len(rep_windows) == 1
    return [
        i
        for i, phase in rep_windows[0].phase_by_frame_index.items()
        if phase == Phase.REST
    ]


def test_hyperextension_lockout_rest_only_override_does_not_also_fire_bar_path_drift() -> None:
    """A wrist deviation confined strictly to REST-phase frames should
    fire hyperextension_lockout (phases={REST}) without also firing
    bar_path_drift (phases={DRIVE, RECOVER}) — proving the two rules no
    longer overlap after narrowing hyperextension_lockout off RECOVER."""
    base_overrides = _clean_overrides(num_reps=1)
    rest_indices = _rest_frame_indices_for_clean_rep(base_overrides)
    assert rest_indices  # sanity: the rep does have REST-phase frames

    overrides = _clean_overrides(num_reps=1)
    hip_x, hip_y = neutral_xy(L_HIP)
    for i in rest_indices:
        overrides[i][L_WRIST] = kp(hip_x + 230.0, hip_y + 50.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.DEADLIFT, frames)
    assert len(reps) >= 1
    assert "hyperextension_lockout" in reps[0].faults
    assert "bar_path_drift" not in reps[0].faults
