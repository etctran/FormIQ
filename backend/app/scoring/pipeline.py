"""Orchestrates the scoring pipeline: frames -> profile lookup -> signal
normalization -> phase segmentation -> per-rep fault evaluation ->
RepScore list. Failures are caught and logged; callers get [] rather
than an exception, matching "no reps detected" as a normal outcome."""

from __future__ import annotations

import logging

from app.schemas.analysis import Exercise, RepScore
from app.schemas.keypoint import Frame
from app.scoring.phases import segment_phases
from app.scoring.profiles import get_profile
from app.scoring.rules import compute_form_accuracy, evaluate_fault_rules
from app.scoring.signal import build_signal_segments

MIN_FRAMES = 10

logger = logging.getLogger(__name__)


def analyze(exercise: Exercise, frames: list[Frame]) -> list[RepScore]:
    if len(frames) < MIN_FRAMES:
        return []
    try:
        return _analyze(exercise, frames)
    except Exception:
        logger.exception("scoring pipeline failed for exercise=%s", exercise)
        return []


def _analyze(exercise: Exercise, frames: list[Frame]) -> list[RepScore]:
    profile = get_profile(exercise)
    raw_values = [profile.primary_signal(f) for f in frames]
    timestamps = [f.timestamp_sec for f in frames]
    segments = build_signal_segments(raw_values, timestamps)

    reps: list[RepScore] = []
    rep_index = 0
    for segment in segments:
        for rep_window in segment_phases(segment):
            faults = evaluate_fault_rules(frames, rep_window, profile.fault_rules)
            form_accuracy = compute_form_accuracy(faults, profile.fault_rules)
            reps.append(
                RepScore(
                    rep_index=rep_index,
                    start_sec=rep_window.start_sec,
                    end_sec=rep_window.end_sec,
                    form_accuracy=form_accuracy,
                    faults=faults,
                )
            )
            rep_index += 1
    return reps
