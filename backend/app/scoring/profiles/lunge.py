"""Lunge profile (side view). Both legs are modeled with the same
angle_metric; primary signal is the min of the two (whichever leg is
currently more flexed = the working leg). Rest = both legs extended
standing (~170 deg+); peak = working knee bent to its lowest angle."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ANKLE,
    L_FOOT_INDEX,
    L_HIP,
    L_KNEE,
    L_SHOULDER,
    R_ANKLE,
    R_FOOT_INDEX,
    R_HIP,
    R_KNEE,
    R_SHOULDER,
    angle_metric,
    horizontal_offset_metric,
    max_of,
    min_of,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
HIP = (L_HIP, R_HIP)

_LEFT_KNEE_ANGLE = angle_metric(L_HIP, L_KNEE, L_ANKLE)
_RIGHT_KNEE_ANGLE = angle_metric(R_HIP, R_KNEE, R_ANKLE)
_MIN_KNEE_ANGLE = min_of(_LEFT_KNEE_ANGLE, _RIGHT_KNEE_ANGLE)

_LEFT_KNEE_OVER_TOE = horizontal_offset_metric(L_KNEE, L_FOOT_INDEX, normalize=(L_KNEE, L_ANKLE))
_RIGHT_KNEE_OVER_TOE = horizontal_offset_metric(R_KNEE, R_FOOT_INDEX, normalize=(R_KNEE, R_ANKLE))

PROFILE = ExerciseProfile(
    primary_signal=_MIN_KNEE_ANGLE,
    fault_rules=[
        threshold_fault(
            name="insufficient_depth",
            metric=_MIN_KNEE_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=100.0,
            penalty=0.15,
        ),
        threshold_fault(
            name="knee_over_toe",
            metric=max_of(_LEFT_KNEE_OVER_TOE, _RIGHT_KNEE_OVER_TOE),
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=0.4,
            penalty=0.15,
        ),
        threshold_fault(
            name="torso_lean",
            metric=horizontal_offset_metric(SHOULDER, HIP, normalize=(SHOULDER, HIP)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.3,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.LUNGE, PROFILE)
