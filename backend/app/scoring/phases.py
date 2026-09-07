"""Generic 4-phase state machine segmenting a normalized [0, 1] signal
into reps. 1.0 = rest posture, 0.0 = peak-effort posture (see signal.py).
A rep is one full REST -> DRIVE -> PEAK -> RECOVER -> REST cycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from app.scoring.signal import SignalSegment

REST_ENTER, REST_EXIT = 0.85, 0.75
PEAK_ENTER, PEAK_EXIT = 0.15, 0.25


class Phase(Enum):
    REST = "rest"
    DRIVE = "drive"
    PEAK = "peak"
    RECOVER = "recover"


@dataclass
class RepWindow:
    start_sec: float
    end_sec: float
    frame_indices: list[int]
    phase_by_frame_index: dict[int, Phase]


def _phase_sequence(values: np.ndarray) -> list[Phase]:
    if values[0] >= REST_ENTER:
        current = Phase.REST
    elif values[0] <= PEAK_ENTER:
        current = Phase.PEAK
    else:
        current = Phase.DRIVE

    phases: list[Phase] = []
    for v in values:
        if current == Phase.REST:
            if v < REST_EXIT:
                current = Phase.DRIVE
        elif current == Phase.DRIVE:
            if v <= PEAK_ENTER:
                current = Phase.PEAK
            elif v >= REST_ENTER:
                current = Phase.REST
        elif current == Phase.PEAK:
            if v > PEAK_EXIT:
                current = Phase.RECOVER
        elif current == Phase.RECOVER:
            if v >= REST_ENTER:
                current = Phase.REST
            elif v <= PEAK_ENTER:
                current = Phase.PEAK
        phases.append(current)
    return phases


def segment_phases(segment: SignalSegment) -> list[RepWindow]:
    """Rep windows within one SignalSegment. A rep is delimited by two
    REST-phase frames with a PEAK-phase frame somewhere between them; a
    trailing partial rep (never returns to REST) is dropped."""
    phases = _phase_sequence(segment.values)
    reps: list[RepWindow] = []
    rest_start_local: int | None = None
    seen_peak = False

    for local_i, phase in enumerate(phases):
        if phase == Phase.REST:
            if rest_start_local is None:
                rest_start_local = local_i
            elif seen_peak:
                frame_indices = segment.frame_indices[rest_start_local : local_i + 1]
                phase_by_frame_index = {
                    segment.frame_indices[j]: phases[j]
                    for j in range(rest_start_local, local_i + 1)
                }
                reps.append(
                    RepWindow(
                        start_sec=float(segment.timestamps[rest_start_local]),
                        end_sec=float(segment.timestamps[local_i]),
                        frame_indices=frame_indices,
                        phase_by_frame_index=phase_by_frame_index,
                    )
                )
                rest_start_local = local_i
                seen_peak = False
        elif phase == Phase.PEAK:
            seen_peak = True

    return reps
