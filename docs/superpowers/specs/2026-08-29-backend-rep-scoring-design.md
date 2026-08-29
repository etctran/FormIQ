# Backend rep-segmentation + per-exercise form-accuracy scoring

Status: Draft for review
Date: 2026-08-29

## Goal

`/analyze/{exercise}` currently returns real `frame_count` but `reps` is
always `[]` (see [backend/app/api/routes.py](../../../backend/app/api/routes.py)).
This spec covers turning the per-frame keypoint stream cv-engine already
produces into real `RepScore`s: detecting rep boundaries and scoring
per-rep form accuracy with named faults, for all 8 supported exercises
(`squat`, `deadlift`, `bench_press`, `overhead_press`, `lunge`, `pushup`,
`pullup`, `row`).

The target output shape is **already fixed** and does not change:

```python
# backend/app/schemas/analysis.py — existing, unmodified
class RepScore(BaseModel):
    rep_index: int
    start_sec: float
    end_sec: float
    form_accuracy: float
    faults: list[str] = []
```

Once this ships, `frontend/src/mockReps.ts` and `mockReps.test.ts` are
deleted and `ResultsView.tsx` switches its one call site from
`getReps(response, duration)` to `response.reps` directly — no other
frontend change, since every other component is already written against
this exact `RepScore` shape.

## Non-goals

- Camera-angle detection or support for arbitrary filming angles (see
  Camera angle below — one fixed angle per exercise, by design).
- Calibrating fault thresholds/penalties against real labeled data. All
  numeric thresholds below are defaults sourced from general
  strength-coaching heuristics, explicitly tunable, not validated against
  ground truth.
- AWS ECS deployment (separate sub-project, tracked in `CLAUDE.md`).

## Architecture

New package `backend/app/scoring/`:

```
backend/app/scoring/
  landmarks.py    # named MediaPipe landmark indices + geometry helpers
                  #   (angle_between, midpoint, normalized_distance)
  signal.py       # raw-metric -> per-video min-max normalize -> smooth
  phases.py       # generic phase state machine (REST/DRIVE/PEAK/RECOVER)
                  #   with hysteresis
  profiles/
    __init__.py   # ExerciseProfile registry, keyed by Exercise enum
    squat.py
    deadlift.py
    bench_press.py
    overhead_press.py
    lunge.py
    pushup.py
    pullup.py
    row.py
  pipeline.py     # analyze(exercise, frames) -> list[RepScore]
```

`backend/app/api/routes.py` changes by one line:

```python
reps = scoring.pipeline.analyze(exercise, frames)
return AnalysisResponse(exercise=exercise, frame_count=len(frames), reps=reps, frames=frames)
```

Pipeline failures are caught in `pipeline.analyze` and logged; the
function returns `[]` rather than raising, so a scoring bug degrades to
"no reps detected" (already a normal outcome) instead of a 500.

New dependency: `numpy` (signal smoothing/vector math), added to
`backend/pyproject.toml`. No `scipy` — not needed.

### Coordinate system note

Keypoints are in **raw video pixel coordinates**, not normalized 0–1
(confirmed in `cv-engine/src/landmark_regressor.cpp`'s
`kp.x = crop_rect.x + lm[0] * sx` and mirrored by
`frontend/src/components/SkeletonOverlay.tsx`'s `videoWidth`/`videoHeight`
scaling). Consequently:

- **Joint angles** (computed from `(x, y)` vectors) are scale-invariant
  by construction — no normalization needed, and used as the primary
  signal wherever the exercise's ROM is well captured by one joint angle.
- **Distance-based metrics** (e.g. bar drift, hip sag) are only ever
  used relative to a per-frame body-length reference (e.g. torso length
  = `|shoulder_mid − hip_mid|`), never as raw pixel distances, since
  those vary with video resolution and camera distance.

### Camera angle

Each exercise assumes one fixed, conventional filming angle (matches how
these are actually filmed in practice); no angle detection or
multi-angle support:

| Exercise | Angle |
|---|---|
| squat, deadlift, lunge, row | side view |
| bench_press, overhead_press | front view |
| pushup, pullup | front / three-quarter view |

Video filmed from the wrong angle degrades results silently rather than
being detected/rejected — out of scope here.

## Rep segmentation

### Primary signal

Per exercise, one scalar per frame ("primary signal") oriented so that
**1.0 = rest posture** (the natural pause position between reps) and
**0.0 = peak-effort posture** (point of maximum exertion/end-range),
regardless of which spatial direction that is (e.g. a pull-up's rest is
a dead hang at the *bottom* of the movement in space, but is still
signal = 1.0). See the per-exercise table below for each exercise's
specific metric and, where the natural joint-angle direction runs the
other way (overhead press), the explicit inversion used.

Pipeline steps (in `signal.py`):

1. Compute the raw per-frame metric (a joint angle in degrees, or a
   body-length-normalized distance).
2. Skip frames where a required landmark's `visibility` is below a
   threshold (default `0.5`); linearly interpolate the raw series across
   the gap. If a contiguous unresolvable stretch exceeds ~1s, exclude
   that stretch from segmentation entirely rather than interpolating
   over it.
3. Rescale to `[0, 1]` using the video's own 5th/95th percentile of the
   raw series (self-calibrating per video — no cross-user calibration
   data required), oriented so 1.0 = rest as defined per exercise.
4. Smooth with a moving average (default window: ~0.3s of frames) to
   suppress per-frame jitter before phase detection.

### Phase state machine (`phases.py`)

Four phases, with hysteresis bands to avoid flicker near a threshold:

- `REST`: signal > 0.85 to enter, stays until < 0.75
- `DRIVE`: falling, between exit-`REST` and enter-`PEAK`
- `PEAK`: signal < 0.15 to enter, stays until > 0.25
- `RECOVER`: rising, between exit-`PEAK` and enter-`REST`

One rep = one full `REST → DRIVE → PEAK → RECOVER → REST` cycle.
`rep_index` increments per completed cycle; `start_sec`/`end_sec` are the
timestamps of the two `REST` crossings bounding it.

### Edge cases

- **Leading/trailing partial rep** (video starts mid-rep or ends before
  returning to `REST`): dropped, not scored. `RepScore` has no field to
  mark "incomplete," so a rep only counts once its cycle fully closes.
- **No completed rep** (never returns to `REST`, or video too short):
  `reps: []` — not an error, same as today's default.
- **Degenerate video** (`frame_count` too small to smooth meaningfully,
  default threshold: fewer than 10 usable frames after visibility
  filtering): skip the pipeline, return `reps: []` immediately.
- **Low-visibility landmarks**: handled in signal step 2 above.

## Fault detection & scoring

`FaultRule` (declarative, one set per `ExerciseProfile`):

```python
@dataclass
class FaultRule:
    name: str                                    # e.g. "insufficient_depth"
    phases: set[Phase]                            # when to check, e.g. {Phase.PEAK}
    metric: Callable[[Frame], float | None]       # None if unresolvable this frame
    check: Callable[[float], bool]                 # True = this frame violates the rule
    min_violating_frames_ratio: float = 0.5        # debounce: fraction of in-phase
                                                    # frames that must violate before
                                                    # the fault fires for the whole rep
    penalty: float                                 # form_accuracy deduction if fired
```

Per rep, per `FaultRule`: gather the rep's frames whose phase is in
`rule.phases`, evaluate `check(metric(frame))` on each with a resolvable
metric, and fire (append `rule.name` to `faults`) if the violating
fraction ≥ `min_violating_frames_ratio`.

```
form_accuracy = clamp(1.0 - sum(penalty for each fired fault), 0.0, 1.0)
```

## Per-exercise profiles

Landmark shorthand: `shoulder`/`hip`/`knee`/`elbow`/`wrist`/`ankle` mean
the midpoint of the left/right pair (MediaPipe indices 11/12, 23/24,
25/26, 13/14, 15/16, 27/28) unless a rule explicitly needs per-side
values. `angle(A, B, C)` = angle at vertex B between rays `BA`/`BC`, from
`(x, y)` only. All penalties/thresholds below are proposed defaults,
tunable later — not derived from a labeled dataset (see Non-goals).

### squat (side view)
- **Signal**: `angle(hip, knee, ankle)` (knee angle). Rest ≈ standing
  extension (~170°+); peak = deepest point (lowest angle).
- **Faults**:
  | name | phases | check | penalty |
  |---|---|---|---|
  | `insufficient_depth` | PEAK | knee angle (the primary signal itself) fails to drop below a depth threshold | 0.20 |
  | `forward_knee_travel` | DRIVE, PEAK | knee's horizontal position extends past the foot-index landmark beyond threshold (normalized by shin length) | 0.15 |
  | `back_rounding` | DRIVE, PEAK | `angle(shoulder, hip, knee)` drops below threshold (torso collapsing forward) | 0.15 |
  | `heel_rise` | PEAK | heel landmark (29/30) lifts above ankle height beyond threshold (normalized by foot length) | 0.10 |

  > `forward_knee_travel` replaces an earlier `knee_valgus` fault from
  > brainstorming: knee cave-in is a frontal-plane deviation, essentially
  > unobservable from the side-view angle this exercise assumes (the far
  > knee is partially occluded). Forward knee travel is visible in the
  > sagittal plane, so it fits the fixed camera angle.

### deadlift (side view)
- **Signal**: `angle(shoulder, hip, knee)` (hip hinge angle). Rest ≈
  standing tall (~170°+); peak = bar at floor (lowest angle).
- **Faults**:
  | name | phases | check | penalty |
  |---|---|---|---|
  | `back_rounding` | DRIVE, PEAK | spinal curvature proxy (deviation of the shoulder–hip–knee line from straight) exceeds threshold | 0.20 |
  | `bar_path_drift` | DRIVE, RECOVER | wrist midpoint's horizontal drift from a vertical line through the hip exceeds threshold (normalized by torso length) | 0.15 |
  | `hyperextension_lockout` | REST, RECOVER (near top) | wrist midpoint's horizontal drift from the hip exceeds threshold (leaning back past neutral at lockout; uses wrist rather than shoulder as the lean proxy, since shoulder position is already the signal driving segmentation here) | 0.10 |

### bench_press (front view)
- **Signal**: `angle(shoulder, elbow, wrist)` (elbow angle). Rest = arms
  extended at top (~170°+); peak = bar at chest (lowest angle).
- **Faults**:
  | name | phases | check | penalty |
  |---|---|---|---|
  | `uneven_bar_path` | DRIVE, RECOVER | left vs. right wrist height difference exceeds threshold (normalized by shoulder width) | 0.15 |
  | `partial_lockout` | RECOVER (near top), REST | elbow angle fails to reach near-full-extension threshold | 0.15 |
  | `flared_elbows` | PEAK | elbow's horizontal deviation from the shoulder line exceeds threshold | 0.10 |

### overhead_press (front view)
- **Signal**: `180° − angle(shoulder, elbow, wrist)`. **Inverted** relative
  to bench/squat: rest here is bar racked at shoulders (elbow bent, so
  raw angle is low but signal is high), peak is arms locked out overhead
  (elbow angle maximal, signal low).
- **Faults**:
  | name | phases | check | penalty |
  |---|---|---|---|
  | `incomplete_lockout` | PEAK | elbow angle fails to reach near-full-extension threshold overhead | 0.20 |
  | `excessive_back_lean` | DRIVE, PEAK | shoulder–hip line deviates from vertical beyond threshold | 0.15 |
  | `uneven_press` | DRIVE, PEAK | left vs. right wrist height difference exceeds threshold (normalized by shoulder width) | 0.10 |

### lunge (side view)
- **Working leg** = whichever side (L/R) has the smaller knee angle at
  any given frame (the currently-loaded leg).
- **Signal**: `min(angle(hip_L, knee_L, ankle_L), angle(hip_R, knee_R, ankle_R))`.
  Rest ≈ both legs extended standing (~170°+); peak = working knee bent
  to its lowest angle.
- **Faults**:
  | name | phases | check | penalty |
  |---|---|---|---|
  | `knee_over_toe` | PEAK | working knee's horizontal position extends past its foot-index landmark beyond threshold (normalized by shin length) | 0.15 |
  | `insufficient_depth` | PEAK | working knee angle doesn't drop below ~90° threshold | 0.15 |
  | `torso_lean` | DRIVE, PEAK | shoulder–hip vertical alignment deviates from vertical beyond threshold | 0.10 |

### pushup (front / three-quarter view)
- **Signal**: `angle(shoulder, elbow, wrist)`. Rest = arms extended at
  top (~170°+); peak = chest near floor (lowest angle).
- **Faults**:
  | name | phases | check | penalty |
  |---|---|---|---|
  | `insufficient_depth` | PEAK | elbow angle doesn't drop below ~90° threshold | 0.20 |
  | `hip_sag` | DRIVE, PEAK | hip deviates below the shoulder–ankle line beyond threshold (normalized by torso length) | 0.20 |
  | `flared_elbows` | PEAK | elbow angle relative to torso (flare) exceeds threshold | 0.10 |

### pullup (front / three-quarter view)
- **Signal**: `angle(shoulder, elbow, wrist)`. Rest = dead hang, arms
  extended (~170°+); peak = chin over bar (lowest angle).
- **Faults**:
  | name | phases | check | penalty |
  |---|---|---|---|
  | `incomplete_rom_top` | PEAK | elbow angle (the primary signal itself) fails to drop below threshold | 0.20 |
  | `kipping_swing` | DRIVE, PEAK | hip's horizontal displacement relative to shoulder exceeds threshold (normalized by torso length) | 0.15 |
  | `incomplete_lockout_bottom` | REST (entry) | elbow angle fails to reach near-full-extension at the bottom | 0.10 |

### row (side view)
- **Signal**: `angle(shoulder, elbow, wrist)`. Rest = arms extended
  (~170°+); peak = handle pulled to torso (lowest angle).
- **Faults**:
  | name | phases | check | penalty |
  |---|---|---|---|
  | `insufficient_pull` | PEAK | elbow angle (the primary signal itself) fails to drop below threshold | 0.20 |
  | `back_rounding` | DRIVE, PEAK | `angle(shoulder, hip, knee)` drops below threshold | 0.15 |
  | `torso_swing` | DRIVE, PEAK | shoulder's horizontal displacement relative to hip exceeds threshold (using momentum to pull) | 0.10 |

Concrete numeric threshold values (degrees, normalized-distance cutoffs)
are not enumerated per fault above — each row's qualitative description
(e.g. "drops below threshold," "exceeds threshold") is the requirement;
the implementation plan picks a specific starting constant consistent
with that description and stores it alongside the `FaultRule`, not
buried in a magic number. Like the penalties, these are defaults to
tune later, not derived from labeled data (see Non-goals).

## Testing

`backend/tests/scoring/fixtures.py`: synthetic `Frame` builders per
exercise, generating multi-rep sequences via interpolated joint-angle
trajectories between each exercise's rest/peak angles — a "clean"
variant per exercise, plus one perturbed variant per fault (violating
just that fault's metric/phase). No video or cv-engine dependency; pure
Python, fast, deterministic, matches the repo's existing TDD convention.

Per-exercise test files (`backend/tests/scoring/test_squat.py`, etc.)
assert:
- Correct rep count and boundaries (within a small timestamp tolerance)
  on the clean fixture.
- Each fault fires on its perturbed fixture and does **not** fire on the
  clean fixture.
- `form_accuracy` matches the expected penalty-sum calculation for a
  fixture with a known combination of faults.

Shared tests (`backend/tests/scoring/test_pipeline.py`) cover the edge
cases from Rep segmentation § Edge cases: degenerate/too-short video,
no completed rep, and a low-visibility gap — all asserted to return
`[]` without raising, across a couple of representative exercises (not
all 8, since this logic is exercise-agnostic).

## Summary of contract impact

No changes to `RepScore`, `AnalysisResponse`, or the `/analyze/{exercise}`
route signature. One line in `routes.py` changes (`reps=[]` →
`reps=scoring.pipeline.analyze(...)`). `numpy` added as a new backend
dependency. Frontend follow-up (not part of this spec's implementation,
but the reason it's worth doing): delete `mockReps.ts`/`mockReps.test.ts`,
switch `ResultsView.tsx` to `response.reps`.
