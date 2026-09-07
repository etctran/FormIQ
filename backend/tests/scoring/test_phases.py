import numpy as np
import pytest

from app.scoring.phases import Phase, segment_phases
from app.scoring.signal import SignalSegment


def _segment(values: list[float]) -> SignalSegment:
    n = len(values)
    return SignalSegment(
        frame_indices=list(range(n)),
        timestamps=np.array([i / 30.0 for i in range(n)]),
        values=np.array(values, dtype=float),
    )


def _one_rep_values() -> list[float]:
    rest = [1.0] * 5
    down = np.linspace(1.0, 0.0, 10).tolist()
    up = np.linspace(0.0, 1.0, 10).tolist()
    return rest + down + up + rest


def test_single_rep_detected() -> None:
    seg = _segment(_one_rep_values())
    reps = segment_phases(seg)
    assert len(reps) == 1
    rep = reps[0]
    assert rep.start_sec < rep.end_sec
    assert rep.frame_indices[0] < rep.frame_indices[-1]


def test_two_reps_detected() -> None:
    one_rep = _one_rep_values()
    # Second rep continues from where the first's rest padding ended.
    seg = _segment(one_rep + one_rep[5:])
    reps = segment_phases(seg)
    assert len(reps) == 2
    assert reps[0].end_sec <= reps[1].start_sec


def test_no_completed_rep_when_never_returns_to_rest() -> None:
    values = [1.0] * 5 + np.linspace(1.0, 0.0, 10).tolist()  # descends, never recovers
    seg = _segment(values)
    assert segment_phases(seg) == []


def test_no_rep_when_signal_never_leaves_rest() -> None:
    seg = _segment([1.0] * 20)
    assert segment_phases(seg) == []


def test_every_frame_in_rep_window_has_a_phase_label() -> None:
    seg = _segment(_one_rep_values())
    rep = segment_phases(seg)[0]
    for i in rep.frame_indices:
        assert rep.phase_by_frame_index[i] in Phase


def test_peak_phase_present_at_the_bottom() -> None:
    seg = _segment(_one_rep_values())
    rep = segment_phases(seg)[0]
    bottom_index = seg.values.argmin()
    assert rep.phase_by_frame_index[int(bottom_index)] == Phase.PEAK
