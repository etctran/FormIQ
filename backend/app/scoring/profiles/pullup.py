"""Pullup profile (front / three-quarter view). Primary signal: elbow
angle (shoulder-elbow-wrist). Rest = dead hang, arms extended (~170
deg+); peak = chin over bar."""

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
            name="incomplete_rom_top",
            metric=_ELBOW_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=90.0,
            penalty=0.20,
        ),
        threshold_fault(
            name="kipping_swing",
            metric=horizontal_offset_metric(HIP, SHOULDER, normalize=(SHOULDER, HIP)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.25,
            penalty=0.15,
        ),
        threshold_fault(
            name="incomplete_lockout_bottom",
            metric=_ELBOW_ANGLE,
            # A rep's REST-phase window is only ever its two boundary
            # frames (the phase state machine's rest_start_local collapses
            # to the last pre-DRIVE sample), and REST_EXIT=0.75 lets that
            # boundary frame drift down to ~0.75 of this exercise's full
            # ~100 deg range (~153 deg for a clean 170-deg-rest rep)
            # before the phase officially exits REST -- so 160 would flag
            # even a fully-locked-out clean rep at that boundary. 150 sits
            # below that natural drift floor while still catching a rep
            # whose REST frames stayed bent near ~140 (same reasoning as
            # bench_press's partial_lockout).
            phases={Phase.REST},
            comparison=operator.lt,
            threshold=150.0,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.PULLUP, PROFILE)
