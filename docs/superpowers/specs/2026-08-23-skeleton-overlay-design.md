# Pose Skeleton Overlay on the Results Video

**Status:** Approved for planning
**Date:** 2026-08-23
**Scope:** `backend/app/schemas/`, `backend/app/api/routes.py`, and
`frontend/` — extends the `/analyze/{exercise}` API contract to include
per-frame keypoints, and renders them as a skeleton overlay on the results
video. Rep-segmentation/scoring remains out of scope (unrelated,
not-yet-started sub-project).

## Background

`cv-engine`'s `KeypointExtractor::Extract` genuinely extracts 33-landmark
pose keypoints per sampled frame — this is real, working extraction (the
cv-engine pose-extraction plan). But `backend/app/api/routes.py` currently
discards the extracted frames entirely, keeping only `len(frames)` for
`AnalysisResponse.frame_count`. Nothing in the API response — and
therefore nothing in the frontend — exposes the actual keypoint data.
`backend/app/schemas/keypoint.py` already defines `Keypoint`/`Frame`
Pydantic models mirroring `cv-engine`'s C++ structs exactly; they're just
never used in `AnalysisResponse`.

The user, after testing the merged frontend results UI, asked to see the
real extraction visualized directly — a skeleton drawn on the video,
synced to playback — rather than continuing to trust it works from
`frame_count` alone.

## Goals

- Extend `AnalysisResponse` to include real per-frame keypoint data.
- Render a skeleton (dots + connecting lines) on top of the results
  video, synced to actual playback position, using real extraction output
  — no mock/placeholder skeleton data (unlike `mockReps.ts`, there is no
  reason to fake this: cv-engine's extraction is real today).
- Handle the two real gaps in the data honestly: keypoints only exist for
  *sampled* frames (not full 30fps), and some sampled frames have no
  detection at all.

## Non-goals

- Any change to rep-segmentation, scoring, or `mockReps.ts` — unrelated.
- 3D/depth visualization (`Keypoint.z` is extracted but unused here — 2D
  overlay only).
- Confidence-based visual treatment (dimming low-visibility points) — the
  approved design uses uniform styling per point; visibility-based
  rendering is a reasonable future refinement, not in scope now.
- Any change to `cv-engine`'s C++ extraction itself — this spec only
  plumbs already-extracted data through the API and renders it.

## Key decisions

1. **Delivery: bundled into the existing `/analyze` response**, not a
   separate endpoint. `AnalysisResponse` gains `frames: list[Frame]`
   (`Frame`/`Keypoint` already defined in `keypoint.py` — no new backend
   types needed, just wiring). Simpler than a second endpoint, at the
   cost of a larger single response payload; accepted given this project's
   current scale (no video-length cap exists yet regardless, per the
   cv-engine final review's parked findings).
2. **Rendering: absolutely-positioned `<canvas>` over the `<video>`
   element**, redrawn via `requestAnimationFrame` synced to
   `video.currentTime`. Chosen over an SVG overlay for redraw performance
   (33 points repositioned many times/sec) and simpler resize handling.
3. **Visual style: dots + connecting lines** (the standard MediaPipe
   "skeleton" look), cyan dots/lines consistent with the existing
   energetic/dark design tokens — approved via mockup over the real
   fixture photo.
4. **Between sampled frames: linear interpolation.** cv-engine samples at
   ~6-10fps (`kFrameSampleInterval`), not full 30fps. Rather than a
   visibly-stepping skeleton, interpolate each of the 33 `(x, y)` points
   between the two nearest sampled `Frame`s bracketing `currentTime`.
5. **Detection gaps: hide, never fabricate.** When `currentTime` falls
   where the bracketing frame(s) have empty `landmarks` (no person
   detected), or before the first / after the last sampled frame, draw
   nothing. Matches this project's existing principle (from the cv-engine
   spec) of never fabricating pose data that wasn't actually produced.
6. **Coordinate space: `Keypoint.x`/`y` are in original-video pixel
   coordinates** (confirmed against `LandmarkRegressor`'s decode math:
   `kp.x = crop_rect.x + lm[0] * sx`, absolute pixel offsets, not
   normalized 0-1). The overlay must scale from `video.videoWidth`/
   `videoHeight` (native resolution) to the canvas's actual displayed
   size, recomputed on resize — a real, easy-to-get-wrong detail worth
   stating explicitly.

## Architecture

```
Backend:
  routes.py: frames = KeypointExtractor().extract(tmp.name)   [already happens]
             AnalysisResponse(..., frame_count=len(frames), frames=frames)
                                                                [NEW: pass frames through]

Frontend (ResultsView.tsx):
  <video ref={videoRef} .../>              [existing]
  <SkeletonOverlay frames={response.frames} videoRef={videoRef} />   [NEW]

SkeletonOverlay.tsx:
  - <canvas> sized/positioned via ResizeObserver on the video element
  - on each rAF tick (while mounted):
      currentTime = videoRef.current.currentTime
      kps = interpolateFrame(frames, currentTime)   // null if no data here
      clear canvas
      if (kps) draw POSE_CONNECTIONS as lines, then 33 dots, scaled to
                canvas's displayed size
```

## Components

- `backend/app/schemas/analysis.py` — `AnalysisResponse` gains `frames:
  list[Frame]` (import `Frame` from `.keypoint`).
- `backend/app/api/routes.py` — `analyze()` passes `frames=frames` into
  the `AnalysisResponse(...)` constructor (the variable already exists
  locally, currently only `len()`'d).
- `frontend/src/types.ts` — new `Keypoint`/`Frame` interfaces mirroring
  the backend exactly (`x, y, z, visibility` / `timestamp_sec,
  landmarks: Keypoint[]`); `AnalysisResponse` gains `frames: Frame[]`.
- `frontend/src/poseConnections.ts` (new) — `POSE_CONNECTIONS: [number,
  number][]`, the static MediaPipe 33-landmark bone topology (shoulder
  11-12, 11-13-15 / 12-14-16 arms, 11-23 / 12-24 torso sides, 23-24 hips,
  23-25-27 / 24-26-28 legs — the standard, well-documented set; auxiliary
  face/hand/foot landmarks beyond the core body skeleton are excluded to
  keep the drawn skeleton clean).
- `frontend/src/interpolateFrame.ts` (new) — pure function:
  `interpolateFrame(frames: Frame[], currentTime: number): Keypoint[] |
  null`. Binary-searches `frames` (already timestamp-ordered from
  extraction) for the bracketing pair, returns `null` on any gap/edge
  case per Key Decision 5, otherwise lerps `x`/`y` per point (ignores
  `z`/`visibility` per Non-goals).
- `frontend/src/components/SkeletonOverlay.tsx` (new) — owns the
  `<canvas>`, the `ResizeObserver`, and the `requestAnimationFrame` draw
  loop; calls `interpolateFrame` each tick and draws via the 2D canvas
  API.
- `ResultsView.tsx` — renders `<SkeletonOverlay frames={response.frames}
  videoRef={videoRef} />` positioned over the existing `<video>` (a
  wrapping container with `position: relative` if one doesn't already
  exist around the video element — check current `ResultsView.tsx`
  during planning).

## Data flow

1. Backend: unchanged extraction, newly-included `frames` in the JSON
   response.
2. `ResultsView` already fetches `response` (existing) — passes
   `response.frames` straight through to `SkeletonOverlay`, no
   transformation.
3. `SkeletonOverlay`'s draw loop reads `videoRef.current.currentTime`
   every animation frame (not from React state — avoids a re-render per
   frame; this is a canvas-imperative loop, matching how `ResultsView`
   already reads `currentTime` from the video element's native events for
   its own state, but the overlay's OWN redraw loop is independent of
   React's render cycle for performance).
4. Scale factors (`canvas.clientWidth / video.videoWidth`, same for Y)
   recomputed inside the draw loop (cheap) or cached and invalidated by
   the `ResizeObserver` (slightly more code, avoids redundant reads) —
   pin the exact approach during planning; either is correct.

## Error handling

- `frames` empty or missing entirely (defensive — `frame_count > 0`
  should imply non-empty `frames`, but don't assume the two never
  diverge) → `interpolateFrame` returns `null` for every `currentTime`,
  overlay draws nothing, no crash.
- Video not yet loaded (`videoWidth === 0`) → skip drawing until
  `loadedmetadata` (same event `ResultsView` already uses for duration).
- Canvas 2D context unavailable (should not happen in any real browser,
  but `getContext('2d')` can return `null` per its type signature) →
  bail out of the draw loop gracefully, no crash.

## Testing

- `interpolateFrame.test.ts` — the core logic, fully unit-testable
  without any canvas/DOM: exact match at a sample timestamp, midpoint
  linear interpolation between two known frames, `null` for a gap where
  the bracketing frame(s) have empty `landmarks`, `null` before the first
  / after the last frame's timestamp.
- `poseConnections.ts` — static data, no test needed.
- `SkeletonOverlay` itself — canvas-drawing side effects are awkward to
  unit test meaningfully (would mostly be testing that canvas API calls
  happened, not that pixels are correct); rely on the extracted
  `interpolateFrame` unit tests for the logic and a manual/visual check
  (dev server + real upload) for the rendering — consistent with how
  `ResultsView`'s own video-element wiring has no dedicated unit test
  either, per the existing plan's precedent.
- Backend: no new test file needed — `AnalysisResponse` gaining a field
  is exercised implicitly by existing `pytest backend/tests` runs (adjust
  any existing response-shape assertions if they check exact keys).

## Open questions for the implementation plan

- Exact `POSE_CONNECTIONS` index pairs — pin the precise standard MediaPipe
  33-point topology during planning (it's a well-documented, static list;
  get it right once rather than approximating).
- Whether scale-factor caching (via `ResizeObserver`) or per-tick
  recomputation is used — either is correct, pin one during planning for
  consistency.
