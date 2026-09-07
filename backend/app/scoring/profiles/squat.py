"""Squat profile (side view). Primary signal: knee angle
(hip-knee-ankle). Rest = standing (~170 deg+); peak = deepest point."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ANKLE,
    L_FOOT_INDEX,
    L_HEEL,
    L_HIP,
    L_KNEE,
    L_SHOULDER,
    R_ANKLE,
    R_FOOT_INDEX,
    R_HEEL,
    R_HIP,
    R_KNEE,
    R_SHOULDER,
    angle_metric,
    horizontal_offset_metric,
    vertical_offset_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

HIP = (L_HIP, R_HIP)
KNEE = (L_KNEE, R_KNEE)
ANKLE = (L_ANKLE, R_ANKLE)
SHOULDER = (L_SHOULDER, R_SHOULDER)
FOOT_INDEX = (L_FOOT_INDEX, R_FOOT_INDEX)
HEEL = (L_HEEL, R_HEEL)

_KNEE_ANGLE = angle_metric(HIP, KNEE, ANKLE)

PROFILE = ExerciseProfile(
    primary_signal=_KNEE_ANGLE,
    fault_rules=[
        threshold_fault(
            name="insufficient_depth",
            metric=_KNEE_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=100.0,
            penalty=0.20,
        ),
        threshold_fault(
            name="forward_knee_travel",
            metric=horizontal_offset_metric(KNEE, FOOT_INDEX, normalize=(KNEE, ANKLE)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.5,
            penalty=0.15,
        ),
        threshold_fault(
            name="back_rounding",
            metric=angle_metric(SHOULDER, HIP, KNEE),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.lt,
            threshold=150.0,
            penalty=0.15,
        ),
        threshold_fault(
            name="heel_rise",
            metric=vertical_offset_metric(HEEL, ANKLE, normalize=(FOOT_INDEX, ANKLE)),
            phases={Phase.PEAK},
            comparison=operator.lt,
            threshold=-0.3,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.SQUAT, PROFILE)
