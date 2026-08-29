# Backend Rep-Segmentation + Form-Accuracy Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn cv-engine's real per-frame keypoints into real `RepScore`s (rep boundaries + per-exercise fault detection + `form_accuracy`) for all 8 exercises, replacing the always-`[]` `reps` field in `/analyze/{exercise}`.

**Architecture:** New `backend/app/scoring/` package: a generic pipeline (landmark geometry → per-video-normalized signal → 4-phase state machine → declarative per-exercise fault rules → weighted-penalty score) driven by 8 small, declarative `ExerciseProfile` modules. `routes.py` changes by wiring this pipeline in; no schema changes.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, numpy (new dependency), pytest.

**Spec:** [docs/superpowers/specs/2026-08-29-backend-rep-scoring-design.md](../specs/2026-08-29-backend-rep-scoring-design.md)

## Global Constraints

- Keypoints are raw video **pixel coordinates**, not normalized 0–1. Joint angles are scale-invariant by construction; any distance-based metric must be divided by a per-frame body-length reference (never a raw pixel distance).
- `numpy` is a new backend dependency (added in Task 1). No `scipy`.
- Camera angle is fixed per exercise, no detection: side view for squat/deadlift/lunge/row; front view for bench_press/overhead_press; front/three-quarter for pushup/pullup.
- Primary signal convention: 1.0 = rest posture, 0.0 = peak-effort posture, for every exercise (`overhead_press` inverts its raw elbow angle to satisfy this).
- Phase hysteresis (fixed, not per-exercise): `REST` enter > 0.85 / exit < 0.75; `PEAK` enter < 0.15 / exit > 0.25.
- `form_accuracy = clamp(1.0 - sum(penalty for each fired fault), 0.0, 1.0)`.
- No changes to `RepScore` / `AnalysisResponse` / the `/analyze/{exercise}` route signature (`backend/app/schemas/analysis.py`).
- Low-visibility landmarks (`visibility < 0.5`) are treated as missing; a raw-signal gap longer than 1.0s splits segmentation rather than being interpolated over.
- Videos with fewer than 10 usable frames return `reps: []` without running the pipeline.
- Scoring unit tests use only synthetic `Frame`/`Keypoint` fixtures (`app.schemas.keypoint`) — no video, no `cv_engine` dependency. `cv_engine` is still a transitive import for the whole test suite via `app.main` → `app.api.routes`, same as today.
- Ruff line-length is 100 (`backend/pyproject.toml`); run `ruff check backend` if convenient after each task.
- Run tests from the repo root as `pytest backend/tests/...` (matches `CLAUDE.md`'s documented `pytest backend/tests`).

---

## File Structure

```
backend/app/scoring/
  __init__.py         # empty (package marker)
  landmarks.py         # landmark indices + geometry primitives + metric-factory functions
  signal.py            # raw values -> per-video-normalized SignalSegment list
  phases.py            # Phase enum + phase state machine -> RepWindow list
  rules.py              # FaultRule, threshold_fault factory, evaluate_fault_rules, compute_form_accuracy
  pipeline.py           # analyze(exercise, frames) -> list[RepScore]
  profiles/
    __init__.py         # ExerciseProfile, registry, get_profile/register_profile
    squat.py
    deadlift.py
    bench_press.py
    overhead_press.py
    lunge.py
    pushup.py
    pullup.py
    row.py

backend/tests/scoring/
  __init__.py
  fixtures.py           # generic synthetic-Frame test toolkit (no cv_engine)
  test_landmarks.py
  test_signal.py
  test_phases.py
  test_rules.py
  test_profiles_registry.py
  test_squat.py
  test_deadlift.py
  test_bench_press.py
  test_overhead_press.py
  test_lunge.py
  test_pushup.py
  test_pullup.py
  test_row.py
  test_pipeline.py

backend/app/api/routes.py   # modified: wire scoring.pipeline into analyze()
backend/tests/test_main.py  # modified: rename one test, add one wiring test
backend/pyproject.toml      # modified: add numpy dependency
```

---

## Task 1: Landmark geometry primitives

**Files:**
- Modify: `backend/pyproject.toml` (add `numpy` to `dependencies`)
- Create: `backend/app/scoring/__init__.py` (empty)
- Create: `backend/app/scoring/landmarks.py`
- Test: `backend/tests/scoring/__init__.py` (empty)
- Test: `backend/tests/scoring/test_landmarks.py`

**Interfaces:**
- Produces (used by every later task): landmark index constants `NOSE, L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW, L_WRIST, R_WRIST, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE, L_HEEL, R_HEEL, L_FOOT_INDEX, R_FOOT_INDEX`; type alias `PointRef = int | tuple[int, int]`; functions `landmark(frame, index) -> Keypoint | None`, `midpoint(frame, i, j) -> tuple[float,float] | None`, `angle_between(a, b, c) -> float`, `distance(a, b) -> float`; metric factories `angle_metric(a, vertex, c)`, `inverted_angle_metric(a, vertex, c)`, `horizontal_offset_metric(point, reference, normalize)`, `vertical_offset_metric(point, reference, normalize)`, `vertical_symmetry_metric(left, right, normalize)`, `min_of(metric_a, metric_b)`, `max_of(metric_a, metric_b)` — every metric factory returns `Callable[[Frame], float | None]`.

- [ ] **Step 1: Add numpy to backend dependencies**

Edit `backend/pyproject.toml`'s `dependencies` list:

```toml
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "python-multipart>=0.0.12",
  "numpy>=2.0",
  "cv-engine",
]
```

Run: `cd backend && uv sync` (or `pip install -e .` if not using uv)
Expected: installs numpy into the backend environment without error.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/scoring/__init__.py` (empty file).

Create `backend/tests/scoring/test_landmarks.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_landmarks.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring'` (or `ImportError`).

- [ ] **Step 4: Write the implementation**

Create `backend/app/scoring/__init__.py` (empty).

Create `backend/app/scoring/landmarks.py`:

```python
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


def horizontal_offset_metric(point: PointRef, reference: PointRef, normalize: tuple[PointRef, PointRef]) -> Metric:
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


def vertical_offset_metric(point: PointRef, reference: PointRef, normalize: tuple[PointRef, PointRef]) -> Metric:
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/scoring/test_landmarks.py -v`
Expected: PASS (20 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/scoring backend/tests/scoring
git commit -m "feat: add landmark geometry primitives for rep scoring"
```

---

## Task 2: Synthetic test-fixture toolkit

**Files:**
- Create: `backend/tests/scoring/fixtures.py`
- Test: `backend/tests/scoring/test_fixtures.py`

**Interfaces:**
- Consumes: `app.scoring.landmarks.angle_between` (Task 1) — used to cross-check `point_at_angle`.
- Produces (used by Tasks 7–15's exercise tests and pipeline tests): `NUM_LANDMARKS`, `FPS`, `NEUTRAL_POSE: dict[int, tuple[float,float,float,float]]`, `kp(x, y) -> tuple[float,float,float,float]` (visibility=1.0, z=0.0), `neutral_xy(index) -> tuple[float,float]`, `make_frame(timestamp_sec, overrides) -> Frame`, `make_frames(overrides_sequence, fps=FPS) -> list[Frame]`, `point_at_angle(vertex, reference, angle_deg, length) -> tuple[float,float]`, `linspace_rep(rest_value, peak_value, frames_down=20, frames_up=20) -> list[float]`, `repeat_trajectory(single_rep, num_reps, rest_value, rest_frames=5) -> list[float]`, `active_frame_offsets(num_reps, frames_down, frames_up, rest_frames) -> list[list[int]]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_fixtures.py`:

```python
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
    assert values[-1] == pytest.approx(70.0, abs=15.0)


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_fixtures.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'tests.scoring.fixtures'`.

- [ ] **Step 3: Write the implementation**

Create `backend/tests/scoring/fixtures.py`:

```python
"""Generic synthetic-Frame test toolkit. No cv_engine / video dependency.

Exercise-specific joint trajectories are built in each exercise's own
test module using these primitives.
"""

from __future__ import annotations

import math

import numpy as np

from app.schemas.keypoint import Frame, Keypoint

NUM_LANDMARKS = 33
FPS = 30.0

# A plausible standing-neutral pose, in video pixel coordinates (roughly
# a 720x1280 portrait frame). Index -> (x, y, z, visibility).
NEUTRAL_POSE: dict[int, tuple[float, float, float, float]] = {
    0: (360.0, 200.0, 0.0, 1.0),  # nose
    11: (300.0, 320.0, 0.0, 1.0),  # L shoulder
    12: (420.0, 320.0, 0.0, 1.0),  # R shoulder
    13: (290.0, 460.0, 0.0, 1.0),  # L elbow
    14: (430.0, 460.0, 0.0, 1.0),  # R elbow
    15: (285.0, 600.0, 0.0, 1.0),  # L wrist
    16: (435.0, 600.0, 0.0, 1.0),  # R wrist
    23: (310.0, 620.0, 0.0, 1.0),  # L hip
    24: (410.0, 620.0, 0.0, 1.0),  # R hip
    25: (310.0, 860.0, 0.0, 1.0),  # L knee
    26: (410.0, 860.0, 0.0, 1.0),  # R knee
    27: (310.0, 1100.0, 0.0, 1.0),  # L ankle
    28: (410.0, 1100.0, 0.0, 1.0),  # R ankle
    29: (310.0, 1140.0, 0.0, 1.0),  # L heel
    30: (410.0, 1140.0, 0.0, 1.0),  # R heel
    31: (330.0, 1150.0, 0.0, 1.0),  # L foot index
    32: (390.0, 1150.0, 0.0, 1.0),  # R foot index
}


def kp(x: float, y: float) -> tuple[float, float, float, float]:
    """Shorthand override tuple: (x, y, z=0.0, visibility=1.0)."""
    return (x, y, 0.0, 1.0)


def neutral_xy(index: int) -> tuple[float, float]:
    """The (x, y) of `index` in NEUTRAL_POSE, before any override."""
    x, y, _z, _vis = NEUTRAL_POSE[index]
    return (x, y)


def make_frame(timestamp_sec: float, overrides: dict[int, tuple[float, float, float, float]]) -> Frame:
    """A Frame with all 33 landmarks: NEUTRAL_POSE layered with `overrides`
    (index -> (x, y, z, visibility)). Indices with no neutral-pose entry
    and no override default to (0, 0, 0, visibility=0.0) — i.e.
    unresolvable, matching real undetected landmarks."""
    landmarks = []
    for i in range(NUM_LANDMARKS):
        x, y, z, vis = overrides.get(i, NEUTRAL_POSE.get(i, (0.0, 0.0, 0.0, 0.0)))
        landmarks.append(Keypoint(x=x, y=y, z=z, visibility=vis))
    return Frame(timestamp_sec=timestamp_sec, landmarks=landmarks)


def make_frames(
    overrides_sequence: list[dict[int, tuple[float, float, float, float]]], fps: float = FPS
) -> list[Frame]:
    """One Frame per element of `overrides_sequence`, timestamped at `fps`."""
    return [make_frame(i / fps, overrides) for i, overrides in enumerate(overrides_sequence)]


def point_at_angle(vertex: tuple[float, float], reference: tuple[float, float], angle_deg: float, length: float) -> tuple[float, float]:
    """A point P at `length` from `vertex`, such that the angle at
    `vertex` between rays vertex->reference and vertex->P is `angle_deg`
    (rotating counter-clockwise from the reference direction, in screen
    coordinates where +y is down). Inverse of angle_between for
    constructing fixtures with a known target angle."""
    ref_dx, ref_dy = reference[0] - vertex[0], reference[1] - vertex[1]
    ref_angle = math.atan2(ref_dy, ref_dx)
    theta = ref_angle + math.radians(angle_deg)
    return (vertex[0] + length * math.cos(theta), vertex[1] + length * math.sin(theta))


def linspace_rep(rest_value: float, peak_value: float, frames_down: int = 20, frames_up: int = 20) -> list[float]:
    """One rep's target-scalar trajectory: linearly interpolated
    rest_value -> peak_value over `frames_down` frames, then back to
    rest_value over `frames_up` frames."""
    down = np.linspace(rest_value, peak_value, frames_down).tolist()
    up = np.linspace(peak_value, rest_value, frames_up).tolist()
    return down + up


def repeat_trajectory(single_rep: list[float], num_reps: int, rest_value: float, rest_frames: int = 5) -> list[float]:
    """Repeat `single_rep` `num_reps` times, with `rest_frames` frames of
    `rest_value` before, between, and after each rep, so REST phases are
    clearly established for the phase state machine."""
    rest = [rest_value] * rest_frames
    out = list(rest)
    for _ in range(num_reps):
        out.extend(single_rep)
        out.extend(rest)
    return out


def active_frame_offsets(num_reps: int, frames_down: int, frames_up: int, rest_frames: int) -> list[list[int]]:
    """Global frame indices spanning the DRIVE->PEAK->RECOVER portion of
    each rep (everything except the REST padding between reps), given the
    same frames_down/frames_up/rest_frames used to build the trajectory
    via repeat_trajectory(linspace_rep(...), ...). Used by fault tests to
    know which frames to override with a fault-triggering landmark
    position."""
    rep_len = frames_down + frames_up
    offsets = []
    cursor = rest_frames
    for _ in range(num_reps):
        offsets.append(list(range(cursor, cursor + rep_len)))
        cursor += rep_len + rest_frames
    return offsets
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/scoring/test_fixtures.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/scoring/fixtures.py backend/tests/scoring/test_fixtures.py
git commit -m "test: add synthetic Frame fixture toolkit for scoring tests"
```

---

## Task 3: Signal normalization

**Files:**
- Create: `backend/app/scoring/signal.py`
- Test: `backend/tests/scoring/test_signal.py`

**Interfaces:**
- Produces (used by Task 4's `segment_phases` and Task 15's `pipeline.py`): `@dataclass SignalSegment(frame_indices: list[int], timestamps: np.ndarray, values: np.ndarray)`, `build_signal_segments(raw_values: list[float | None], timestamps: list[float], max_gap_sec: float = 1.0, smoothing_window_sec: float = 0.3) -> list[SignalSegment]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_signal.py`:

```python
import numpy as np
import pytest

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_signal.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.signal'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/signal.py`:

```python
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
    gap_start_ts: float | None = None
    for i in range(n):
        if raw_values[i] is None:
            if gap_start_ts is None:
                gap_start_ts = timestamps[i]
            if timestamps[i] - gap_start_ts > max_gap_sec:
                if current:
                    segments_idx.append(current)
                    current = []
                continue
            current.append(i)
        else:
            gap_start_ts = None
            current.append(i)
    if current:
        segments_idx.append(current)

    segments: list[SignalSegment] = []
    for idx_list in segments_idx:
        resolvable = [i for i in idx_list if raw_values[i] is not None]
        if len(resolvable) < 2:
            continue

        ts = np.array([timestamps[i] for i in idx_list], dtype=float)
        raw = np.array(
            [raw_values[i] if raw_values[i] is not None else np.nan for i in idx_list],
            dtype=float,
        )
        nan_mask = np.isnan(raw)
        if nan_mask.any():
            raw[nan_mask] = np.interp(ts[nan_mask], ts[~nan_mask], raw[~nan_mask])

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
            smoothed = np.convolve(rescaled, kernel, mode="same")
        else:
            smoothed = rescaled

        segments.append(SignalSegment(frame_indices=idx_list, timestamps=ts, values=smoothed))

    return segments
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/scoring/test_signal.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/signal.py backend/tests/scoring/test_signal.py
git commit -m "feat: add per-video signal normalization for rep scoring"
```

---

## Task 4: Phase state machine

**Files:**
- Create: `backend/app/scoring/phases.py`
- Test: `backend/tests/scoring/test_phases.py`

**Interfaces:**
- Consumes: `app.scoring.signal.SignalSegment` (Task 3).
- Produces (used by Task 5's `evaluate_fault_rules` and Task 15's `pipeline.py`): `class Phase(Enum)` with members `REST, DRIVE, PEAK, RECOVER`; `@dataclass RepWindow(start_sec: float, end_sec: float, frame_indices: list[int], phase_by_frame_index: dict[int, Phase])`; `segment_phases(segment: SignalSegment) -> list[RepWindow]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_phases.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_phases.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.phases'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/phases.py`:

```python
"""Generic 4-phase state machine segmenting a normalized [0, 1] signal
into reps. 1.0 = rest posture, 0.0 = peak-effort posture (see signal.py).
A rep is one full REST -> DRIVE -> PEAK -> RECOVER -> REST cycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from app.scoring.signal import SignalSegment

REST_ENTER, REST_EXIT = 0.85, 0.75
PEAK_ENTER, PEAK_EXIT = 0.15, 0.25


class Phase(Enum):
    REST = "rest"
    DRIVE = "drive"
    PEAK = "peak"
    RECOVER = "recover"


@dataclass
class RepWindow:
    start_sec: float
    end_sec: float
    frame_indices: list[int]
    phase_by_frame_index: dict[int, Phase]


def _phase_sequence(values: np.ndarray) -> list[Phase]:
    if values[0] >= REST_ENTER:
        current = Phase.REST
    elif values[0] <= PEAK_ENTER:
        current = Phase.PEAK
    else:
        current = Phase.DRIVE

    phases: list[Phase] = []
    for v in values:
        if current == Phase.REST:
            if v < REST_EXIT:
                current = Phase.DRIVE
        elif current == Phase.DRIVE:
            if v <= PEAK_ENTER:
                current = Phase.PEAK
            elif v >= REST_ENTER:
                current = Phase.REST
        elif current == Phase.PEAK:
            if v > PEAK_EXIT:
                current = Phase.RECOVER
        elif current == Phase.RECOVER:
            if v >= REST_ENTER:
                current = Phase.REST
            elif v <= PEAK_ENTER:
                current = Phase.PEAK
        phases.append(current)
    return phases


def segment_phases(segment: SignalSegment) -> list[RepWindow]:
    """Rep windows within one SignalSegment. A rep is delimited by two
    REST-phase frames with a PEAK-phase frame somewhere between them; a
    trailing partial rep (never returns to REST) is dropped."""
    phases = _phase_sequence(segment.values)
    reps: list[RepWindow] = []
    rest_start_local: int | None = None
    seen_peak = False

    for local_i, phase in enumerate(phases):
        if phase == Phase.REST:
            if rest_start_local is None:
                rest_start_local = local_i
            elif seen_peak:
                frame_indices = segment.frame_indices[rest_start_local : local_i + 1]
                phase_by_frame_index = {
                    segment.frame_indices[j]: phases[j]
                    for j in range(rest_start_local, local_i + 1)
                }
                reps.append(
                    RepWindow(
                        start_sec=float(segment.timestamps[rest_start_local]),
                        end_sec=float(segment.timestamps[local_i]),
                        frame_indices=frame_indices,
                        phase_by_frame_index=phase_by_frame_index,
                    )
                )
                rest_start_local = local_i
                seen_peak = False
        elif phase == Phase.PEAK:
            seen_peak = True

    return reps
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/scoring/test_phases.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/phases.py backend/tests/scoring/test_phases.py
git commit -m "feat: add phase state machine for rep segmentation"
```

---

## Task 5: Fault rules and scoring

**Files:**
- Create: `backend/app/scoring/rules.py`
- Test: `backend/tests/scoring/test_rules.py`

**Interfaces:**
- Consumes: `app.scoring.phases.Phase, RepWindow` (Task 4); `app.schemas.keypoint.Frame`.
- Produces (used by Task 6's `ExerciseProfile` and every exercise profile in Tasks 7–14, and Task 15's `pipeline.py`): `@dataclass FaultRule(name: str, phases: frozenset[Phase], metric: Callable[[Frame], float|None], check: Callable[[float], bool], penalty: float, min_violating_frames_ratio: float = 0.5)`; `threshold_fault(name, metric, phases, comparison, threshold, penalty, min_violating_frames_ratio=0.5) -> FaultRule`; `evaluate_fault_rules(frames: list[Frame], rep: RepWindow, rules: list[FaultRule]) -> list[str]`; `compute_form_accuracy(fired_fault_names: list[str], rules: list[FaultRule]) -> float`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_rules.py`:

```python
import operator

import pytest

from app.schemas.keypoint import Frame, Keypoint
from app.scoring.phases import Phase, RepWindow
from app.scoring.rules import compute_form_accuracy, evaluate_fault_rules, threshold_fault


def _frame() -> Frame:
    return Frame(timestamp_sec=0.0, landmarks=[Keypoint(x=0, y=0, z=0, visibility=1.0)] * 33)


def _rep(phase_by_index: dict[int, Phase]) -> RepWindow:
    indices = sorted(phase_by_index)
    return RepWindow(
        start_sec=0.0,
        end_sec=1.0,
        frame_indices=indices,
        phase_by_frame_index=phase_by_index,
    )


def test_fault_fires_when_majority_of_in_phase_frames_violate() -> None:
    frames = [_frame() for _ in range(6)]
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
    frames = [_frame() for _ in range(6)]
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
    frames = [_frame() for _ in range(2)]
    rep = _rep({0: Phase.REST, 1: Phase.REST})
    rule = threshold_fault(
        name="whatever", metric=lambda f: 100.0, phases={Phase.PEAK},
        comparison=operator.gt, threshold=0.0, penalty=0.1,
    )
    assert evaluate_fault_rules(frames, rep, [rule]) == []


def test_none_metric_values_excluded_from_ratio() -> None:
    frames = [_frame() for _ in range(3)]
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
    frames = [_frame() for _ in range(2)]
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_rules.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.rules'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/rules.py`:

```python
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


def evaluate_fault_rules(frames: list[Frame], rep: RepWindow, rules: list[FaultRule]) -> list[str]:
    """Fault names that fire for this rep: for each rule, of the rep's
    frames whose phase is in rule.phases and whose metric resolves, at
    least min_violating_frames_ratio must violate rule.check."""
    fired: list[str] = []
    for rule in rules:
        in_phase = [i for i in rep.frame_indices if rep.phase_by_frame_index[i] in rule.phases]
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


def compute_form_accuracy(fired_fault_names: list[str], rules: list[FaultRule]) -> float:
    penalty_by_name = {r.name: r.penalty for r in rules}
    total_penalty = sum(penalty_by_name.get(name, 0.0) for name in fired_fault_names)
    return max(0.0, min(1.0, 1.0 - total_penalty))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/scoring/test_rules.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/rules.py backend/tests/scoring/test_rules.py
git commit -m "feat: add declarative fault rules and form_accuracy scoring"
```

---

## Task 6: Exercise profile registry

**Files:**
- Create: `backend/app/scoring/profiles/__init__.py`
- Test: `backend/tests/scoring/test_profiles_registry.py`

**Interfaces:**
- Consumes: `app.schemas.analysis.Exercise`; `app.scoring.rules.FaultRule` (Task 5).
- Produces (used by Tasks 7–15): `@dataclass ExerciseProfile(primary_signal: Callable[[Frame], float|None], fault_rules: list[FaultRule])`; `register_profile(exercise: Exercise, profile: ExerciseProfile) -> None`; `get_profile(exercise: Exercise) -> ExerciseProfile`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_profiles_registry.py`:

```python
import pytest

from app.schemas.analysis import Exercise


def test_register_and_get_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scoring.profiles as profiles_module
    from app.scoring.profiles import ExerciseProfile, get_profile, register_profile

    # Skip _ensure_loaded's real per-exercise imports so this test is
    # unaffected by however many real profiles exist by the time it runs.
    monkeypatch.setattr(profiles_module, "_loaded", True)

    dummy = ExerciseProfile(primary_signal=lambda frame: 1.0, fault_rules=[])
    register_profile(Exercise.SQUAT, dummy)
    assert get_profile(Exercise.SQUAT) is dummy


def test_get_profile_raises_for_unregistered_exercise(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scoring.profiles as profiles_module
    from app.scoring.profiles import get_profile

    monkeypatch.setattr(profiles_module, "_loaded", True)
    monkeypatch.setattr(profiles_module, "_REGISTRY", {})
    with pytest.raises(KeyError):
        get_profile(Exercise.SQUAT)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_profiles_registry.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.profiles'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/profiles/__init__.py`:

```python
"""Registry of ExerciseProfile, one per Exercise. Profile modules
(squat.py, deadlift.py, ...) call register_profile(...) at import time;
_ensure_loaded imports each of them lazily on first get_profile() call,
so importing this package alone never requires every profile module to
exist."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.schemas.analysis import Exercise
from app.schemas.keypoint import Frame
from app.scoring.rules import FaultRule


@dataclass
class ExerciseProfile:
    primary_signal: Callable[[Frame], float | None]
    fault_rules: list[FaultRule]


_REGISTRY: dict[Exercise, ExerciseProfile] = {}
_loaded = False


def register_profile(exercise: Exercise, profile: ExerciseProfile) -> None:
    _REGISTRY[exercise] = profile


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    # Each import below registers its exercise's profile as a side
    # effect. Extended by one line per exercise in Tasks 7-14.
    _loaded = True


def get_profile(exercise: Exercise) -> ExerciseProfile:
    _ensure_loaded()
    return _REGISTRY[exercise]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/scoring/test_profiles_registry.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/profiles/__init__.py backend/tests/scoring/test_profiles_registry.py
git commit -m "feat: add exercise profile registry"
```

---

## Task 7: Squat profile

**Files:**
- Modify: `backend/app/scoring/profiles/__init__.py` (`_ensure_loaded`: import `squat`)
- Create: `backend/app/scoring/profiles/squat.py`
- Test: `backend/tests/scoring/test_squat.py`

**Interfaces:**
- Consumes: `app.scoring.landmarks` factories/indices (Task 1); `app.scoring.profiles.ExerciseProfile, register_profile` (Task 6); `app.scoring.rules.threshold_fault` (Task 5); `app.scoring.phases.Phase` (Task 4); `tests.scoring.fixtures` (Task 2).
- Produces: `app.scoring.profiles.squat.PROFILE: ExerciseProfile`, registered under `Exercise.SQUAT`. Fault names: `insufficient_depth`, `forward_knee_travel`, `back_rounding`, `heel_rise`.

This task establishes the template every later exercise task (8–14) follows: build a "clean" 2-rep trajectory via the exercise's primary joint, assert exact segmentation with no faults; then one test per fault, using either (a) a shallower/insufficient trajectory when the fault reuses the primary metric itself, or (b) a landmark override on a point the primary trajectory doesn't touch (or computed relative to whichever primary landmark *is* dynamic, when the fault's own landmark depends on it).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_squat.py`:

```python
import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    active_frame_offsets,
    kp,
    linspace_rep,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)

L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_SHOULDER, R_SHOULDER = 11, 12
L_HEEL, R_HEEL = 29, 30
L_FOOT_INDEX, R_FOOT_INDEX = 31, 32

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _knee_trajectory_frames(knee_angles: list[float]) -> list[dict[int, tuple]]:
    """Overrides driving HIP position (per side) so angle(hip,knee,ankle)
    follows `knee_angles`, with KNEE/ANKLE fixed at their neutral pose."""
    knee_l, ankle_l = neutral_xy(L_KNEE), neutral_xy(L_ANKLE)
    knee_r, ankle_r = neutral_xy(R_KNEE), neutral_xy(R_ANKLE)
    overrides_sequence = []
    for angle in knee_angles:
        hip_l = point_at_angle(knee_l, ankle_l, angle, length=250.0)
        hip_r = point_at_angle(knee_r, ankle_r, angle, length=250.0)
        overrides_sequence.append({L_HIP: kp(*hip_l), R_HIP: kp(*hip_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _knee_trajectory_frames(angles)


def test_clean_squat_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.SQUAT, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_insufficient_depth_fires_on_shallow_trajectory() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 130.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_knee_trajectory_frames(angles))
    reps = analyze(Exercise.SQUAT, frames)
    assert len(reps) >= 1
    assert "insufficient_depth" in reps[0].faults


def test_forward_knee_travel_fires_when_foot_index_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    knee_l_x, _ = neutral_xy(L_KNEE)
    knee_l_y = neutral_xy(L_KNEE)[1]
    for i in active:
        # Foot index placed far behind the knee (knee travels well past it).
        overrides[i][L_FOOT_INDEX] = kp(knee_l_x - 200.0, knee_l_y + 20.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.SQUAT, frames)
    assert len(reps) >= 1
    assert "forward_knee_travel" in reps[0].faults


def test_back_rounding_fires_when_shoulder_collapses_relative_to_hip() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    knee_l, ankle_l = neutral_xy(L_KNEE), neutral_xy(L_ANKLE)
    knee_r, ankle_r = neutral_xy(R_KNEE), neutral_xy(R_ANKLE)
    active = set(active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0])
    overrides_sequence = []
    for local_i, angle in enumerate(angles):
        hip_l = point_at_angle(knee_l, ankle_l, angle, length=250.0)
        hip_r = point_at_angle(knee_r, ankle_r, angle, length=250.0)
        overrides = {L_HIP: kp(*hip_l), R_HIP: kp(*hip_r)}
        if local_i in active:
            # Shoulder placed to make angle(shoulder, hip, knee) ~ 120 deg
            # (a collapsed torso), computed relative to the CURRENT hip
            # position so it doesn't depend on where in the trajectory we are.
            shoulder_l = point_at_angle(hip_l, knee_l, 120.0, length=200.0)
            shoulder_r = point_at_angle(hip_r, knee_r, 120.0, length=200.0)
            overrides[L_SHOULDER] = kp(*shoulder_l)
            overrides[R_SHOULDER] = kp(*shoulder_r)
        overrides_sequence.append(overrides)
    frames = make_frames(overrides_sequence)
    reps = analyze(Exercise.SQUAT, frames)
    assert len(reps) >= 1
    assert "back_rounding" in reps[0].faults


def test_heel_rise_fires_when_heel_lifted() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    ankle_l_x, ankle_l_y = neutral_xy(L_ANKLE)
    for i in active:
        overrides[i][L_HEEL] = kp(ankle_l_x, ankle_l_y - 100.0)  # heel well above ankle
    frames = make_frames(overrides)
    reps = analyze(Exercise.SQUAT, frames)
    assert len(reps) >= 1
    assert "heel_rise" in reps[0].faults
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_squat.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.pipeline'` (Task 15 doesn't exist yet — see note below).

> **Note:** this task's test imports `app.scoring.pipeline.analyze`, which
> is written in Task 15. Until Task 15 lands, this test will fail/error
> for that reason even after `squat.py` is written — that's expected.
> Step 4 below still writes and registers the real profile now (so Task
> 15 has all 8 profiles ready); confirm the profile module itself is
> correct by running Step 4a (a temporary direct check), then leave this
> test file as-is for Task 15 to make pass end-to-end.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/profiles/squat.py`:

```python
"""Squat profile (side view). Primary signal: knee angle
(hip-knee-ankle). Rest = standing (~170 deg+); peak = deepest point."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ANKLE,
    L_FOOT_INDEX,
    L_HEEL,
    L_HIP,
    L_KNEE,
    L_SHOULDER,
    R_ANKLE,
    R_FOOT_INDEX,
    R_HEEL,
    R_HIP,
    R_KNEE,
    R_SHOULDER,
    angle_metric,
    horizontal_offset_metric,
    vertical_offset_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

HIP = (L_HIP, R_HIP)
KNEE = (L_KNEE, R_KNEE)
ANKLE = (L_ANKLE, R_ANKLE)
SHOULDER = (L_SHOULDER, R_SHOULDER)
FOOT_INDEX = (L_FOOT_INDEX, R_FOOT_INDEX)
HEEL = (L_HEEL, R_HEEL)

_KNEE_ANGLE = angle_metric(HIP, KNEE, ANKLE)

PROFILE = ExerciseProfile(
    primary_signal=_KNEE_ANGLE,
    fault_rules=[
        threshold_fault(
            name="insufficient_depth",
            metric=_KNEE_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=100.0,
            penalty=0.20,
        ),
        threshold_fault(
            name="forward_knee_travel",
            metric=horizontal_offset_metric(KNEE, FOOT_INDEX, normalize=(KNEE, ANKLE)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.5,
            penalty=0.15,
        ),
        threshold_fault(
            name="back_rounding",
            metric=angle_metric(SHOULDER, HIP, KNEE),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.lt,
            threshold=150.0,
            penalty=0.15,
        ),
        threshold_fault(
            name="heel_rise",
            metric=vertical_offset_metric(HEEL, ANKLE, normalize=(FOOT_INDEX, ANKLE)),
            phases={Phase.PEAK},
            comparison=operator.lt,
            threshold=-0.3,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.SQUAT, PROFILE)
```

Modify `backend/app/scoring/profiles/__init__.py`'s `_ensure_loaded`:

```python
def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    from app.scoring.profiles import squat  # noqa: F401

    _loaded = True
```

- [ ] **Step 4: Run tests**

Run: `pytest backend/tests/scoring/test_squat.py -v`
Expected: still FAILs/ERRORs on the `app.scoring.pipeline` import (Task 15 not done yet) — this is expected per the note in Step 2. Confirm no *other* error (e.g. no `ImportError` from within `squat.py` itself) by running:

```bash
cd backend && python -c "from app.scoring.profiles.squat import PROFILE; print(PROFILE.primary_signal, len(PROFILE.fault_rules))"
```

Expected: prints the function repr and `4` without raising.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/profiles/squat.py backend/app/scoring/profiles/__init__.py backend/tests/scoring/test_squat.py
git commit -m "feat: add squat exercise profile"
```

---

## Task 8: Deadlift profile

**Files:**
- Modify: `backend/app/scoring/profiles/__init__.py` (`_ensure_loaded`: add `deadlift` import)
- Create: `backend/app/scoring/profiles/deadlift.py`
- Test: `backend/tests/scoring/test_deadlift.py`

**Interfaces:**
- Same shape as Task 7. Produces `app.scoring.profiles.deadlift.PROFILE`, registered under `Exercise.DEADLIFT`. Fault names: `back_rounding`, `bar_path_drift`, `hyperextension_lockout`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_deadlift.py`:

```python
import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    active_frame_offsets,
    kp,
    linspace_rep,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)

NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _hinge_trajectory_frames(hip_angles: list[float]) -> list[dict[int, tuple]]:
    """Overrides driving SHOULDER position (per side) so
    angle(shoulder,hip,knee) follows `hip_angles`, with HIP/KNEE fixed."""
    hip_l, knee_l = neutral_xy(L_HIP), neutral_xy(L_KNEE)
    hip_r, knee_r = neutral_xy(R_HIP), neutral_xy(R_KNEE)
    overrides_sequence = []
    for angle in hip_angles:
        shoulder_l = point_at_angle(hip_l, knee_l, angle, length=300.0)
        shoulder_r = point_at_angle(hip_r, knee_r, angle, length=300.0)
        overrides_sequence.append({L_SHOULDER: kp(*shoulder_l), R_SHOULDER: kp(*shoulder_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 80.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _hinge_trajectory_frames(angles)


def test_clean_deadlift_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.DEADLIFT, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_back_rounding_fires_when_nose_collapses_relative_to_shoulder() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 80.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    hip_l, knee_l = neutral_xy(L_HIP), neutral_xy(L_KNEE)
    active = set(active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0])
    overrides_sequence = []
    for local_i, angle in enumerate(angles):
        shoulder_l = point_at_angle(hip_l, knee_l, angle, length=300.0)
        shoulder_r = shoulder_l  # symmetric enough for this test
        overrides = {L_SHOULDER: kp(*shoulder_l), R_SHOULDER: kp(*shoulder_r)}
        if local_i in active:
            nose = point_at_angle(shoulder_l, hip_l, 140.0, length=150.0)
            overrides[NOSE] = kp(*nose)
        overrides_sequence.append(overrides)
    frames = make_frames(overrides_sequence)
    reps = analyze(Exercise.DEADLIFT, frames)
    assert len(reps) >= 1
    assert "back_rounding" in reps[0].faults


def test_bar_path_drift_fires_when_wrist_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    hip_x, hip_y = neutral_xy(L_HIP)
    for i in active:
        overrides[i][L_WRIST] = kp(hip_x + 150.0, hip_y + 50.0)  # bar drifting away from hip
    frames = make_frames(overrides)
    reps = analyze(Exercise.DEADLIFT, frames)
    assert len(reps) >= 1
    assert "bar_path_drift" in reps[0].faults


def test_hyperextension_lockout_fires_when_wrist_overridden_at_rest() -> None:
    overrides = _clean_overrides(num_reps=1)
    hip_x, hip_y = neutral_xy(L_HIP)
    for i in range(len(overrides)):  # whole sequence, incl. REST padding
        overrides[i][L_WRIST] = kp(hip_x + 150.0, hip_y + 50.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.DEADLIFT, frames)
    assert len(reps) >= 1
    assert "hyperextension_lockout" in reps[0].faults
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_deadlift.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.profiles.deadlift'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/profiles/deadlift.py`:

```python
"""Deadlift profile (side view). Primary signal: hip hinge angle
(shoulder-hip-knee). Rest = standing tall (~170 deg+); peak = bar at
floor."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_HIP,
    L_KNEE,
    L_SHOULDER,
    L_WRIST,
    NOSE,
    R_HIP,
    R_KNEE,
    R_SHOULDER,
    R_WRIST,
    angle_metric,
    horizontal_offset_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
HIP = (L_HIP, R_HIP)
KNEE = (L_KNEE, R_KNEE)
WRIST = (L_WRIST, R_WRIST)

_HIP_HINGE_ANGLE = angle_metric(SHOULDER, HIP, KNEE)

PROFILE = ExerciseProfile(
    primary_signal=_HIP_HINGE_ANGLE,
    fault_rules=[
        threshold_fault(
            name="back_rounding",
            metric=angle_metric(NOSE, SHOULDER, HIP),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.lt,
            threshold=160.0,
            penalty=0.20,
        ),
        threshold_fault(
            name="bar_path_drift",
            metric=horizontal_offset_metric(WRIST, HIP, normalize=(SHOULDER, HIP)),
            phases={Phase.DRIVE, Phase.RECOVER},
            comparison=operator.gt,
            threshold=0.25,
            penalty=0.15,
        ),
        threshold_fault(
            name="hyperextension_lockout",
            metric=horizontal_offset_metric(WRIST, HIP, normalize=(SHOULDER, HIP)),
            phases={Phase.REST, Phase.RECOVER},
            comparison=operator.gt,
            threshold=0.3,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.DEADLIFT, PROFILE)
```

Modify `backend/app/scoring/profiles/__init__.py`'s `_ensure_loaded`:

```python
def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    from app.scoring.profiles import deadlift, squat  # noqa: F401

    _loaded = True
```

- [ ] **Step 4: Verify the module loads (pipeline still pending Task 15)**

```bash
cd backend && python -c "from app.scoring.profiles.deadlift import PROFILE; print(len(PROFILE.fault_rules))"
```

Expected: prints `3` without raising.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/profiles/deadlift.py backend/app/scoring/profiles/__init__.py backend/tests/scoring/test_deadlift.py
git commit -m "feat: add deadlift exercise profile"
```

---

## Task 9: Bench press profile

**Files:**
- Modify: `backend/app/scoring/profiles/__init__.py` (`_ensure_loaded`: add `bench_press` import)
- Create: `backend/app/scoring/profiles/bench_press.py`
- Test: `backend/tests/scoring/test_bench_press.py`

**Interfaces:**
- Same shape as Task 7. Produces `app.scoring.profiles.bench_press.PROFILE`, registered under `Exercise.BENCH_PRESS`. Fault names: `uneven_bar_path`, `partial_lockout`, `flared_elbows`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_bench_press.py`:

```python
import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    active_frame_offsets,
    kp,
    linspace_rep,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)

L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _elbow_trajectory_frames(elbow_angles: list[float]) -> list[dict[int, tuple]]:
    """Overrides driving WRIST position (per side) so
    angle(shoulder,elbow,wrist) follows `elbow_angles`, SHOULDER/ELBOW
    fixed."""
    shoulder_l, elbow_l = neutral_xy(L_SHOULDER), neutral_xy(L_ELBOW)
    shoulder_r, elbow_r = neutral_xy(R_SHOULDER), neutral_xy(R_ELBOW)
    overrides_sequence = []
    for angle in elbow_angles:
        wrist_l = point_at_angle(elbow_l, shoulder_l, angle, length=160.0)
        wrist_r = point_at_angle(elbow_r, shoulder_r, angle, length=160.0)
        overrides_sequence.append({L_WRIST: kp(*wrist_l), R_WRIST: kp(*wrist_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _elbow_trajectory_frames(angles)


def test_clean_bench_press_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.BENCH_PRESS, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_uneven_bar_path_fires_when_one_wrist_offset_vertically() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    for i in active:
        x, y = overrides[i][R_WRIST][0], overrides[i][R_WRIST][1]
        overrides[i][R_WRIST] = kp(x, y + 100.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.BENCH_PRESS, frames)
    assert len(reps) >= 1
    assert "uneven_bar_path" in reps[0].faults


def test_partial_lockout_fires_when_rest_never_reaches_extension() -> None:
    angles = repeat_trajectory(
        linspace_rep(150.0, 70.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=150.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.BENCH_PRESS, frames)
    assert len(reps) >= 1
    assert "partial_lockout" in reps[0].faults


def test_flared_elbows_fires_when_elbow_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    shoulder_x, shoulder_y = neutral_xy(L_SHOULDER)
    for i in active:
        overrides[i][L_ELBOW] = kp(shoulder_x - 250.0, shoulder_y + 100.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.BENCH_PRESS, frames)
    assert len(reps) >= 1
    assert "flared_elbows" in reps[0].faults
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_bench_press.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.profiles.bench_press'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/profiles/bench_press.py`:

```python
"""Bench press profile (front view). Primary signal: elbow angle
(shoulder-elbow-wrist). Rest = arms extended (~170 deg+); peak = bar at
chest."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ELBOW,
    L_HIP,
    L_SHOULDER,
    L_WRIST,
    R_ELBOW,
    R_HIP,
    R_SHOULDER,
    R_WRIST,
    angle_metric,
    horizontal_offset_metric,
    vertical_symmetry_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
ELBOW = (L_ELBOW, R_ELBOW)
WRIST = (L_WRIST, R_WRIST)
HIP = (L_HIP, R_HIP)

_ELBOW_ANGLE = angle_metric(SHOULDER, ELBOW, WRIST)

PROFILE = ExerciseProfile(
    primary_signal=_ELBOW_ANGLE,
    fault_rules=[
        threshold_fault(
            name="uneven_bar_path",
            metric=vertical_symmetry_metric(L_WRIST, R_WRIST, normalize=(L_SHOULDER, R_SHOULDER)),
            phases={Phase.DRIVE, Phase.RECOVER},
            comparison=operator.gt,
            threshold=0.15,
            penalty=0.15,
        ),
        threshold_fault(
            name="partial_lockout",
            metric=_ELBOW_ANGLE,
            phases={Phase.RECOVER, Phase.REST},
            comparison=operator.lt,
            threshold=160.0,
            penalty=0.15,
        ),
        threshold_fault(
            name="flared_elbows",
            metric=horizontal_offset_metric(ELBOW, SHOULDER, normalize=(SHOULDER, HIP)),
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=0.6,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.BENCH_PRESS, PROFILE)
```

Modify `backend/app/scoring/profiles/__init__.py`'s `_ensure_loaded`:

```python
def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    from app.scoring.profiles import bench_press, deadlift, squat  # noqa: F401

    _loaded = True
```

- [ ] **Step 4: Verify the module loads**

```bash
cd backend && python -c "from app.scoring.profiles.bench_press import PROFILE; print(len(PROFILE.fault_rules))"
```

Expected: prints `3` without raising.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/profiles/bench_press.py backend/app/scoring/profiles/__init__.py backend/tests/scoring/test_bench_press.py
git commit -m "feat: add bench press exercise profile"
```

---

## Task 10: Overhead press profile

**Files:**
- Modify: `backend/app/scoring/profiles/__init__.py` (`_ensure_loaded`: add `overhead_press` import)
- Create: `backend/app/scoring/profiles/overhead_press.py`
- Test: `backend/tests/scoring/test_overhead_press.py`

**Interfaces:**
- Same shape as Task 7. Produces `app.scoring.profiles.overhead_press.PROFILE`, registered under `Exercise.OVERHEAD_PRESS`. Fault names: `incomplete_lockout`, `excessive_back_lean`, `uneven_press`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_overhead_press.py`:

```python
import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    active_frame_offsets,
    kp,
    linspace_rep,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)

L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _elbow_trajectory_frames(raw_elbow_angles: list[float]) -> list[dict[int, tuple]]:
    """Overrides driving WRIST position so the RAW angle(shoulder,elbow,
    wrist) follows `raw_elbow_angles` (increasing toward peak for this
    exercise — the profile inverts it internally to get the primary
    signal)."""
    shoulder_l, elbow_l = neutral_xy(L_SHOULDER), neutral_xy(L_ELBOW)
    shoulder_r, elbow_r = neutral_xy(R_SHOULDER), neutral_xy(R_ELBOW)
    overrides_sequence = []
    for angle in raw_elbow_angles:
        wrist_l = point_at_angle(elbow_l, shoulder_l, angle, length=160.0)
        wrist_r = point_at_angle(elbow_r, shoulder_r, angle, length=160.0)
        overrides_sequence.append({L_WRIST: kp(*wrist_l), R_WRIST: kp(*wrist_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(60.0, 175.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=60.0, rest_frames=REST_FRAMES
    )
    return _elbow_trajectory_frames(angles)


def test_clean_overhead_press_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.OVERHEAD_PRESS, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_incomplete_lockout_fires_when_peak_never_reaches_extension() -> None:
    angles = repeat_trajectory(
        linspace_rep(60.0, 140.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=60.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.OVERHEAD_PRESS, frames)
    assert len(reps) >= 1
    assert "incomplete_lockout" in reps[0].faults


def test_excessive_back_lean_fires_when_shoulder_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    hip_x, hip_y = neutral_xy(L_HIP)
    for i in active:
        overrides[i][L_SHOULDER] = kp(hip_x + 150.0, hip_y - 300.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.OVERHEAD_PRESS, frames)
    assert len(reps) >= 1
    assert "excessive_back_lean" in reps[0].faults


def test_uneven_press_fires_when_one_wrist_offset_vertically() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    for i in active:
        x, y = overrides[i][R_WRIST][0], overrides[i][R_WRIST][1]
        overrides[i][R_WRIST] = kp(x, y + 100.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.OVERHEAD_PRESS, frames)
    assert len(reps) >= 1
    assert "uneven_press" in reps[0].faults
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_overhead_press.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.profiles.overhead_press'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/profiles/overhead_press.py`:

```python
"""Overhead press profile (front view). Primary signal: 180 -
angle(shoulder,elbow,wrist), inverted because rest here is the flexed
position (bar racked at shoulder) and peak is full extension overhead."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ELBOW,
    L_HIP,
    L_SHOULDER,
    L_WRIST,
    R_ELBOW,
    R_HIP,
    R_SHOULDER,
    R_WRIST,
    horizontal_offset_metric,
    inverted_angle_metric,
    vertical_symmetry_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
ELBOW = (L_ELBOW, R_ELBOW)
WRIST = (L_WRIST, R_WRIST)
HIP = (L_HIP, R_HIP)

_INVERTED_ELBOW_ANGLE = inverted_angle_metric(SHOULDER, ELBOW, WRIST)

PROFILE = ExerciseProfile(
    primary_signal=_INVERTED_ELBOW_ANGLE,
    fault_rules=[
        threshold_fault(
            name="incomplete_lockout",
            metric=_INVERTED_ELBOW_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=25.0,  # raw elbow angle stayed below ~155 deg
            penalty=0.20,
        ),
        threshold_fault(
            name="excessive_back_lean",
            metric=horizontal_offset_metric(SHOULDER, HIP, normalize=(SHOULDER, HIP)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.3,
            penalty=0.15,
        ),
        threshold_fault(
            name="uneven_press",
            metric=vertical_symmetry_metric(L_WRIST, R_WRIST, normalize=(L_SHOULDER, R_SHOULDER)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.15,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.OVERHEAD_PRESS, PROFILE)
```

Modify `backend/app/scoring/profiles/__init__.py`'s `_ensure_loaded`:

```python
def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    from app.scoring.profiles import bench_press, deadlift, overhead_press, squat  # noqa: F401

    _loaded = True
```

- [ ] **Step 4: Verify the module loads**

```bash
cd backend && python -c "from app.scoring.profiles.overhead_press import PROFILE; print(len(PROFILE.fault_rules))"
```

Expected: prints `3` without raising.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/profiles/overhead_press.py backend/app/scoring/profiles/__init__.py backend/tests/scoring/test_overhead_press.py
git commit -m "feat: add overhead press exercise profile"
```

---

## Task 11: Lunge profile

**Files:**
- Modify: `backend/app/scoring/profiles/__init__.py` (`_ensure_loaded`: add `lunge` import)
- Create: `backend/app/scoring/profiles/lunge.py`
- Test: `backend/tests/scoring/test_lunge.py`

**Interfaces:**
- Same shape as Task 7. Produces `app.scoring.profiles.lunge.PROFILE`, registered under `Exercise.LUNGE`. Fault names: `insufficient_depth`, `knee_over_toe`, `torso_lean`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_lunge.py`:

```python
import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    active_frame_offsets,
    kp,
    linspace_rep,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)

L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_FOOT_INDEX, R_FOOT_INDEX = 31, 32

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _knee_trajectory_frames(knee_angles: list[float]) -> list[dict[int, tuple]]:
    """Both legs driven together (min_of(L, R) == the shared value), same
    construction as squat's."""
    knee_l, ankle_l = neutral_xy(L_KNEE), neutral_xy(L_ANKLE)
    knee_r, ankle_r = neutral_xy(R_KNEE), neutral_xy(R_ANKLE)
    overrides_sequence = []
    for angle in knee_angles:
        hip_l = point_at_angle(knee_l, ankle_l, angle, length=250.0)
        hip_r = point_at_angle(knee_r, ankle_r, angle, length=250.0)
        overrides_sequence.append({L_HIP: kp(*hip_l), R_HIP: kp(*hip_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _knee_trajectory_frames(angles)


def test_clean_lunge_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.LUNGE, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_insufficient_depth_fires_on_shallow_trajectory() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 130.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_knee_trajectory_frames(angles))
    reps = analyze(Exercise.LUNGE, frames)
    assert len(reps) >= 1
    assert "insufficient_depth" in reps[0].faults


def test_knee_over_toe_fires_when_foot_index_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    knee_l_x, knee_l_y = neutral_xy(L_KNEE)
    for i in active:
        overrides[i][L_FOOT_INDEX] = kp(knee_l_x - 200.0, knee_l_y + 20.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.LUNGE, frames)
    assert len(reps) >= 1
    assert "knee_over_toe" in reps[0].faults


def test_torso_lean_fires_when_shoulder_offset_relative_to_hip() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    knee_l, ankle_l = neutral_xy(L_KNEE), neutral_xy(L_ANKLE)
    knee_r, ankle_r = neutral_xy(R_KNEE), neutral_xy(R_ANKLE)
    active = set(active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0])
    overrides_sequence = []
    for local_i, angle in enumerate(angles):
        hip_l = point_at_angle(knee_l, ankle_l, angle, length=250.0)
        hip_r = point_at_angle(knee_r, ankle_r, angle, length=250.0)
        overrides = {L_HIP: kp(*hip_l), R_HIP: kp(*hip_r)}
        if local_i in active:
            overrides[L_SHOULDER] = kp(hip_l[0] + 150.0, hip_l[1] - 300.0)
            overrides[R_SHOULDER] = kp(hip_r[0] + 150.0, hip_r[1] - 300.0)
        overrides_sequence.append(overrides)
    frames = make_frames(overrides_sequence)
    reps = analyze(Exercise.LUNGE, frames)
    assert len(reps) >= 1
    assert "torso_lean" in reps[0].faults
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_lunge.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.profiles.lunge'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/profiles/lunge.py`:

```python
"""Lunge profile (side view). Both legs are modeled with the same
angle_metric; primary signal is the min of the two (whichever leg is
currently more flexed = the working leg). Rest = both legs extended
standing (~170 deg+); peak = working knee bent to its lowest angle."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ANKLE,
    L_FOOT_INDEX,
    L_HIP,
    L_KNEE,
    L_SHOULDER,
    R_ANKLE,
    R_FOOT_INDEX,
    R_HIP,
    R_KNEE,
    R_SHOULDER,
    angle_metric,
    horizontal_offset_metric,
    max_of,
    min_of,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
HIP = (L_HIP, R_HIP)

_LEFT_KNEE_ANGLE = angle_metric(L_HIP, L_KNEE, L_ANKLE)
_RIGHT_KNEE_ANGLE = angle_metric(R_HIP, R_KNEE, R_ANKLE)
_MIN_KNEE_ANGLE = min_of(_LEFT_KNEE_ANGLE, _RIGHT_KNEE_ANGLE)

_LEFT_KNEE_OVER_TOE = horizontal_offset_metric(L_KNEE, L_FOOT_INDEX, normalize=(L_KNEE, L_ANKLE))
_RIGHT_KNEE_OVER_TOE = horizontal_offset_metric(R_KNEE, R_FOOT_INDEX, normalize=(R_KNEE, R_ANKLE))

PROFILE = ExerciseProfile(
    primary_signal=_MIN_KNEE_ANGLE,
    fault_rules=[
        threshold_fault(
            name="insufficient_depth",
            metric=_MIN_KNEE_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=100.0,
            penalty=0.15,
        ),
        threshold_fault(
            name="knee_over_toe",
            metric=max_of(_LEFT_KNEE_OVER_TOE, _RIGHT_KNEE_OVER_TOE),
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=0.4,
            penalty=0.15,
        ),
        threshold_fault(
            name="torso_lean",
            metric=horizontal_offset_metric(SHOULDER, HIP, normalize=(SHOULDER, HIP)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.3,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.LUNGE, PROFILE)
```

Modify `backend/app/scoring/profiles/__init__.py`'s `_ensure_loaded`:

```python
def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    from app.scoring.profiles import (  # noqa: F401
        bench_press,
        deadlift,
        lunge,
        overhead_press,
        squat,
    )

    _loaded = True
```

- [ ] **Step 4: Verify the module loads**

```bash
cd backend && python -c "from app.scoring.profiles.lunge import PROFILE; print(len(PROFILE.fault_rules))"
```

Expected: prints `3` without raising.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/profiles/lunge.py backend/app/scoring/profiles/__init__.py backend/tests/scoring/test_lunge.py
git commit -m "feat: add lunge exercise profile"
```

---

## Task 12: Pushup profile

**Files:**
- Modify: `backend/app/scoring/profiles/__init__.py` (`_ensure_loaded`: add `pushup` import)
- Create: `backend/app/scoring/profiles/pushup.py`
- Test: `backend/tests/scoring/test_pushup.py`

**Interfaces:**
- Same shape as Task 7. Produces `app.scoring.profiles.pushup.PROFILE`, registered under `Exercise.PUSHUP`. Fault names: `insufficient_depth`, `hip_sag`, `flared_elbows`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_pushup.py`:

```python
import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    active_frame_offsets,
    kp,
    linspace_rep,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)

L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_ANKLE, R_ANKLE = 27, 28

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _elbow_trajectory_frames(elbow_angles: list[float]) -> list[dict[int, tuple]]:
    shoulder_l, elbow_l = neutral_xy(L_SHOULDER), neutral_xy(L_ELBOW)
    shoulder_r, elbow_r = neutral_xy(R_SHOULDER), neutral_xy(R_ELBOW)
    overrides_sequence = []
    for angle in elbow_angles:
        wrist_l = point_at_angle(elbow_l, shoulder_l, angle, length=160.0)
        wrist_r = point_at_angle(elbow_r, shoulder_r, angle, length=160.0)
        overrides_sequence.append({L_WRIST: kp(*wrist_l), R_WRIST: kp(*wrist_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _elbow_trajectory_frames(angles)


def test_clean_pushup_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.PUSHUP, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_insufficient_depth_fires_on_shallow_trajectory() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 130.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.PUSHUP, frames)
    assert len(reps) >= 1
    assert "insufficient_depth" in reps[0].faults


def test_hip_sag_fires_when_hip_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    for i in active:
        # Drop the hip well below the natural shoulder-ankle line.
        overrides[i][L_HIP] = kp(360.0, 950.0)
        overrides[i][R_HIP] = kp(410.0, 950.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.PUSHUP, frames)
    assert len(reps) >= 1
    assert "hip_sag" in reps[0].faults


def test_flared_elbows_fires_when_elbow_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    shoulder_x, shoulder_y = neutral_xy(L_SHOULDER)
    for i in active:
        overrides[i][L_ELBOW] = kp(shoulder_x - 250.0, shoulder_y + 100.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.PUSHUP, frames)
    assert len(reps) >= 1
    assert "flared_elbows" in reps[0].faults
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_pushup.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.profiles.pushup'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/profiles/pushup.py`:

```python
"""Pushup profile (front / three-quarter view). Primary signal: elbow
angle (shoulder-elbow-wrist). Rest = arms extended (~170 deg+); peak =
chest near floor."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ANKLE,
    L_ELBOW,
    L_HIP,
    L_SHOULDER,
    L_WRIST,
    R_ANKLE,
    R_ELBOW,
    R_HIP,
    R_SHOULDER,
    R_WRIST,
    angle_metric,
    horizontal_offset_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
ELBOW = (L_ELBOW, R_ELBOW)
WRIST = (L_WRIST, R_WRIST)
HIP = (L_HIP, R_HIP)
ANKLE = (L_ANKLE, R_ANKLE)

_ELBOW_ANGLE = angle_metric(SHOULDER, ELBOW, WRIST)

PROFILE = ExerciseProfile(
    primary_signal=_ELBOW_ANGLE,
    fault_rules=[
        threshold_fault(
            name="insufficient_depth",
            metric=_ELBOW_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=100.0,
            penalty=0.20,
        ),
        threshold_fault(
            name="hip_sag",
            metric=angle_metric(SHOULDER, HIP, ANKLE),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.lt,
            threshold=160.0,
            penalty=0.20,
        ),
        threshold_fault(
            name="flared_elbows",
            metric=horizontal_offset_metric(ELBOW, SHOULDER, normalize=(SHOULDER, HIP)),
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=0.6,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.PUSHUP, PROFILE)
```

Modify `backend/app/scoring/profiles/__init__.py`'s `_ensure_loaded`:

```python
def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    from app.scoring.profiles import (  # noqa: F401
        bench_press,
        deadlift,
        lunge,
        overhead_press,
        pushup,
        squat,
    )

    _loaded = True
```

- [ ] **Step 4: Verify the module loads**

```bash
cd backend && python -c "from app.scoring.profiles.pushup import PROFILE; print(len(PROFILE.fault_rules))"
```

Expected: prints `3` without raising.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/profiles/pushup.py backend/app/scoring/profiles/__init__.py backend/tests/scoring/test_pushup.py
git commit -m "feat: add pushup exercise profile"
```

---

## Task 13: Pullup profile

**Files:**
- Modify: `backend/app/scoring/profiles/__init__.py` (`_ensure_loaded`: add `pullup` import)
- Create: `backend/app/scoring/profiles/pullup.py`
- Test: `backend/tests/scoring/test_pullup.py`

**Interfaces:**
- Same shape as Task 7. Produces `app.scoring.profiles.pullup.PROFILE`, registered under `Exercise.PULLUP`. Fault names: `incomplete_rom_top`, `kipping_swing`, `incomplete_lockout_bottom`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_pullup.py`:

```python
import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    active_frame_offsets,
    kp,
    linspace_rep,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)

L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _elbow_trajectory_frames(elbow_angles: list[float]) -> list[dict[int, tuple]]:
    shoulder_l, elbow_l = neutral_xy(L_SHOULDER), neutral_xy(L_ELBOW)
    shoulder_r, elbow_r = neutral_xy(R_SHOULDER), neutral_xy(R_ELBOW)
    overrides_sequence = []
    for angle in elbow_angles:
        wrist_l = point_at_angle(elbow_l, shoulder_l, angle, length=160.0)
        wrist_r = point_at_angle(elbow_r, shoulder_r, angle, length=160.0)
        overrides_sequence.append({L_WRIST: kp(*wrist_l), R_WRIST: kp(*wrist_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _elbow_trajectory_frames(angles)


def test_clean_pullup_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.PULLUP, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_incomplete_rom_top_fires_on_shallow_trajectory() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 110.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.PULLUP, frames)
    assert len(reps) >= 1
    assert "incomplete_rom_top" in reps[0].faults


def test_kipping_swing_fires_when_hip_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    shoulder_x, shoulder_y = neutral_xy(L_SHOULDER)
    for i in active:
        overrides[i][L_HIP] = kp(shoulder_x + 150.0, shoulder_y + 300.0)
        overrides[i][R_HIP] = kp(shoulder_x + 150.0, shoulder_y + 300.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.PULLUP, frames)
    assert len(reps) >= 1
    assert "kipping_swing" in reps[0].faults


def test_incomplete_lockout_bottom_fires_when_rest_stays_bent() -> None:
    angles = repeat_trajectory(
        linspace_rep(150.0, 70.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=150.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.PULLUP, frames)
    assert len(reps) >= 1
    assert "incomplete_lockout_bottom" in reps[0].faults
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_pullup.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.profiles.pullup'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/profiles/pullup.py`:

```python
"""Pullup profile (front / three-quarter view). Primary signal: elbow
angle (shoulder-elbow-wrist). Rest = dead hang, arms extended (~170
deg+); peak = chin over bar."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ELBOW,
    L_HIP,
    L_SHOULDER,
    L_WRIST,
    R_ELBOW,
    R_HIP,
    R_SHOULDER,
    R_WRIST,
    angle_metric,
    horizontal_offset_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
ELBOW = (L_ELBOW, R_ELBOW)
WRIST = (L_WRIST, R_WRIST)
HIP = (L_HIP, R_HIP)

_ELBOW_ANGLE = angle_metric(SHOULDER, ELBOW, WRIST)

PROFILE = ExerciseProfile(
    primary_signal=_ELBOW_ANGLE,
    fault_rules=[
        threshold_fault(
            name="incomplete_rom_top",
            metric=_ELBOW_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=90.0,
            penalty=0.20,
        ),
        threshold_fault(
            name="kipping_swing",
            metric=horizontal_offset_metric(HIP, SHOULDER, normalize=(SHOULDER, HIP)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.25,
            penalty=0.15,
        ),
        threshold_fault(
            name="incomplete_lockout_bottom",
            metric=_ELBOW_ANGLE,
            phases={Phase.REST},
            comparison=operator.lt,
            threshold=160.0,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.PULLUP, PROFILE)
```

Modify `backend/app/scoring/profiles/__init__.py`'s `_ensure_loaded`:

```python
def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    from app.scoring.profiles import (  # noqa: F401
        bench_press,
        deadlift,
        lunge,
        overhead_press,
        pullup,
        pushup,
        squat,
    )

    _loaded = True
```

- [ ] **Step 4: Verify the module loads**

```bash
cd backend && python -c "from app.scoring.profiles.pullup import PROFILE; print(len(PROFILE.fault_rules))"
```

Expected: prints `3` without raising.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/profiles/pullup.py backend/app/scoring/profiles/__init__.py backend/tests/scoring/test_pullup.py
git commit -m "feat: add pullup exercise profile"
```

---

## Task 14: Row profile

**Files:**
- Modify: `backend/app/scoring/profiles/__init__.py` (`_ensure_loaded`: add `row` import — this task's edit registers all 8, completing the registry)
- Create: `backend/app/scoring/profiles/row.py`
- Test: `backend/tests/scoring/test_row.py`

**Interfaces:**
- Same shape as Task 7. Produces `app.scoring.profiles.row.PROFILE`, registered under `Exercise.ROW`. Fault names: `insufficient_pull`, `back_rounding`, `torso_swing`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_row.py`:

```python
import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    active_frame_offsets,
    kp,
    linspace_rep,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)

L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _elbow_trajectory_frames(elbow_angles: list[float]) -> list[dict[int, tuple]]:
    shoulder_l, elbow_l = neutral_xy(L_SHOULDER), neutral_xy(L_ELBOW)
    shoulder_r, elbow_r = neutral_xy(R_SHOULDER), neutral_xy(R_ELBOW)
    overrides_sequence = []
    for angle in elbow_angles:
        wrist_l = point_at_angle(elbow_l, shoulder_l, angle, length=160.0)
        wrist_r = point_at_angle(elbow_r, shoulder_r, angle, length=160.0)
        overrides_sequence.append({L_WRIST: kp(*wrist_l), R_WRIST: kp(*wrist_r)})
    return overrides_sequence


def _clean_overrides(num_reps: int = 2) -> list[dict[int, tuple]]:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), num_reps, rest_value=170.0, rest_frames=REST_FRAMES
    )
    return _elbow_trajectory_frames(angles)


def test_clean_row_two_reps_no_faults() -> None:
    frames = make_frames(_clean_overrides())
    reps = analyze(Exercise.ROW, frames)
    assert len(reps) == 2
    for rep in reps:
        assert rep.faults == []
        assert rep.form_accuracy == pytest.approx(1.0)


def test_insufficient_pull_fires_on_shallow_trajectory() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 130.0, FRAMES_DOWN, FRAMES_UP), 1, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_elbow_trajectory_frames(angles))
    reps = analyze(Exercise.ROW, frames)
    assert len(reps) >= 1
    assert "insufficient_pull" in reps[0].faults


def test_back_rounding_fires_when_hip_overridden() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    for i in active:
        overrides[i][L_HIP] = kp(360.0, 500.0)  # breaks shoulder-hip-knee collinearity
        overrides[i][R_HIP] = kp(410.0, 500.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.ROW, frames)
    assert len(reps) >= 1
    assert "back_rounding" in reps[0].faults


def test_torso_swing_fires_when_hip_offset_horizontally() -> None:
    overrides = _clean_overrides(num_reps=1)
    active = active_frame_offsets(1, FRAMES_DOWN, FRAMES_UP, REST_FRAMES)[0]
    shoulder_x, shoulder_y = neutral_xy(L_SHOULDER)
    for i in active:
        overrides[i][L_HIP] = kp(shoulder_x + 200.0, shoulder_y + 300.0)
        overrides[i][R_HIP] = kp(shoulder_x + 200.0, shoulder_y + 300.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.ROW, frames)
    assert len(reps) >= 1
    assert "torso_swing" in reps[0].faults
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_row.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.profiles.row'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/profiles/row.py`:

```python
"""Row profile (side view). Primary signal: elbow angle
(shoulder-elbow-wrist). Rest = arms extended (~170 deg+); peak = handle
pulled to torso."""

from __future__ import annotations

import operator

from app.schemas.analysis import Exercise
from app.scoring.landmarks import (
    L_ELBOW,
    L_HIP,
    L_KNEE,
    L_SHOULDER,
    L_WRIST,
    R_ELBOW,
    R_HIP,
    R_KNEE,
    R_SHOULDER,
    R_WRIST,
    angle_metric,
    horizontal_offset_metric,
)
from app.scoring.phases import Phase
from app.scoring.profiles import ExerciseProfile, register_profile
from app.scoring.rules import threshold_fault

SHOULDER = (L_SHOULDER, R_SHOULDER)
ELBOW = (L_ELBOW, R_ELBOW)
WRIST = (L_WRIST, R_WRIST)
HIP = (L_HIP, R_HIP)
KNEE = (L_KNEE, R_KNEE)

_ELBOW_ANGLE = angle_metric(SHOULDER, ELBOW, WRIST)

PROFILE = ExerciseProfile(
    primary_signal=_ELBOW_ANGLE,
    fault_rules=[
        threshold_fault(
            name="insufficient_pull",
            metric=_ELBOW_ANGLE,
            phases={Phase.PEAK},
            comparison=operator.gt,
            threshold=100.0,
            penalty=0.20,
        ),
        threshold_fault(
            name="back_rounding",
            metric=angle_metric(SHOULDER, HIP, KNEE),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.lt,
            threshold=150.0,
            penalty=0.15,
        ),
        threshold_fault(
            name="torso_swing",
            metric=horizontal_offset_metric(SHOULDER, HIP, normalize=(SHOULDER, HIP)),
            phases={Phase.DRIVE, Phase.PEAK},
            comparison=operator.gt,
            threshold=0.25,
            penalty=0.10,
        ),
    ],
)

register_profile(Exercise.ROW, PROFILE)
```

Modify `backend/app/scoring/profiles/__init__.py`'s `_ensure_loaded` (all 8 exercises now imported):

```python
def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    from app.scoring.profiles import (  # noqa: F401
        bench_press,
        deadlift,
        lunge,
        overhead_press,
        pullup,
        pushup,
        row,
        squat,
    )

    _loaded = True
```

- [ ] **Step 4: Verify the module loads**

```bash
cd backend && python -c "from app.scoring.profiles.row import PROFILE; print(len(PROFILE.fault_rules))"
```

Expected: prints `3` without raising.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/profiles/row.py backend/app/scoring/profiles/__init__.py backend/tests/scoring/test_row.py
git commit -m "feat: add row exercise profile"
```

---

## Task 15: Pipeline orchestration

**Files:**
- Create: `backend/app/scoring/pipeline.py`
- Test: `backend/tests/scoring/test_pipeline.py`

**Interfaces:**
- Consumes: `app.schemas.analysis.Exercise, RepScore` (existing); `app.schemas.keypoint.Frame` (existing); `app.scoring.profiles.get_profile` (Task 6); `app.scoring.signal.build_signal_segments` (Task 3); `app.scoring.phases.segment_phases` (Task 4); `app.scoring.rules.evaluate_fault_rules, compute_form_accuracy` (Task 5).
- Produces (used by Task 16's `routes.py`, and already consumed by Tasks 7–14's tests): `analyze(exercise: Exercise, frames: list[Frame]) -> list[RepScore]`.

This task is the one that makes Tasks 7–14's test files pass end-to-end (they import `app.scoring.pipeline.analyze` already). Run the full `backend/tests/scoring/` suite at the end of this task, not just `test_pipeline.py`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scoring/test_pipeline.py`:

```python
import pytest

from app.schemas.analysis import Exercise
from app.scoring.pipeline import analyze
from tests.scoring.fixtures import (
    kp,
    linspace_rep,
    make_frames,
    neutral_xy,
    point_at_angle,
    repeat_trajectory,
)

L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16

FRAMES_DOWN, FRAMES_UP, REST_FRAMES = 20, 20, 5


def _pushup_elbow_overrides(elbow_angles: list[float]) -> list[dict[int, tuple]]:
    shoulder_l, elbow_l = neutral_xy(L_SHOULDER), neutral_xy(L_ELBOW)
    shoulder_r, elbow_r = neutral_xy(R_SHOULDER), neutral_xy(R_ELBOW)
    overrides_sequence = []
    for angle in elbow_angles:
        wrist_l = point_at_angle(elbow_l, shoulder_l, angle, length=160.0)
        wrist_r = point_at_angle(elbow_r, shoulder_r, angle, length=160.0)
        overrides_sequence.append({L_WRIST: kp(*wrist_l), R_WRIST: kp(*wrist_r)})
    return overrides_sequence


def test_too_few_frames_returns_empty() -> None:
    angles = [170.0] * 5  # under MIN_FRAMES
    frames = make_frames(_pushup_elbow_overrides(angles))
    assert analyze(Exercise.PUSHUP, frames) == []


def test_no_completed_rep_returns_empty() -> None:
    angles = [170.0] * 5 + linspace_rep(170.0, 70.0, 20, 20)[:20]  # descends, never returns
    frames = make_frames(_pushup_elbow_overrides(angles))
    assert analyze(Exercise.PUSHUP, frames) == []


def test_clean_two_rep_video_returns_two_reps() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), 2, rest_value=170.0, rest_frames=REST_FRAMES
    )
    frames = make_frames(_pushup_elbow_overrides(angles))
    reps = analyze(Exercise.PUSHUP, frames)
    assert len(reps) == 2
    assert [r.rep_index for r in reps] == [0, 1]
    assert reps[0].end_sec <= reps[1].start_sec


def test_low_visibility_gap_still_detects_reps_around_it() -> None:
    angles = repeat_trajectory(
        linspace_rep(170.0, 70.0, FRAMES_DOWN, FRAMES_UP), 2, rest_value=170.0, rest_frames=REST_FRAMES
    )
    overrides = _pushup_elbow_overrides(angles)
    # Zero out wrist visibility for > 1s (30+ frames at 30fps) between the
    # two reps' rest padding.
    gap_start = REST_FRAMES + FRAMES_DOWN + FRAMES_UP
    for i in range(gap_start, gap_start + 32):
        overrides[i][L_WRIST] = (0.0, 0.0, 0.0, 0.0)
        overrides[i][R_WRIST] = (0.0, 0.0, 0.0, 0.0)
    frames = make_frames(overrides)
    reps = analyze(Exercise.PUSHUP, frames)
    assert len(reps) >= 1  # at least the first rep, unaffected by the later gap


def test_scoring_failure_is_caught_and_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scoring.pipeline as pipeline_module

    def _boom(exercise, frames):  # noqa: ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline_module, "_analyze", _boom)
    angles = repeat_trajectory(linspace_rep(170.0, 70.0, 20, 20), 1, rest_value=170.0, rest_frames=5)
    frames = make_frames(_pushup_elbow_overrides(angles))
    assert analyze(Exercise.PUSHUP, frames) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/scoring/test_pipeline.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.scoring.pipeline'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/scoring/pipeline.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/scoring/ -v`
Expected: PASS for the entire `backend/tests/scoring/` suite — `test_pipeline.py`'s 5 tests, and now also Tasks 7–14's exercise test files (each: 1 clean-rep test + 3 fault tests), plus Tasks 1–6's own tests. If any exercise fault test fails here, it means the hand-derived geometry/threshold in that exercise's task was slightly off — adjust the override magnitude or threshold in that profile/test (not the pipeline) until it passes; this is expected TDD feedback, not a pipeline bug.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scoring/pipeline.py backend/tests/scoring/test_pipeline.py
git commit -m "feat: add rep-scoring pipeline orchestration"
```

---

## Task 16: Wire into the API

**Files:**
- Modify: `backend/app/api/routes.py`
- Modify: `backend/tests/test_main.py`

**Interfaces:**
- Consumes: `app.scoring.pipeline.analyze` (Task 15); `app.schemas.keypoint.Frame` (existing).
- Produces: `/analyze/{exercise}` now returns real `reps` instead of always `[]`. No change to `AnalysisResponse`'s shape.

- [ ] **Step 1: Write the failing test**

Modify `backend/tests/test_main.py`: rename the existing stub test (its "stub" framing is no longer accurate — `reps == []` here is because the video is invalid and produces 0 frames, not because scoring is unimplemented) and add a new wiring test that monkeypatches `cv_engine.KeypointExtractor` with synthetic squat frames so the full route is exercised without needing a real video or the `cv_engine` build to produce meaningful output:

```python
def test_analyze_invalid_video_returns_empty_reps() -> None:
    video_bytes = b"not a real video"
    response = client.post(
        "/analyze/squat",
        files={"video": ("clip.mp4", video_bytes, "video/mp4")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exercise"] == "squat"
    assert body["reps"] == []
    assert body["frame_count"] == 0
    assert body["frames"] == []


def test_analyze_returns_real_reps_for_synthetic_squat_video(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.scoring.fixtures import kp, linspace_rep, make_frames, neutral_xy, point_at_angle, repeat_trajectory

    L_HIP, R_HIP = 23, 24
    L_KNEE, R_KNEE = 25, 26
    L_ANKLE, R_ANKLE = 27, 28

    angles = repeat_trajectory(linspace_rep(170.0, 70.0, 20, 20), 2, rest_value=170.0, rest_frames=5)
    knee_l, ankle_l = neutral_xy(L_KNEE), neutral_xy(L_ANKLE)
    knee_r, ankle_r = neutral_xy(R_KNEE), neutral_xy(R_ANKLE)
    overrides_sequence = []
    for angle in angles:
        hip_l = point_at_angle(knee_l, ankle_l, angle, length=250.0)
        hip_r = point_at_angle(knee_r, ankle_r, angle, length=250.0)
        overrides_sequence.append({L_HIP: kp(*hip_l), R_HIP: kp(*hip_r)})
    synthetic_frames = make_frames(overrides_sequence)

    class FakeExtractor:
        def extract(self, path: str) -> list:  # noqa: ARG002
            return synthetic_frames

    monkeypatch.setattr("app.api.routes.cv_engine.KeypointExtractor", FakeExtractor)

    response = client.post(
        "/analyze/squat",
        files={"video": ("clip.mp4", b"x", "video/mp4")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["frame_count"] == len(synthetic_frames)
    assert len(body["reps"]) == 2
    for rep in body["reps"]:
        assert rep["faults"] == []
        assert rep["form_accuracy"] == pytest.approx(1.0)
```

(Remove the old `test_analyze_stub_returns_empty_reps` — replaced by `test_analyze_invalid_video_returns_empty_reps` above, same assertions.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_main.py -v -k "invalid_video or synthetic_squat"`
Expected: `test_analyze_invalid_video_returns_empty_reps` PASSes already (behavior unchanged); `test_analyze_returns_real_reps_for_synthetic_squat_video` FAILs — `body["reps"]` is `[]`, not length 2 (routes.py not wired yet).

- [ ] **Step 3: Write the implementation**

Modify `backend/app/api/routes.py`:

```python
import tempfile
from pathlib import Path

import cv_engine
from fastapi import APIRouter, UploadFile

from app.schemas.analysis import AnalysisResponse, Exercise
from app.schemas.keypoint import Frame as FrameSchema
from app.scoring import pipeline as scoring_pipeline

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyze/{exercise}", response_model=AnalysisResponse)
async def analyze(exercise: Exercise, video: UploadFile) -> AnalysisResponse:
    suffix = Path(video.filename or "video.mp4").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(await video.read())
        tmp.flush()
        frames = cv_engine.KeypointExtractor().extract(tmp.name)

    frame_models = [FrameSchema.model_validate(f) for f in frames]
    reps = scoring_pipeline.analyze(exercise, frame_models)

    return AnalysisResponse(
        exercise=exercise, frame_count=len(frame_models), reps=reps, frames=frame_models
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_main.py -v`
Expected: PASS (all tests in the file, including the two from Step 1).

Run the full backend suite: `pytest backend/tests -v`
Expected: PASS (every test across `backend/tests/scoring/` and `backend/tests/test_main.py`).

Run ruff: `cd backend && ruff check .`
Expected: no errors (fix any line-length/import-order issues it flags before committing).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes.py backend/tests/test_main.py
git commit -m "feat: wire rep-segmentation and form-accuracy scoring into /analyze"
```

---

## Post-plan follow-up (not part of this plan's tasks)

Once this plan is merged, `reps` is real for all 8 exercises. The frontend cleanup described in the spec's "Summary of contract impact" — deleting `frontend/src/mockReps.ts` / `mockReps.test.ts` and switching `ResultsView.tsx` to `response.reps` — is a separate, small follow-up change, not included here since it touches the frontend, not the backend scoring subsystem this plan covers.
