"""Deadlift profile (side view). Primary signal: hip hinge angle
(shoulder-hip-knee). Rest = standing tall (~170 deg+); peak = bar at
floor."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_HIP,
    L_KNEE,
    L_SHOULDER,
    L_WRIST,
    NOSE,
    R_HIP,
    R_KNEE,
    R_SHOULDER,
    R_WRIST,
    angle_metric,
    horizontal_offset_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
HIP = (L_HIP, R_HIP)
KNEE = (L_KNEE, R_KNEE)
WRIST = (L_WRIST, R_WRIST)

_HIP_HINGE_ANGLE = angle_metric(SHOULDER, HIP, KNEE)

PROFILE = ExerciseProfile(
    primary_signal=_HIP_HINGE_ANGLE,
    fault_rules=[
        threshold_fault(
            name="back_rounding",
            metric=angle_metric(NOSE, SHOULDER, HIP),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.lt,
            threshold=160.0,
            penalty=0.20,
        ),
        threshold_fault(
            name="bar_path_drift",
            metric=horizontal_offset_metric(WRIST, HIP, normalize=(SHOULDER, HIP)),
            phases={Phase.DRIVE, Phase.RECOVER},
            comparison=operator.gt,
            threshold=0.25,
            penalty=0.15,
        ),
        threshold_fault(
            name="hyperextension_lockout",
            metric=horizontal_offset_metric(WRIST, HIP, normalize=(SHOULDER, HIP)),
            phases={Phase.REST, Phase.RECOVER},
            comparison=operator.gt,
            threshold=0.3,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.DEADLIFT, PROFILE)
