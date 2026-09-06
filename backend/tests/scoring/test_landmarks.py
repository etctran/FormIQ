import pytest

from app.schemas.keypoint import Frame, Keypoint
from app.scoring.landmarks import (
    L_ANKLE,
    L_HIP,
    L_KNEE,
    R_ANKLE,
    R_HIP,
    R_KNEE,
    angle_between,
    angle_metric,
    distance,
    horizontal_offset_metric,
    inverted_angle_metric,
    landmark,
    max_of,
    midpoint,
    min_of,
    vertical_offset_metric,
    vertical_symmetry_metric,
)


def _kp(x: float, y: float, visibility: float = 1.0) -> Keypoint:
    return Keypoint(x=x, y=y, z=0.0, visibility=visibility)


def _frame(overrides: dict[int, Keypoint]) -> Frame:
    landmarks = [overrides.get(i, _kp(0.0, 0.0, 0.0)) for i in range(33)]
    return Frame(timestamp_sec=0.0, landmarks=landmarks)


def test_angle_between_right_angle() -> None:
    assert angle_between((0, 0), (0, -1), (1, -1)) == pytest.approx(90.0)


def test_angle_between_straight_line() -> None:
    assert angle_between((0, 0), (1, 0), (2, 0)) == pytest.approx(180.0)


def test_angle_between_zero_length_ray_returns_zero() -> None:
    assert angle_between((0, 0), (0, 0), (1, 0)) == 0.0


def test_distance() -> None:
    assert distance((0, 0), (3, 4)) == pytest.approx(5.0)


def test_landmark_returns_none_below_visibility_threshold() -> None:
    frame = _frame({L_HIP: _kp(1.0, 2.0, visibility=0.1)})
    assert landmark(frame, L_HIP) is None


def test_landmark_returns_keypoint_above_threshold() -> None:
    frame = _frame({L_HIP: _kp(1.0, 2.0, visibility=0.9)})
    kp = landmark(frame, L_HIP)
    assert kp is not None
    assert (kp.x, kp.y) == (1.0, 2.0)


def test_landmark_none_when_frame_has_no_landmarks() -> None:
    frame = Frame(timestamp_sec=0.0, landmarks=[])
    assert landmark(frame, L_HIP) is None


def test_midpoint() -> None:
    frame = _frame({L_HIP: _kp(0.0, 0.0), R_HIP: _kp(10.0, 20.0)})
    assert midpoint(frame, L_HIP, R_HIP) == (5.0, 10.0)


def test_midpoint_none_if_either_unresolvable() -> None:
    frame = _frame({L_HIP: _kp(0.0, 0.0, visibility=0.0)})
    assert midpoint(frame, L_HIP, R_HIP) is None


def test_angle_metric_with_single_indices() -> None:
    frame = _frame(
        {
            L_HIP: _kp(0.0, -10.0),
            L_KNEE: _kp(0.0, 0.0),
            L_ANKLE: _kp(10.0, 0.0),
        }
    )
    metric = angle_metric(L_HIP, L_KNEE, L_ANKLE)
    assert metric(frame) == pytest.approx(90.0)


def test_angle_metric_with_paired_midpoints() -> None:
    frame = _frame(
        {
            L_HIP: _kp(-2.0, -10.0),
            R_HIP: _kp(2.0, -10.0),
            L_KNEE: _kp(-2.0, 0.0),
            R_KNEE: _kp(2.0, 0.0),
            L_ANKLE: _kp(8.0, 0.0),
            R_ANKLE: _kp(12.0, 0.0),
        }
    )
    metric = angle_metric((L_HIP, R_HIP), (L_KNEE, R_KNEE), (L_ANKLE, R_ANKLE))
    assert metric(frame) == pytest.approx(90.0)


def test_angle_metric_none_when_unresolvable() -> None:
    frame = _frame({L_KNEE: _kp(0.0, 0.0)})
    metric = angle_metric(L_HIP, L_KNEE, L_ANKLE)
    assert metric(frame) is None


def test_inverted_angle_metric() -> None:
    frame = _frame(
        {L_HIP: _kp(0.0, -10.0), L_KNEE: _kp(0.0, 0.0), L_ANKLE: _kp(10.0, 0.0)}
    )
    metric = inverted_angle_metric(L_HIP, L_KNEE, L_ANKLE)
    assert metric(frame) == pytest.approx(90.0)  # 180 - 90


def test_horizontal_offset_metric() -> None:
    frame = _frame(
        {
            L_HIP: _kp(10.0, 0.0),
            L_KNEE: _kp(0.0, 0.0),
            L_ANKLE: _kp(0.0, 100.0),
        }
    )
    metric = horizontal_offset_metric(L_HIP, L_KNEE, normalize=(L_KNEE, L_ANKLE))
    assert metric(frame) == pytest.approx(0.10)  # |10-0| / 100


def test_vertical_offset_metric_is_signed() -> None:
    frame = _frame(
        {
            L_HIP: _kp(0.0, -20.0),
            L_KNEE: _kp(0.0, 0.0),
            L_ANKLE: _kp(0.0, 100.0),
        }
    )
    metric = vertical_offset_metric(L_HIP, L_KNEE, normalize=(L_KNEE, L_ANKLE))
    assert metric(frame) == pytest.approx(-0.20)  # (-20-0) / 100


def test_vertical_symmetry_metric() -> None:
    frame = _frame(
        {
            L_HIP: _kp(0.0, 0.0),
            R_HIP: _kp(0.0, 15.0),
            L_KNEE: _kp(0.0, 0.0),
            L_ANKLE: _kp(0.0, 100.0),
        }
    )
    metric = vertical_symmetry_metric(L_HIP, R_HIP, normalize=(L_KNEE, L_ANKLE))
    assert metric(frame) == pytest.approx(0.15)


def test_min_of_and_max_of() -> None:
    frame = _frame({})

    def const(v: float):
        return lambda _f: v

    assert min_of(const(3.0), const(7.0))(frame) == 3.0
    assert max_of(const(3.0), const(7.0))(frame) == 7.0


def test_min_of_ignores_none() -> None:
    frame = _frame({})

    def none(_f):
        return None

    def const(v: float):
        return lambda _f: v

    assert min_of(none, const(5.0))(frame) == 5.0
    assert min_of(none, none)(frame) is None
