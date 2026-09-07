"""Registry of ExerciseProfile, one per Exercise. Profile modules
(squat.py, deadlift.py, ...) call register_profile(...) at import time;
_ensure_loaded imports each of them lazily on first get_profile() call,
so importing this package alone never requires every profile module to
exist."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.schemas.analysis import Exercise
from app.schemas.keypoint import Frame
from app.scoring.rules import FaultRule


@dataclass
class ExerciseProfile:
    primary_signal: Callable[[Frame], float | None]
    fault_rules: list[FaultRule]


_REGISTRY: dict[Exercise, ExerciseProfile] = {}
_loaded = False


def register_profile(exercise: Exercise, profile: ExerciseProfile) -> None:
    _REGISTRY[exercise] = profile


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    # Each import below registers its exercise's profile as a side
    # effect. Extended by one line per exercise in Tasks 7-14.
    from app.scoring.profiles import (  # noqa: F401
        bench_press,
        deadlift,
        lunge,
        overhead_press,
        pullup,
        pushup,
        squat,
    )

    _loaded = True


def get_profile(exercise: Exercise) -> ExerciseProfile:
    _ensure_loaded()
    return _REGISTRY[exercise]
