import operator

import pytest

from app.schemas.keypoint import Frame, Keypoint
from app.scoring.phases import Phase, RepWindow
from app.scoring.rules import compute_form_accuracy, evaluate_fault_rules, threshold_fault


def _frame(index: int = 0) -> Frame:
    return Frame(
        timestamp_sec=index / 30.0, landmarks=[Keypoint(x=0, y=0, z=0, visibility=1.0)] * 33
    )


def _rep(phase_by_index: dict[int, Phase]) -> RepWindow:
    indices = sorted(phase_by_index)
    return RepWindow(
        start_sec=0.0,
        end_sec=1.0,
        frame_indices=indices,
        phase_by_frame_index=phase_by_index,
    )


def test_fault_fires_when_majority_of_in_phase_frames_violate() -> None:
    frames = [_frame(i) for i in range(6)]
    rep = _rep({0: Phase.REST, 1: Phase.PEAK, 2: Phase.PEAK, 3: Phase.PEAK, 4: Phase.RECOVER, 5: Phase.REST})
    values = {1: 50.0, 2: 60.0, 3: 5.0}  # 2/3 PEAK frames > 40

    def metric(frame: Frame) -> float:
        return values[frames.index(frame)]

    rule = threshold_fault(
        name="too_shallow",
        metric=metric,
        phases={Phase.PEAK},
        comparison=operator.gt,
        threshold=40.0,
        penalty=0.2,
    )
    assert evaluate_fault_rules(frames, rep, [rule]) == ["too_shallow"]


def test_fault_does_not_fire_below_violation_ratio() -> None:
    frames = [_frame(i) for i in range(6)]
    rep = _rep({0: Phase.REST, 1: Phase.PEAK, 2: Phase.PEAK, 3: Phase.PEAK, 4: Phase.RECOVER, 5: Phase.REST})
    values = {1: 5.0, 2: 6.0, 3: 50.0}  # only 1/3 PEAK frames > 40

    def metric(frame: Frame) -> float:
        return values[frames.index(frame)]

    rule = threshold_fault(
        name="too_shallow",
        metric=metric,
        phases={Phase.PEAK},
        comparison=operator.gt,
        threshold=40.0,
        penalty=0.2,
    )
    assert evaluate_fault_rules(frames, rep, [rule]) == []


def test_fault_scoped_to_phase_not_present_in_rep_does_not_fire() -> None:
    frames = [_frame(i) for i in range(2)]
    rep = _rep({0: Phase.REST, 1: Phase.REST})
    rule = threshold_fault(
        name="whatever", metric=lambda f: 100.0, phases={Phase.PEAK},
        comparison=operator.gt, threshold=0.0, penalty=0.1,
    )
    assert evaluate_fault_rules(frames, rep, [rule]) == []


def test_none_metric_values_excluded_from_ratio() -> None:
    frames = [_frame(i) for i in range(3)]
    rep = _rep({0: Phase.PEAK, 1: Phase.PEAK, 2: Phase.PEAK})
    values = {0: None, 1: 50.0, 2: 50.0}

    def metric(frame: Frame) -> float | None:
        return values[frames.index(frame)]

    rule = threshold_fault(
        name="x", metric=metric, phases={Phase.PEAK},
        comparison=operator.gt, threshold=40.0, penalty=0.1,
    )
    # Both resolvable frames violate -> fires, despite one None.
    assert evaluate_fault_rules(frames, rep, [rule]) == ["x"]


def test_all_none_metric_values_means_no_fire() -> None:
    frames = [_frame(i) for i in range(2)]
    rep = _rep({0: Phase.PEAK, 1: Phase.PEAK})
    rule = threshold_fault(
        name="x", metric=lambda f: None, phases={Phase.PEAK},
        comparison=operator.gt, threshold=40.0, penalty=0.1,
    )
    assert evaluate_fault_rules(frames, rep, [rule]) == []


def test_compute_form_accuracy_no_faults() -> None:
    rules = [threshold_fault("a", lambda f: 0.0, {Phase.PEAK}, operator.gt, 1.0, 0.2)]
    assert compute_form_accuracy([], rules) == 1.0


def test_compute_form_accuracy_sums_penalties_and_clamps() -> None:
    rules = [
        threshold_fault("a", lambda f: 0.0, {Phase.PEAK}, operator.gt, 1.0, 0.6),
        threshold_fault("b", lambda f: 0.0, {Phase.PEAK}, operator.gt, 1.0, 0.6),
    ]
    assert compute_form_accuracy(["a", "b"], rules) == 0.0  # clamped, not -0.2
