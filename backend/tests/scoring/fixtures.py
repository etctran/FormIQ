"""Generic synthetic-Frame test toolkit. No cv_engine / video dependency.

Exercise-specific joint trajectories are built in each exercise's own
test module using these primitives.
"""

from __future__ import annotations

import math

import numpy as np

from app.schemas.keypoint import Frame, Keypoint

NUM_LANDMARKS = 33
FPS = 30.0

# A plausible standing-neutral pose, in video pixel coordinates (roughly
# a 720x1280 portrait frame). Index -> (x, y, z, visibility).
NEUTRAL_POSE: dict[int, tuple[float, float, float, float]] = {
    0: (360.0, 200.0, 0.0, 1.0),  # nose
    11: (300.0, 320.0, 0.0, 1.0),  # L shoulder
    12: (420.0, 320.0, 0.0, 1.0),  # R shoulder
    13: (290.0, 460.0, 0.0, 1.0),  # L elbow
    14: (430.0, 460.0, 0.0, 1.0),  # R elbow
    15: (285.0, 600.0, 0.0, 1.0),  # L wrist
    16: (435.0, 600.0, 0.0, 1.0),  # R wrist
    23: (310.0, 620.0, 0.0, 1.0),  # L hip
    24: (410.0, 620.0, 0.0, 1.0),  # R hip
    25: (310.0, 860.0, 0.0, 1.0),  # L knee
    26: (410.0, 860.0, 0.0, 1.0),  # R knee
    27: (310.0, 1100.0, 0.0, 1.0),  # L ankle
    28: (410.0, 1100.0, 0.0, 1.0),  # R ankle
    29: (310.0, 1140.0, 0.0, 1.0),  # L heel
    30: (410.0, 1140.0, 0.0, 1.0),  # R heel
    31: (330.0, 1150.0, 0.0, 1.0),  # L foot index
    32: (390.0, 1150.0, 0.0, 1.0),  # R foot index
}


def kp(x: float, y: float) -> tuple[float, float, float, float]:
    """Shorthand override tuple: (x, y, z=0.0, visibility=1.0)."""
    return (x, y, 0.0, 1.0)


def neutral_xy(index: int) -> tuple[float, float]:
    """The (x, y) of `index` in NEUTRAL_POSE, before any override."""
    x, y, _z, _vis = NEUTRAL_POSE[index]
    return (x, y)


def make_frame(
    timestamp_sec: float,
    overrides: dict[int, tuple[float, float, float, float]],
) -> Frame:
    """A Frame with all 33 landmarks: NEUTRAL_POSE layered with `overrides`
    (index -> (x, y, z, visibility)). Indices with no neutral-pose entry
    and no override default to (0, 0, 0, visibility=0.0) — i.e.
    unresolvable, matching real undetected landmarks."""
    landmarks = []
    for i in range(NUM_LANDMARKS):
        x, y, z, vis = overrides.get(
            i, NEUTRAL_POSE.get(i, (0.0, 0.0, 0.0, 0.0))
        )
        landmarks.append(Keypoint(x=x, y=y, z=z, visibility=vis))
    return Frame(timestamp_sec=timestamp_sec, landmarks=landmarks)


def make_frames(
    overrides_sequence: list[dict[int, tuple[float, float, float, float]]],
    fps: float = FPS,
) -> list[Frame]:
    """One Frame per element of `overrides_sequence`, timestamped at `fps`."""
    return [
        make_frame(i / fps, overrides)
        for i, overrides in enumerate(overrides_sequence)
    ]


def point_at_angle(
    vertex: tuple[float, float],
    reference: tuple[float, float],
    angle_deg: float,
    length: float,
) -> tuple[float, float]:
    """A point P at `length` from `vertex`, such that the angle at
    `vertex` between rays vertex->reference and vertex->P is `angle_deg`
    (rotating counter-clockwise from the reference direction, in screen
    coordinates where +y is down). Inverse of angle_between for
    constructing fixtures with a known target angle."""
    ref_dx, ref_dy = reference[0] - vertex[0], reference[1] - vertex[1]
    ref_angle = math.atan2(ref_dy, ref_dx)
    theta = ref_angle + math.radians(angle_deg)
    return (
        vertex[0] + length * math.cos(theta),
        vertex[1] + length * math.sin(theta),
    )


def linspace_rep(
    rest_value: float,
    peak_value: float,
    frames_down: int = 20,
    frames_up: int = 20,
) -> list[float]:
    """One rep's target-scalar trajectory: linearly interpolated
    rest_value -> peak_value over `frames_down` frames, then back to
    rest_value over `frames_up` frames."""
    down = np.linspace(rest_value, peak_value, frames_down).tolist()
    up = np.linspace(peak_value, rest_value, frames_up).tolist()
    return down + up


def repeat_trajectory(
    single_rep: list[float],
    num_reps: int,
    rest_value: float,
    rest_frames: int = 5,
) -> list[float]:
    """Repeat `single_rep` `num_reps` times, with `rest_frames` frames of
    `rest_value` before, between, and after each rep, so REST phases are
    clearly established for the phase state machine."""
    rest = [rest_value] * rest_frames
    out = list(rest)
    for _ in range(num_reps):
        out.extend(single_rep)
        out.extend(rest)
    return out


def active_frame_offsets(
    num_reps: int,
    frames_down: int,
    frames_up: int,
    rest_frames: int,
) -> list[list[int]]:
    """Global frame indices spanning the DRIVE->PEAK->RECOVER portion of
    each rep (everything except the REST padding between reps), given the
    same frames_down/frames_up/rest_frames used to build the trajectory
    via repeat_trajectory(linspace_rep(...), ...). Used by fault tests to
    know which frames to override with a fault-triggering landmark
    position."""
    rep_len = frames_down + frames_up
    offsets = []
    cursor = rest_frames
    for _ in range(num_reps):
        offsets.append(list(range(cursor, cursor + rep_len)))
        cursor += rep_len + rest_frames
    return offsets
