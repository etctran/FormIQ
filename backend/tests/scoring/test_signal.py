import numpy as np

from app.scoring.signal import build_signal_segments


def _linear_trajectory(n: int, fps: float = 30.0) -> tuple[list[float], list[float]]:
    """A clean rest(170)->peak(70)->rest(170) trajectory, n frames."""
    half = n // 2
    down = np.linspace(170.0, 70.0, half).tolist()
    up = np.linspace(70.0, 170.0, n - half).tolist()
    values = down + up
    timestamps = [i / fps for i in range(n)]
    return values, timestamps


def test_empty_input_returns_no_segments() -> None:
    assert build_signal_segments([], []) == []


def test_clean_signal_produces_one_segment_rescaled_to_unit_range() -> None:
    values, timestamps = _linear_trajectory(60)
    segments = build_signal_segments(values, timestamps)
    assert len(segments) == 1
    seg = segments[0]
    assert seg.frame_indices == list(range(60))
    assert seg.values.min() >= 0.0
    assert seg.values.max() <= 1.0
    # Rest end -> high signal, peak middle -> low signal.
    assert seg.values[0] > 0.8
    assert seg.values[29] < 0.3


def test_small_interior_gap_is_interpolated_not_split() -> None:
    values, timestamps = _linear_trajectory(60)
    values[30] = None
    values[31] = None
    segments = build_signal_segments(values, timestamps)
    assert len(segments) == 1
    assert len(segments[0].frame_indices) == 60


def test_large_gap_splits_into_two_segments() -> None:
    values, timestamps = _linear_trajectory(90)
    # Blank out roughly 1.5s (45 frames at 30fps) in the middle.
    for i in range(20, 65):
        values[i] = None
    segments = build_signal_segments(values, timestamps, max_gap_sec=1.0)
    assert len(segments) == 2
    assert segments[0].frame_indices[-1] < 20
    assert segments[1].frame_indices[0] >= 65


def test_flat_signal_produces_no_segment() -> None:
    values = [100.0] * 30
    timestamps = [i / 30.0 for i in range(30)]
    assert build_signal_segments(values, timestamps) == []


def test_all_none_produces_no_segment() -> None:
    values: list[float | None] = [None] * 30
    timestamps = [i / 30.0 for i in range(30)]
    assert build_signal_segments(values, timestamps) == []


def test_short_trailing_gap_is_interpolated() -> None:
    """A clean trajectory with only the last 2 frames None should
    interpolate them, not truncate the segment."""
    values, timestamps = _linear_trajectory(60)
    values[58] = None
    values[59] = None
    segments = build_signal_segments(values, timestamps)
    assert len(segments) == 1
    seg = segments[0]
    # All 60 frames should be included (Nones interpolated)
    assert len(seg.frame_indices) == 60
    # Last frames should have interpolated values (not NaN)
    assert not np.isnan(seg.values[58])
    assert not np.isnan(seg.values[59])
