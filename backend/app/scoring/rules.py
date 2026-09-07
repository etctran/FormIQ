"""Declarative per-exercise fault rules and weighted-penalty scoring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.schemas.keypoint import Frame
from app.scoring.phases import Phase, RepWindow

Comparison = Callable[[float, float], bool]
Metric = Callable[[Frame], float | None]


@dataclass
class FaultRule:
    name: str
    phases: frozenset[Phase]
    metric: Metric
    check: Callable[[float], bool]
    penalty: float
    min_violating_frames_ratio: float = 0.5


def threshold_fault(
    name: str,
    metric: Metric,
    phases: set[Phase] | frozenset[Phase],
    comparison: Comparison,
    threshold: float,
    penalty: float,
    min_violating_frames_ratio: float = 0.5,
) -> FaultRule:
    return FaultRule(
        name=name,
        phases=frozenset(phases),
        metric=metric,
        check=lambda v: comparison(v, threshold),
        penalty=penalty,
        min_violating_frames_ratio=min_violating_frames_ratio,
    )


def evaluate_fault_rules(
    frames: list[Frame], rep: RepWindow, rules: list[FaultRule]
) -> list[str]:
    """Fault names that fire for this rep: for each rule, of the rep's
    frames whose phase is in rule.phases and whose metric resolves, at
    least min_violating_frames_ratio must violate rule.check."""
    fired: list[str] = []
    for rule in rules:
        in_phase = [
            i for i in rep.frame_indices
            if rep.phase_by_frame_index[i] in rule.phases
        ]
        if not in_phase:
            continue
        evaluated = 0
        violations = 0
        for i in in_phase:
            value = rule.metric(frames[i])
            if value is None:
                continue
            evaluated += 1
            if rule.check(value):
                violations += 1
        if evaluated == 0:
            continue
        if violations / evaluated >= rule.min_violating_frames_ratio:
            fired.append(rule.name)
    return fired


def compute_form_accuracy(
    fired_fault_names: list[str], rules: list[FaultRule]
) -> float:
    penalty_by_name = {r.name: r.penalty for r in rules}
    total_penalty = sum(penalty_by_name.get(name, 0.0) for name in fired_fault_names)
    return max(0.0, min(1.0, 1.0 - total_penalty))
