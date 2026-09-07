"""Row profile (side view). Primary signal: elbow angle
(shoulder-elbow-wrist). Rest = arms extended (~170 deg+); peak = handle
pulled to torso."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ELBOW,
    L_HIP,
    L_KNEE,
    L_SHOULDER,
    L_WRIST,
    R_ELBOW,
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
ELBOW = (L_ELBOW, R_ELBOW)
WRIST = (L_WRIST, R_WRIST)
HIP = (L_HIP, R_HIP)
KNEE = (L_KNEE, R_KNEE)

_ELBOW_ANGLE = angle_metric(SHOULDER, ELBOW, WRIST)

PROFILE = ExerciseProfile(
    primary_signal=_ELBOW_ANGLE,
    fault_rules=[
        threshold_fault(
            name="insufficient_pull",
            metric=_ELBOW_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=100.0,
            penalty=0.20,
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
            name="torso_swing",
            metric=horizontal_offset_metric(SHOULDER, HIP, normalize=(SHOULDER, HIP)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.25,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.ROW, PROFILE)
