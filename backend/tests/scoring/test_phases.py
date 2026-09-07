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


def test_false_start_not_stitched_into_real_rep() -> None:
    # Signal: REST -> partial dip (0.5, never reaches PEAK) -> REST ->
    # real rep (down to 0.0, up to 1.0) -> REST. The emitted rep should
    # only include the real rep, not the earlier false start.
    false_start = [1.0] * 5 + [0.8, 0.7, 0.6, 0.5, 0.6, 0.7, 0.8] + [1.0] * 3
    real_rep = _one_rep_values()
    combined = false_start + real_rep
    seg = _segment(combined)
    reps = segment_phases(seg)
    assert len(reps) == 1
    # The rep should start after the false start, not at frame 0.
    assert reps[0].frame_indices[0] > 5  # Must skip the false start phase


def test_hysteresis_dead_zone_prevents_spurious_transitions() -> None:
    # Signal that stays in the REST hysteresis dead zone [REST_EXIT=0.75,
    # REST_ENTER=0.85) should not cause a phase flip. A value at 0.80
    # should keep the signal in REST phase without transitioning to DRIVE.
    values = [1.0] * 10 + [0.80] * 10 + [1.0] * 10
    seg = _segment(values)
    phases_result = segment_phases(seg)
    # No complete rep because signal never reaches PEAK (0.15), so no
    # RepWindow is emitted.
    assert phases_result == []
