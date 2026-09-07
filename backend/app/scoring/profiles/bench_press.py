"""Bench press profile (front view). Primary signal: elbow angle
(shoulder-elbow-wrist). Rest = arms extended (~170 deg+); peak = bar at
chest."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ELBOW,
    L_HIP,
    L_SHOULDER,
    L_WRIST,
    R_ELBOW,
    R_HIP,
    R_SHOULDER,
    R_WRIST,
    angle_metric,
    horizontal_offset_metric,
    vertical_symmetry_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
ELBOW = (L_ELBOW, R_ELBOW)
WRIST = (L_WRIST, R_WRIST)
HIP = (L_HIP, R_HIP)

_ELBOW_ANGLE = angle_metric(SHOULDER, ELBOW, WRIST)

PROFILE = ExerciseProfile(
    primary_signal=_ELBOW_ANGLE,
    fault_rules=[
        threshold_fault(
            name="uneven_bar_path",
            metric=vertical_symmetry_metric(L_WRIST, R_WRIST, normalize=(L_SHOULDER, R_SHOULDER)),
            phases={Phase.DRIVE, Phase.RECOVER},
            comparison=operator.gt,
            threshold=0.15,
            penalty=0.15,
        ),
        threshold_fault(
            name="partial_lockout",
            metric=_ELBOW_ANGLE,
            # REST only: RECOVER's own phase definition (signal below
            # REST_ENTER) means elbow angle hasn't fully returned to rest
            # yet by construction, so checking lockout during RECOVER
            # would always partially violate even a clean rep. Checking
            # once the rep has actually settled into REST is what
            # "lockout completion" means. Threshold lowered from 160 to
            # 150: a rep's REST-phase window is only ever its two boundary
            # frames (the state machine's rest_start_local collapses to
            # the last pre-DRIVE sample), and REST_EXIT=0.75 lets that
            # boundary frame drift down to ~0.75 of this exercise's full
            # ~100 deg range (~149 deg) before phase officially exits REST
            # — so 160 would flag even a fully-locked-out clean rep at
            # that boundary. 150 sits below that natural drift floor while
            # still catching a rep whose REST frames stayed near ~140.
            phases={Phase.REST},
            comparison=operator.lt,
            threshold=150.0,
            penalty=0.15,
        ),
        threshold_fault(
            name="flared_elbows",
            metric=horizontal_offset_metric(ELBOW, SHOULDER, normalize=(SHOULDER, HIP)),
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=0.6,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.BENCH_PRESS, PROFILE)
