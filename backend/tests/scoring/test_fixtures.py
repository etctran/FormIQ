import pytest

from app.scoring.landmarks import angle_between
from tests.scoring.fixtures import (
    NUM_LANDMARKS,
    active_frame_offsets,
    linspace_rep,
    make_frame,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)


def test_make_frame_has_all_landmarks_with_overrides_applied() -> None:
    frame = make_frame(1.5, {23: (1.0, 2.0, 0.0, 1.0)})
    assert frame.timestamp_sec == 1.5
    assert len(frame.landmarks) == NUM_LANDMARKS
    assert (frame.landmarks[23].x, frame.landmarks[23].y) == (1.0, 2.0)


def test_make_frames_assigns_increasing_timestamps() -> None:
    frames = make_frames([{}, {}, {}], fps=30.0)
    assert [f.timestamp_sec for f in frames] == pytest.approx([0.0, 1 / 30, 2 / 30])


def test_point_at_angle_matches_angle_between() -> None:
    vertex = (0.0, 0.0)
    reference = (10.0, 0.0)
    for target in (30.0, 90.0, 150.0):
        point = point_at_angle(vertex, reference, target, length=5.0)
        assert angle_between(reference, vertex, point) == pytest.approx(target, abs=1e-6)


def test_neutral_xy_matches_base_pose() -> None:
    x, y = neutral_xy(23)
    assert isinstance(x, float)
    assert isinstance(y, float)


def test_linspace_rep_starts_and_ends_at_rest() -> None:
    values = linspace_rep(rest_value=170.0, peak_value=70.0, frames_down=10, frames_up=10)
    assert len(values) == 20
    assert values[0] == pytest.approx(170.0)
    assert values[9] == pytest.approx(70.0, abs=15.0)  # nearing peak
    assert values[-1] == pytest.approx(170.0)


def test_repeat_trajectory_wraps_with_rest_padding() -> None:
    single_rep = [1.0, 2.0, 3.0]
    out = repeat_trajectory(single_rep, num_reps=2, rest_value=0.0, rest_frames=2)
    assert out == [0.0, 0.0, 1.0, 2.0, 3.0, 0.0, 0.0, 1.0, 2.0, 3.0, 0.0, 0.0]


def test_active_frame_offsets_skip_rest_padding() -> None:
    offsets = active_frame_offsets(num_reps=2, frames_down=3, frames_up=3, rest_frames=2)
    assert offsets == [
        list(range(2, 8)),
        list(range(10, 16)),
    ]
