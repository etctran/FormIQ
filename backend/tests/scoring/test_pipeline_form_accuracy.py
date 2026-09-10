"""End-to-end test asserting an EXACT known form_accuracy value (and
exact fault list) through the real analyze() pipeline, given a
synthetic rep built with a KNOWN combination of faults firing.

Every existing form_accuracy assertion elsewhere is either
pytest.approx(1.0) on a clean fixture (see each exercise's
test_<exercise>.py) or a direct unit test of compute_form_accuracy in
isolation (test_rules.py). Neither exercises the full pipeline with a
non-trivial, exactly-known penalty sum — this test closes that gap.
"""

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
L_FOOT_INDEX = 31

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _knee_trajectory_frames(knee_angles: list[float]) -> list[dict[int, tuple]]:
    """Same construction as test_squat.py's helper of the same name
    (duplicated locally so this file doesn't depend on that module's
    fixture shape): overrides HIP (per side) so angle(hip,knee,ankle)
    follows `knee_angles`, with SHOULDER pinned relative to the current
    HIP position to keep angle(shoulder,hip,knee) near its neutral
    ~170 deg value throughout, so back_rounding never spuriously fires."""
    knee_l, ankle_l = neutral_xy(L_KNEE), neutral_xy(L_ANKLE)
    knee_r, ankle_r = neutral_xy(R_KNEE), neutral_xy(R_ANKLE)
    overrides_sequence = []
    for angle in knee_angles:
        hip_l = point_at_angle(knee_l, ankle_l, angle, length=250.0)
        hip_r = point_at_angle(knee_r, ankle_r, angle, length=250.0)
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
    return overrides_sequence


def test_squat_with_two_known_faults_yields_exact_form_accuracy() -> None:
    """A shallow squat (insufficient_depth, penalty 0.20 in
    app/scoring/profiles/squat.py) where the knee also travels well past
    the toe (forward_knee_travel, penalty 0.15) should fire exactly
    those two faults, in that order, and no others — and form_accuracy
    should be exactly 1.0 - 0.20 - 0.15 = 0.65, not merely `< 1.0`."""
    angles = repeat_trajectory(
        linspace_rep(170.0, 130.0, FRAMES_DOWN, FRAMES_UP),
        1,
        rest_value=170.0,
        rest_frames=REST_FRAMES,
    )
    overrides = _knee_trajectory_frames(angles)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    knee_l_x, knee_l_y = neutral_xy(L_KNEE)
    for i in active:
        # Foot index placed far behind the knee (knee travels well past it).
        overrides[i][L_FOOT_INDEX] = kp(knee_l_x - 320.0, knee_l_y + 20.0)

    frames = make_frames(overrides)
    reps = analyze(Exercise.SQUAT, frames)

    assert len(reps) == 1
    assert reps[0].faults == ["insufficient_depth", "forward_knee_travel"]
    assert reps[0].form_accuracy == pytest.approx(0.65)
