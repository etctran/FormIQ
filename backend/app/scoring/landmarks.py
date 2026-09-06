"""Named MediaPipe Pose landmark indices, 2D geometry helpers, and metric
factories used to build per-exercise primary signals and fault rules.

Landmark ordering mirrors cv-engine/include/keypoints.h (33 points,
MediaPipe Pose convention).
"""

from __future__ import annotations

import math
from collections.abc import Callable

from app.schemas.keypoint import Frame, Keypoint

NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_HEEL, R_HEEL = 29, 30
L_FOOT_INDEX, R_FOOT_INDEX = 31, 32

Point = tuple[float, float]
PointRef = int | tuple[int, int]
Metric = Callable[[Frame], float | None]

MIN_VISIBILITY = 0.5


def landmark(frame: Frame, index: int) -> Keypoint | None:
    """The landmark at `index`, or None if the frame has no landmarks
    (undetected) or its visibility is below MIN_VISIBILITY."""
    if not frame.landmarks:
        return None
    kp = frame.landmarks[index]
    if kp.visibility < MIN_VISIBILITY:
        return None
    return kp


def midpoint(frame: Frame, index_a: int, index_b: int) -> Point | None:
    """Midpoint of two landmarks (e.g. left/right hip), or None if either
    is unresolvable."""
    a, b = landmark(frame, index_a), landmark(frame, index_b)
    if a is None or b is None:
        return None
    return ((a.x + b.x) / 2, (a.y + b.y) / 2)


def _resolve(frame: Frame, ref: PointRef) -> Point | None:
    if isinstance(ref, tuple):
        return midpoint(frame, ref[0], ref[1])
    kp = landmark(frame, ref)
    return None if kp is None else (kp.x, kp.y)


def angle_between(a: Point, b: Point, c: Point) -> float:
    """Angle at vertex `b`, between rays b->a and b->c, in degrees, from
    (x, y) only. Returns a value in [0, 180]; 0.0 if either ray has
    zero length."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    mag1, mag2 = math.hypot(*v1), math.hypot(*v2)
    if mag1 == 0 or mag2 == 0:
        return 0.0
    cos_theta = (v1[0] * v2[0] + v1[1] * v2[1]) / (mag1 * mag2)
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.degrees(math.acos(cos_theta))


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def angle_metric(a: PointRef, vertex: PointRef, c: PointRef) -> Metric:
    """Metric factory: angle at `vertex` between rays to `a` and `c`.
    Each of a/vertex/c may be a single landmark index or an (L, R) pair
    (resolved to their midpoint)."""

    def metric(frame: Frame) -> float | None:
        pa, pv, pc = _resolve(frame, a), _resolve(frame, vertex), _resolve(frame, c)
        if pa is None or pv is None or pc is None:
            return None
        return angle_between(pa, pv, pc)

    return metric


def inverted_angle_metric(a: PointRef, vertex: PointRef, c: PointRef) -> Metric:
    """Like angle_metric, but returns 180 - angle. Used where "rest" is
    the flexed position and "peak" is the extended one (e.g. overhead
    press), so the raw metric still follows the high-at-rest convention."""
    base = angle_metric(a, vertex, c)

    def metric(frame: Frame) -> float | None:
        v = base(frame)
        return None if v is None else 180.0 - v

    return metric


def horizontal_offset_metric(
    point: PointRef, reference: PointRef, normalize: tuple[PointRef, PointRef]
) -> Metric:
    """abs(point.x - reference.x) / distance(*normalize). Each of
    point/reference/normalize's two ends may be a single landmark index
    or an (L, R) pair."""

    def metric(frame: Frame) -> float | None:
        p, r = _resolve(frame, point), _resolve(frame, reference)
        n1, n2 = _resolve(frame, normalize[0]), _resolve(frame, normalize[1])
        if p is None or r is None or n1 is None or n2 is None:
            return None
        ref_len = distance(n1, n2)
        if ref_len < 1e-6:
            return None
        return abs(p[0] - r[0]) / ref_len

    return metric


def vertical_offset_metric(
    point: PointRef, reference: PointRef, normalize: tuple[PointRef, PointRef]
) -> Metric:
    """(point.y - reference.y) / distance(*normalize) — signed, so
    direction (e.g. "lifted above" vs "below") is preserved."""

    def metric(frame: Frame) -> float | None:
        p, r = _resolve(frame, point), _resolve(frame, reference)
        n1, n2 = _resolve(frame, normalize[0]), _resolve(frame, normalize[1])
        if p is None or r is None or n1 is None or n2 is None:
            return None
        ref_len = distance(n1, n2)
        if ref_len < 1e-6:
            return None
        return (p[1] - r[1]) / ref_len

    return metric


def vertical_symmetry_metric(left: int, right: int, normalize: tuple[PointRef, PointRef]) -> Metric:
    """abs(left.y - right.y) / distance(*normalize) — for detecting
    left/right asymmetry (e.g. an uneven bar path)."""

    def metric(frame: Frame) -> float | None:
        pl, pr = landmark(frame, left), landmark(frame, right)
        n1, n2 = _resolve(frame, normalize[0]), _resolve(frame, normalize[1])
        if pl is None or pr is None or n1 is None or n2 is None:
            return None
        ref_len = distance(n1, n2)
        if ref_len < 1e-6:
            return None
        return abs(pl.y - pr.y) / ref_len

    return metric


def min_of(metric_a: Metric, metric_b: Metric) -> Metric:
    """Combinator: the smaller of two metrics' values this frame,
    ignoring whichever side is None. None if both are None."""

    def metric(frame: Frame) -> float | None:
        va, vb = metric_a(frame), metric_b(frame)
        vals = [v for v in (va, vb) if v is not None]
        return min(vals) if vals else None

    return metric


def max_of(metric_a: Metric, metric_b: Metric) -> Metric:
    """Combinator: the larger of two metrics' values this frame, ignoring
    whichever side is None. None if both are None."""

    def metric(frame: Frame) -> float | None:
        va, vb = metric_a(frame), metric_b(frame)
        vals = [v for v in (va, vb) if v is not None]
        return max(vals) if vals else None

    return metric
