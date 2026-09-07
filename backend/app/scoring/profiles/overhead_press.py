"""Overhead press profile (front view). Primary signal: 180 -
angle(shoulder,elbow,wrist), inverted because rest here is the flexed
position (bar racked at shoulder) and peak is full extension overhead."""

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
    horizontal_offset_metric,
    inverted_angle_metric,
    vertical_symmetry_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
ELBOW = (L_ELBOW, R_ELBOW)
WRIST = (L_WRIST, R_WRIST)
HIP = (L_HIP, R_HIP)

_INVERTED_ELBOW_ANGLE = inverted_angle_metric(SHOULDER, ELBOW, WRIST)

PROFILE = ExerciseProfile(
    primary_signal=_INVERTED_ELBOW_ANGLE,
    fault_rules=[
        threshold_fault(
            name="incomplete_lockout",
            metric=_INVERTED_ELBOW_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=25.0,  # raw elbow angle stayed below ~155 deg
            penalty=0.20,
        ),
        threshold_fault(
            name="excessive_back_lean",
            metric=horizontal_offset_metric(SHOULDER, HIP, normalize=(SHOULDER, HIP)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.3,
            penalty=0.15,
        ),
        threshold_fault(
            name="uneven_press",
            metric=vertical_symmetry_metric(L_WRIST, R_WRIST, normalize=(L_SHOULDER, R_SHOULDER)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.15,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.OVERHEAD_PRESS, PROFILE)
