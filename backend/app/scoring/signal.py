"""Per-video signal normalization: raw per-frame metric values ->
contiguous SignalSegments smoothed and rescaled to [0, 1], where 1.0 is
always "rest" and 0.0 is always "peak effort" (given a raw metric that
follows the same convention — see landmarks.py's metric factories)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SignalSegment:
    frame_indices: list[int]
    timestamps: np.ndarray
    values: np.ndarray  # smoothed, rescaled to [0, 1]


def build_signal_segments(
    raw_values: list[float | None],
    timestamps: list[float],
    max_gap_sec: float = 1.0,
    smoothing_window_sec: float = 0.3,
) -> list[SignalSegment]:
    n = len(raw_values)
    if n == 0:
        return []

    # Split into contiguous stretches, breaking wherever a run of None
    # values spans more than max_gap_sec; short gaps stay in the segment
    # (and get interpolated below).
    segments_idx: list[list[int]] = []
    current: list[int] = []
    none_indices: list[int] = []
    none_start_ts: float | None = None

    for i in range(n):
        if raw_values[i] is None:
            if none_start_ts is None:
                none_start_ts = timestamps[i]
            none_indices.append(i)
        else:
            # Real value: check if preceding gap should be included
            if none_indices:
                gap_duration = timestamps[i] - none_start_ts
                if gap_duration <= max_gap_sec:
                    # Small gap: include it in current for interpolation
                    current.extend(none_indices)
                else:
                    # Large gap: end current segment and skip the gap
                    if current:
                        segments_idx.append(current)
                        current = []
                # Reset gap tracking
                none_indices = []
                none_start_ts = None
            # Add the real value to current
            current.append(i)

    # Handle any remaining None run at the end
    if none_indices:
        if current:
            segments_idx.append(current)
        # Don't add segment if it ends with Nones
    elif current:
        segments_idx.append(current)

    segments: list[SignalSegment] = []
    for idx_list in segments_idx:
        resolvable = [i for i in idx_list if raw_values[i] is not None]
        if len(resolvable) < 2:
            continue

        ts = np.array([timestamps[i] for i in idx_list], dtype=float)
        raw = np.array(
            [
                raw_values[i] if raw_values[i] is not None else np.nan
                for i in idx_list
            ],
            dtype=float,
        )
        nan_mask = np.isnan(raw)
        if nan_mask.any():
            raw[nan_mask] = np.interp(
                ts[nan_mask], ts[~nan_mask], raw[~nan_mask]
            )

        lo, hi = np.percentile(raw, 5), np.percentile(raw, 95)
        if hi - lo < 1e-6:
            continue  # no meaningful movement in this segment
        rescaled = np.clip((raw - lo) / (hi - lo), 0.0, 1.0)

        if len(ts) > 1:
            fps = len(ts) / max(ts[-1] - ts[0], 1e-6)
            window = max(1, int(round(smoothing_window_sec * fps)))
        else:
            window = 1
        if window > 1:
            kernel = np.ones(window) / window
            # Use edge padding to preserve boundary values during convolution
            pad_left = (window - 1) // 2
            pad_right = (window - 1) - pad_left
            padded = np.pad(rescaled, (pad_left, pad_right), mode="edge")
            smoothed = np.convolve(padded, kernel, mode="valid")
        else:
            smoothed = rescaled

        segments.append(
            SignalSegment(frame_indices=idx_list, timestamps=ts, values=smoothed)
        )

    return segments
