"""Pushup profile (front / three-quarter view). Primary signal: elbow
angle (shoulder-elbow-wrist). Rest = arms extended (~170 deg+); peak =
chest near floor."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ANKLE,
    L_ELBOW,
    L_HIP,
    L_SHOULDER,
    L_WRIST,
    R_ANKLE,
    R_ELBOW,
    R_HIP,
    R_SHOULDER,
    R_WRIST,
    angle_metric,
    horizontal_offset_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
ELBOW = (L_ELBOW, R_ELBOW)
WRIST = (L_WRIST, R_WRIST)
HIP = (L_HIP, R_HIP)
ANKLE = (L_ANKLE, R_ANKLE)

_ELBOW_ANGLE = angle_metric(SHOULDER, ELBOW, WRIST)

PROFILE = ExerciseProfile(
    primary_signal=_ELBOW_ANGLE,
    fault_rules=[
        threshold_fault(
            name="insufficient_depth",
            metric=_ELBOW_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=100.0,
            penalty=0.20,
        ),
        threshold_fault(
            name="hip_sag",
            metric=angle_metric(SHOULDER, HIP, ANKLE),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.lt,
            threshold=160.0,
            penalty=0.20,
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

register_profile(Exercise.PUSHUP, PROFILE)
