# Pose Skeleton Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the `/analyze/{exercise}` API to include real per-frame
keypoints, and render them as a skeleton (dots + connecting lines) drawn
on the results video, synced to playback via linear interpolation between
sampled frames.

**Architecture:** `AnalysisResponse` gains a `frames` field carrying the
already-extracted (previously discarded) `cv-engine` output. A new pure
function `interpolateFrame` maps video `currentTime` to an interpolated
33-point pose (or `null` on any gap); a new `SkeletonOverlay` component
owns a `<canvas>` absolutely positioned over the results `<video>` and
redraws every animation frame using that function.

**Tech Stack:** FastAPI/Pydantic (backend), React 19 + TypeScript + native
Canvas 2D API (frontend) — no new dependencies on either side.

**Spec:** `docs/superpowers/specs/2026-08-23-skeleton-overlay-design.md`

## Global Constraints

- No new dependencies, either side.
- `Keypoint`/`Frame` already exist in `backend/app/schemas/keypoint.py`
  matching `cv-engine`'s C++ structs exactly — do not redefine or alter
  them.
- Coordinate space: `Keypoint.x`/`y` are original-video PIXEL coordinates
  (not normalized 0-1) — the overlay must scale by
  `displaySize / video.videoWidth|videoHeight`.
- Never fabricate a pose: `interpolateFrame` returns `null` (draw nothing)
  before the first frame, at/after the last frame, or when either
  bracketing frame has empty `landmarks` — never holds a stale pose or
  guesses.
- Out of scope: rep-segmentation, `mockReps.ts`, any change to
  `cv-engine`'s C++ extraction itself, 3D/depth rendering, confidence-based
  visual treatment.

---

## Task 1: Backend — include real keypoints in the API response

**Files:**
- Modify: `backend/app/schemas/analysis.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/tests/test_main.py`

**Interfaces:**
- Consumes: `Frame`/`Keypoint` already defined in
  `backend/app/schemas/keypoint.py` (`Frame{timestamp_sec: float,
  landmarks: list[Keypoint]}`, `Keypoint{x: float, y: float, z: float,
  visibility: float}`) — unchanged, just imported.
- Produces: `AnalysisResponse.frames: list[Frame]`, consumed by the
  frontend from Task 2 onward (`frames` becomes a real key in the JSON
  response body).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_main.py`, extending the existing
`test_analyze_stub_returns_empty_reps` test (don't rename it — the
scaffold-stub video bytes still produce zero real frames, this just also
proves `frames` round-trips through the schema):

```python
def test_analyze_stub_returns_empty_reps() -> None:
    video_bytes = b"not a real video, scaffolding stub"
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_main.py::test_analyze_stub_returns_empty_reps -v`
Expected: FAIL — `KeyError: 'frames'` (the field doesn't exist in the
response yet).

- [ ] **Step 3: Add `frames` to `AnalysisResponse`**

```python
# backend/app/schemas/analysis.py
from enum import Enum

from pydantic import BaseModel

from app.schemas.keypoint import Frame


class Exercise(str, Enum):
    SQUAT = "squat"
    DEADLIFT = "deadlift"
    BENCH_PRESS = "bench_press"
    OVERHEAD_PRESS = "overhead_press"
    LUNGE = "lunge"
    PUSHUP = "pushup"
    PULLUP = "pullup"
    ROW = "row"


class RepScore(BaseModel):
    rep_index: int
    start_sec: float
    end_sec: float
    form_accuracy: float
    faults: list[str] = []


class AnalysisResponse(BaseModel):
    exercise: Exercise
    frame_count: int
    reps: list[RepScore]
    frames: list[Frame]
```

- [ ] **Step 4: Pass the real frames through in `routes.py`**

```python
# backend/app/api/routes.py
import tempfile
from pathlib import Path

import cv_engine
from fastapi import APIRouter, UploadFile

from app.schemas.analysis import AnalysisResponse, Exercise

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

    return AnalysisResponse(
        exercise=exercise, frame_count=len(frames), reps=[], frames=frames
    )
```

(`cv_engine.Frame`/`cv_engine.Keypoint` pybind11 objects convert into the
Pydantic `Frame`/`Keypoint` models automatically — Pydantic reads
`.timestamp_sec`/`.landmarks` and `.x`/`.y`/`.z`/`.visibility` off any
object with matching attribute names, no manual conversion needed. This
already works today for other pybind11-attribute-style objects in this
codebase's test patterns; if Pydantic raises a validation error here
instead, convert explicitly per-frame
(`Frame(timestamp_sec=f.timestamp_sec, landmarks=[Keypoint(x=k.x, y=k.y,
z=k.z, visibility=k.visibility) for k in f.landmarks])`) as a fallback —
try the direct pass-through first, it's the simpler correct path.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_main.py -v`
Expected: PASS, all 3 tests (including the two untouched ones — confirm
they still pass, nothing else broke).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/analysis.py backend/app/api/routes.py backend/tests/test_main.py
git commit -m "feat: include per-frame keypoints in the analyze response"
```

---

## Task 2: Frontend types for `Keypoint`/`Frame`

**Files:**
- Modify: `frontend/src/types.ts`

**Interfaces:**
- Produces: `Keypoint{x: number, y: number, z: number, visibility:
  number}`, `Frame{timestamp_sec: number, landmarks: Keypoint[]}`,
  `AnalysisResponse` gains `frames: Frame[]`. Consumed by Task 4
  (`interpolateFrame`) and Task 5 (`SkeletonOverlay`).

No test — this is a pure type addition, verified by the type-checker in
Step 2.

- [ ] **Step 1: Add the types**

```ts
// frontend/src/types.ts
export const EXERCISES = [
  'squat',
  'deadlift',
  'bench_press',
  'overhead_press',
  'lunge',
  'pushup',
  'pullup',
  'row',
] as const

export type Exercise = (typeof EXERCISES)[number]

export interface RepScore {
  rep_index: number
  start_sec: number
  end_sec: number
  form_accuracy: number
  faults: string[]
}

export interface Keypoint {
  x: number
  y: number
  z: number
  visibility: number
}

export interface Frame {
  timestamp_sec: number
  landmarks: Keypoint[]
}

export interface AnalysisResponse {
  exercise: Exercise
  frame_count: number
  reps: RepScore[]
  frames: Frame[]
}
```

- [ ] **Step 2: Run the type checker**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors (nothing consumes `frames` yet, so this only proves
the type addition itself is syntactically valid).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat: add Keypoint/Frame types, extend AnalysisResponse"
```

---

## Task 3: Pose connection topology

**Files:**
- Create: `frontend/src/poseConnections.ts`

**Interfaces:**
- Produces: `POSE_CONNECTIONS: readonly [number, number][]` — pairs of
  landmark indices to draw as connecting lines. Consumed by Task 5
  (`SkeletonOverlay`).

Static data, no test needed.

- [ ] **Step 1: Write the file**

```ts
// frontend/src/poseConnections.ts
// Standard MediaPipe BlazePose 33-landmark topology (indices: 11/12
// shoulders, 13/14 elbows, 15/16 wrists, 23/24 hips, 25/26 knees, 27/28
// ankles), restricted to the core body skeleton -- auxiliary face
// (0-10), hand (17-22), and foot-detail (29-32) landmarks are extracted
// by cv-engine but not connected here, to keep the drawn skeleton clean
// (see spec Key Decision 3 / Non-goals).
export const POSE_CONNECTIONS: readonly [number, number][] = [
  [11, 12], // shoulders
  [11, 13],
  [13, 15], // left arm
  [12, 14],
  [14, 16], // right arm
  [11, 23],
  [12, 24], // torso sides
  [23, 24], // hips
  [23, 25],
  [25, 27], // left leg
  [24, 26],
  [26, 28], // right leg
]
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/poseConnections.ts
git commit -m "feat: add static pose connection topology"
```

---

## Task 4: `interpolateFrame` — the core interpolation logic

**Files:**
- Create: `frontend/src/interpolateFrame.ts`
- Test: `frontend/src/interpolateFrame.test.ts`

**Interfaces:**
- Consumes: `Frame`, `Keypoint` from `frontend/src/types.ts` (Task 2).
- Produces: `interpolateFrame(frames: Frame[], currentTime: number):
  Keypoint[] | null`. Consumed by Task 5 (`SkeletonOverlay`).

This is the highest-value task to get exactly right via TDD — everything
else in this plan is straightforward wiring around this function.

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/src/interpolateFrame.test.ts
import { describe, expect, it } from 'vitest'
import { interpolateFrame } from './interpolateFrame'
import type { Frame } from './types'

const frames: Frame[] = [
  {
    timestamp_sec: 0,
    landmarks: [
      { x: 0, y: 0, z: 0, visibility: 1 },
      { x: 10, y: 10, z: 0, visibility: 1 },
    ],
  },
  {
    timestamp_sec: 1,
    landmarks: [
      { x: 10, y: 20, z: 0, visibility: 1 },
      { x: 20, y: 30, z: 0, visibility: 1 },
    ],
  },
  { timestamp_sec: 2, landmarks: [] }, // no detection this sampled frame
  {
    timestamp_sec: 3,
    landmarks: [
      { x: 100, y: 100, z: 0, visibility: 1 },
      { x: 110, y: 110, z: 0, visibility: 1 },
    ],
  },
]

describe('interpolateFrame', () => {
  it('returns exact landmarks at a sample timestamp', () => {
    expect(interpolateFrame(frames, 0)).toEqual(frames[0].landmarks)
  })

  it('linearly interpolates at the midpoint between two frames', () => {
    const result = interpolateFrame(frames, 0.5)
    expect(result).not.toBeNull()
    expect(result![0].x).toBeCloseTo(5)
    expect(result![0].y).toBeCloseTo(10)
    expect(result![1].x).toBeCloseTo(15)
    expect(result![1].y).toBeCloseTo(20)
  })

  it('returns null before the first frame', () => {
    expect(interpolateFrame(frames, -1)).toBeNull()
  })

  it('returns null at or after the last frame', () => {
    expect(interpolateFrame(frames, 3)).toBeNull()
    expect(interpolateFrame(frames, 10)).toBeNull()
  })

  it('returns null when a bracketing frame has no detection', () => {
    // between frames[1] (t=1, has landmarks) and frames[2] (t=2, empty)
    expect(interpolateFrame(frames, 1.5)).toBeNull()
  })

  it('returns null for an empty frames array', () => {
    expect(interpolateFrame([], 1)).toBeNull()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/interpolateFrame.test.ts`
Expected: FAIL — `interpolateFrame.ts` doesn't exist yet.

- [ ] **Step 3: Write `interpolateFrame.ts`**

```ts
// frontend/src/interpolateFrame.ts
import type { Frame, Keypoint } from './types'

// Binary-searches `frames` (assumed sorted ascending by timestamp_sec,
// which extraction already guarantees) for the two frames bracketing
// `currentTime` and linearly interpolates each keypoint's x/y between
// them. Returns null when there's nothing honest to draw: before the
// first frame, at/after the last frame, or when either bracketing frame
// has no detection (empty landmarks) -- never fabricates a pose the
// model didn't actually produce (spec Key Decision 5).
export function interpolateFrame(frames: Frame[], currentTime: number): Keypoint[] | null {
  if (frames.length === 0) return null
  if (currentTime < frames[0].timestamp_sec) return null
  if (currentTime >= frames[frames.length - 1].timestamp_sec) return null

  // Binary search for the last frame index with timestamp_sec <=
  // currentTime. The two guard checks above ensure such an index exists
  // and is not the final frame, so `lo + 1` below is always in bounds.
  let lo = 0
  let hi = frames.length - 2
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2)
    if (frames[mid].timestamp_sec <= currentTime) lo = mid
    else hi = mid - 1
  }
  const a = frames[lo]
  const b = frames[lo + 1]

  if (a.landmarks.length === 0 || b.landmarks.length === 0) return null

  const span = b.timestamp_sec - a.timestamp_sec
  const t = span > 0 ? (currentTime - a.timestamp_sec) / span : 0

  return a.landmarks.map((kpA, i) => {
    const kpB = b.landmarks[i]
    return {
      x: kpA.x + (kpB.x - kpA.x) * t,
      y: kpA.y + (kpB.y - kpA.y) * t,
      z: kpA.z,
      visibility: kpA.visibility,
    }
  })
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/interpolateFrame.test.ts`
Expected: PASS, 6/6 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/interpolateFrame.ts frontend/src/interpolateFrame.test.ts
git commit -m "feat: add interpolateFrame for skeleton keypoint tweening"
```

---

## Task 5: `SkeletonOverlay` component

**Files:**
- Create: `frontend/src/components/SkeletonOverlay.tsx`
- Create: `frontend/src/components/SkeletonOverlay.css`

**Interfaces:**
- Consumes: `Frame` from `frontend/src/types.ts` (Task 2),
  `interpolateFrame` (Task 4), `POSE_CONNECTIONS` (Task 3).
- Produces: `SkeletonOverlay({frames: Frame[], videoRef:
  RefObject<HTMLVideoElement | null>})` — a React component. Consumed by
  Task 6 (`ResultsView`).

No dedicated unit test (canvas-drawing side effects are awkward to test
meaningfully — this matches the plan's stated testing approach; the real
logic lives in `interpolateFrame`, already covered). Verification is the
type-checker plus visual confirmation once wired into `ResultsView` in
Task 6.

- [ ] **Step 1: Write `SkeletonOverlay.tsx`**

```tsx
// frontend/src/components/SkeletonOverlay.tsx
import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import type { Frame } from '../types'
import { interpolateFrame } from '../interpolateFrame'
import { POSE_CONNECTIONS } from '../poseConnections'
import './SkeletonOverlay.css'

interface SkeletonOverlayProps {
  frames: Frame[]
  videoRef: RefObject<HTMLVideoElement | null>
}

export function SkeletonOverlay({ frames, videoRef }: SkeletonOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const video = videoRef.current
    if (!canvas || !video) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let rafId: number

    const draw = () => {
      rafId = requestAnimationFrame(draw)

      if (video.videoWidth === 0 || video.videoHeight === 0) return

      // Match canvas resolution to its displayed size every tick -- cheap
      // for a 33-point skeleton, and avoids a separate ResizeObserver.
      const displayWidth = video.clientWidth
      const displayHeight = video.clientHeight
      if (canvas.width !== displayWidth || canvas.height !== displayHeight) {
        canvas.width = displayWidth
        canvas.height = displayHeight
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height)

      const keypoints = interpolateFrame(frames, video.currentTime)
      if (!keypoints) return

      const scaleX = displayWidth / video.videoWidth
      const scaleY = displayHeight / video.videoHeight

      ctx.strokeStyle = '#22d3ee'
      ctx.lineWidth = 3
      ctx.lineCap = 'round'
      for (const [aIdx, bIdx] of POSE_CONNECTIONS) {
        const a = keypoints[aIdx]
        const b = keypoints[bIdx]
        if (!a || !b) continue
        ctx.beginPath()
        ctx.moveTo(a.x * scaleX, a.y * scaleY)
        ctx.lineTo(b.x * scaleX, b.y * scaleY)
        ctx.stroke()
      }

      ctx.fillStyle = '#a78bfa'
      for (const kp of keypoints) {
        ctx.beginPath()
        ctx.arc(kp.x * scaleX, kp.y * scaleY, 5, 0, Math.PI * 2)
        ctx.fill()
      }
    }

    rafId = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(rafId)
  }, [frames, videoRef])

  return <canvas ref={canvasRef} className="skeleton-overlay" />
}
```

- [ ] **Step 2: Write `SkeletonOverlay.css`**

```css
/* frontend/src/components/SkeletonOverlay.css */
.skeleton-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
```

- [ ] **Step 3: Verify it type-checks**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SkeletonOverlay.tsx frontend/src/components/SkeletonOverlay.css
git commit -m "feat: add SkeletonOverlay canvas component"
```

---

## Task 6: Wire into `ResultsView`, fix test fixtures, verify end-to-end

**Files:**
- Modify: `frontend/src/components/ResultsView.tsx`
- Modify: `frontend/src/components/ResultsView.css`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `SkeletonOverlay` (Task 5), `response.frames` (already present
  on every real `AnalysisResponse` since Task 1/2).

`ResultsView.tsx`'s current `<video>` element is a direct child of the
`.results` container, not wrapped in its own positioned box — the overlay
needs a `position: relative` wrapper around just the video to align
correctly. This step touches an already-fix-looped file; make the
targeted edit below, do not rewrite the whole file from scratch.

- [ ] **Step 1: Wrap the video and add the overlay in `ResultsView.tsx`**

In `frontend/src/components/ResultsView.tsx`, add the import:

```tsx
import { SkeletonOverlay } from './SkeletonOverlay'
```

Then replace this block (the `<video>` element and the `playbackError`
paragraph right after it — everything else in the file, including the
reset button, `Timeline`, and `RepCard` rendering below it, stays
unchanged):

```tsx
      <video
        ref={videoRef}
        src={videoUrl || undefined}
        controls
        data-testid="results-video"
        className="results__video"
        onLoadedMetadata={(event) => {
          const value = event.currentTarget.duration
          setDurationSec(Number.isFinite(value) ? value : 0)
        }}
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        onError={() => setPlaybackError(true)}
      />
      {playbackError && (
```

with:

```tsx
      <div className="results__video-wrap">
        <video
          ref={videoRef}
          src={videoUrl || undefined}
          controls
          data-testid="results-video"
          className="results__video"
          onLoadedMetadata={(event) => {
            const value = event.currentTarget.duration
            setDurationSec(Number.isFinite(value) ? value : 0)
          }}
          onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
          onError={() => setPlaybackError(true)}
        />
        <SkeletonOverlay frames={response.frames} videoRef={videoRef} />
      </div>
      {playbackError && (
```

- [ ] **Step 2: Add the wrapper's positioning to `ResultsView.css`**

Add to `frontend/src/components/ResultsView.css` (the existing
`.results__video` rule stays as-is — it still controls the video's own
sizing; this adds the new wrapper rule):

```css
.results__video-wrap {
  position: relative;
  margin-bottom: 16px;
}

.results__video-wrap .results__video {
  margin-bottom: 0;
}
```

(The `margin-bottom: 0` override is needed because `.results__video`'s
existing `margin-bottom: 16px` would otherwise double up with the new
wrapper's own margin — the wrapper now owns that spacing.)

- [ ] **Step 3: Fix `App.test.tsx`'s mock response**

`AnalysisResponse` now requires `frames` — the existing
`mockAnalysisResponse` in `frontend/src/App.test.tsx` doesn't include it.
This won't fail the type checker (the mock object is never statically
checked against the `AnalysisResponse` interface — it's consumed through
a generic mocked `fetch`), but it WILL fail at runtime once results
render: `SkeletonOverlay` receives `frames={response.frames}`, which
would be `undefined` here, and `interpolateFrame` calls
`frames.length` on it. Fix the mock:

```ts
const mockAnalysisResponse = { exercise: 'squat', frame_count: 100, reps: [], frames: [] }
```

This is the only change needed in `App.test.tsx` — with `frames: []`,
`interpolateFrame([], currentTime)` returns `null` for every tick (per
Task 4's empty-array test case), so `SkeletonOverlay` draws nothing during
these tests, which is correct: the tests don't exercise real skeleton
data, and shouldn't need to.

- [ ] **Step 4: Run the full test suite**

Run: `cd frontend && npx vitest run`
Expected: all test files pass (`App.test.tsx` 5/5, `interpolateFrame.test.ts`
6/6, `Timeline.test.tsx`, `RepCard.test.tsx`, `mockReps.test.ts`).

- [ ] **Step 5: Run the type checker and linter**

Run: `cd frontend && npx tsc -b --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 6: Manual verification with a real video**

This is the step that actually proves the feature works — none of the
automated tests exercise real canvas drawing against real extraction
output. With both the backend (rebuilt with real `cv_engine`, not the
stale stub) and frontend dev servers running, upload a real video with a
visible person and confirm: a cyan/violet skeleton appears on the video
synced to playback, moves smoothly (not stepping) as the video plays,
and disappears during any stretch where the person isn't detected rather
than freezing in a stale pose. Take a screenshot as evidence.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/ResultsView.tsx frontend/src/components/ResultsView.css \
        frontend/src/App.test.tsx
git commit -m "feat: render skeleton overlay on the results video"
```

---

## Post-plan state

After Task 6, uploading a real video shows a live skeleton overlay
tracking the real extracted pose, synced to playback, alongside the
existing (still mock-backed) rep timeline and cards. The overlay is
entirely real data — no mock/placeholder path exists for it, unlike
`mockReps.ts`. Rep-segmentation remains the one open sub-project that
would make the rep cards real too.
