# Frontend: Results UI Beyond the Scaffold

**Status:** Approved for planning
**Date:** 2026-08-23
**Scope:** `frontend/` only. Builds a real upload + results experience around
FormIQ's existing `/analyze/{exercise}` endpoint. Backend rep-segmentation/
scoring is a separate, unbuilt sub-project (`reps` is always `[]` today) —
this spec designs the frontend as if that data exists, using a mock
fallback, so the real UI is ready the moment backend scoring ships.

## Background

The current frontend (`frontend/src/App.tsx`) is the original scaffold: a
single form (exercise `<select>`, file input, submit button) that calls
`checkHealth()`/`analyzeVideo()` and dumps the raw JSON response in a
`<pre>` block. No styling investment, no results visualization. The
cv-engine work (separate, already-merged plan) means `frame_count` in that
JSON is now real; `reps` remains `[]` until backend rep-segmentation exists.

## Goals

- A genuinely designed upload → results flow, not placeholder UI.
- Design and build the results view (rep list, per-rep form-accuracy,
  fault tags, video scrubbing) against the real `RepScore` shape now, via a
  mock-data fallback — so it needs no rework when backend scoring ships.
- Real video playback in the results view, synced to rep boundaries.
- Stay inside the existing stack: React 19 + TypeScript (strict), Vite,
  Vitest + Testing Library, plain CSS. No new frameworks/libraries.

## Non-goals

- Backend changes of any kind (this is frontend-only).
- Routing / multi-page navigation (single page, matches current scaffold
  and the backend's stateless single-request model).
- Persistence / history of past analyses (no backend support exists).
- Auth.

## Key decisions

1. **Design ahead of the data, with a mock fallback, not placeholder UI.**
   A `getReps(response, file)` seam returns `response.reps` when non-empty,
   otherwise deterministic mock reps seeded from the uploaded video's real
   duration (so mock rep boundaries land inside the actual clip and the
   scrubber never seeks to nowhere). `App.tsx` and `ResultsView` are written
   against the real `RepScore` shape (`rep_index`, `start_sec`, `end_sec`,
   `form_accuracy`, `faults: string[]`, from
   `backend/app/schemas/analysis.py`) with zero knowledge of the mock
   fallback's existence — the fallback lives in one isolated file
   (`mockReps.ts`) that gets deleted outright once real scoring ships,
   with no other file touched.
2. **Single page, no routing.** Upload → results happens in place via a
   local state machine (`idle | analyzing | results`), matching the
   scaffold's existing shape and the backend's stateless model.
3. **Layout: stacked timeline**, not side-by-side video+playlist. Full-width
   video on top, a color-coded segment bar showing all reps across the clip
   at a glance immediately below it, then a row of per-rep detail cards.
   Chosen over side-by-side (video + sidebar list) for giving the whole
   set's shape at a glance before drilling into any one rep.
4. **Real client-side video playback**, not a static/decorative timeline.
   The uploaded `File` is kept in state through the whole session;
   `ResultsView` builds a `URL.createObjectURL(file)` for an actual
   `<video>` element. Clicking a rep card or a timeline segment seeks the
   video's `currentTime` to that rep's `start_sec`. No backend involvement
   — the file is already in the browser.
5. **Visual direction: energetic/dark.** Dark background (`#111827` family),
   bright accent gradient (cyan `#22d3ee` → violet `#a78bfa`), bold
   sans-serif weights, pill-shaped tags/buttons. Approved via mockups for
   both the upload screen and results-view color language (form-accuracy
   badges, fault tags).
6. **Plain CSS, matching the existing pattern** (`App.css`/`index.css`) —
   no CSS framework or component library introduced.

## Architecture

```
App.tsx (state machine: idle | analyzing | results)
   │
   ├─ idle ──────────► UploadForm
   │                     exercise picker + dropzone + Analyze button
   │                     onSubmit → setStatus('analyzing'), keep File in state
   │
   ├─ analyzing ─────► AnalyzingView
   │                     spinner + "Analyzing your <exercise> set…"
   │                     on analyzeVideo() resolve → setStatus('results')
   │                     on reject → setStatus('idle') + error message
   │
   └─ results ───────► ResultsView
                          reps = getReps(response, file)   [mockReps.ts fallback]
                          videoUrl = useMemo(() => URL.createObjectURL(file), [file])
                          │
                          ├─ <video> element (native playback)
                          ├─ Timeline (segment bar, onSeek)
                          └─ RepCard[] (per-rep detail, onSeek)
```

## Components

| File | Responsibility | Depends on |
|---|---|---|
| `App.tsx` (rewritten) | State machine + orchestration only — no more inline form/results JSX | `UploadForm`, `AnalyzingView`, `ResultsView`, `api.ts` |
| `UploadForm.tsx` (new) | Exercise pill-picker, dropzone, Analyze button | `types.ts` (`Exercise`, `EXERCISES`) |
| `AnalyzingView.tsx` (new) | Spinner state, takes `exercise` for the label | — |
| `ResultsView.tsx` (new) | Owns playback state (`currentTime`), renders video + Timeline + RepCard row | `Timeline`, `RepCard`, `mockReps.ts`, `types.ts` |
| `Timeline.tsx` (new) | Pure presentational: `{reps, durationSec, currentTime, onSeek}` → colored segment bar | `types.ts` (`RepScore`) |
| `RepCard.tsx` (new) | Pure presentational: one `RepScore` + `active: boolean` + `onSeek` → accuracy badge + fault tags | `types.ts` (`RepScore`) |
| `mockReps.ts` (new) | `getReps(response, durationSec): RepScore[]` — real reps if non-empty, else seeded mock | `types.ts` (`AnalysisResponse`, `RepScore`) |

`types.ts` already defines `RepScore` (`rep_index`, `start_sec`, `end_sec`,
`form_accuracy`, `faults: string[]`) and `AnalysisResponse`, mirroring the
backend exactly — no new types needed there; `mockReps.ts` imports these
rather than duplicating the shape.

`Timeline` and `RepCard` take no `File`/fetch/video-element coupling —
independently unit-testable with plain props.

## Data flow

1. `UploadForm.onSubmit` → `App` stores the `File` in state (not just
   passed transiently) and calls `analyzeVideo(exercise, file)`.
2. On resolve: `App` stores the `AnalysisResponse`, `status = 'results'`.
3. `ResultsView` computes `reps = getReps(response, videoDurationSec)` —
   `videoDurationSec` comes from the `<video>` element's `loadedmetadata`
   event (real duration), not guessed, so mock rep boundaries are always
   valid regardless of the uploaded clip's actual length.
4. Rep click (card or timeline segment) → `onSeek(startSec)` → `ResultsView`
   sets the `<video>` ref's `.currentTime` and updates `currentTime` state
   (drives which `RepCard`/segment shows as active).
5. `videoUrl` (`URL.createObjectURL(file)`) is revoked
   (`URL.revokeObjectURL`) in a cleanup effect when `ResultsView` unmounts
   or `file` changes, to avoid leaking blob URLs across repeated analyses
   in one session.

## Error handling

- Analysis failure (existing `try/catch` around `analyzeVideo`): kept,
  restyled to the dark palette. Returns to `idle` with an error message
  shown above the form.
- **New: client-side file-type rejection** before upload — reject/warn on
  extensions outside an allowlist (`.mp4`, `.mov`, `.webm`), matching a
  hardening gap the cv-engine final review separately flagged on the
  backend side (`routes.py` doesn't allowlist either — out of scope here,
  frontend-side check is independent and doesn't require that backend fix).
- **New: video-playback failure state** in `ResultsView`, distinct from
  analysis failure — the `<video>` element's `onError` sets a local "this
  browser can't play this video for preview" message (the backend accepted
  the file and returned results; playback failing is a separate, narrower
  failure that shouldn't discard the results already received).

## Testing

Extend the existing Vitest + Testing Library setup (`frontend/src/App.test.tsx`,
`frontend/src/test/setup.ts` — already configured, no new dependencies):

- `Timeline.test.tsx` — pure-prop rendering: correct segment count/colors
  for a given `reps` array, `onSeek` called with the right `start_sec` on
  segment click.
- `RepCard.test.tsx` — renders accuracy/fault tags correctly, `active`
  styling toggles, `onSeek` fires on click.
- `mockReps.test.ts` — `getReps` returns `response.reps` unchanged when
  non-empty; falls back to generated mock reps (with boundaries inside
  `[0, durationSec]`) when `response.reps` is empty.
- `App.test.tsx` (extended) — integration test driving `idle → analyzing →
  results` with a mocked `analyzeVideo`, asserting the results view renders
  rep cards from the (mocked) response.

## Open questions for the implementation plan

- Exact mock-rep generation algorithm (how many reps, how accuracy/faults
  are seeded) — needs to be deterministic and visually reasonable, not
  random; pin exact logic during planning.
- Exact fault-tag vocabulary shown in mock data — plan should pick a small
  representative set (e.g. "Knee valgus", "Depth", "Back rounding") rather
  than inventing arbitrary strings per rep.
