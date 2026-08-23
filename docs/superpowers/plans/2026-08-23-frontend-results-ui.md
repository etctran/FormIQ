# Frontend Results UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the scaffold's inline upload-form-plus-JSON-dump with a real
upload → results experience: an energetic/dark styled upload form, an
analyzing state, and a results view with a stacked video + color-coded
timeline + per-rep cards, all driven by real client-side video playback.

**Architecture:** `App.tsx` becomes a thin `idle | analyzing | results`
state machine composing three new view components (`UploadForm`,
`AnalyzingView`, `ResultsView`). `ResultsView` composes two pure
presentational components (`Timeline`, `RepCard`) and a `getReps()` seam
(`mockReps.ts`) that returns the backend's real `reps` when non-empty, or
deterministic mock reps seeded from the video's real duration otherwise —
so every other component is written against the real `RepScore` shape with
no awareness the mock fallback exists.

**Tech Stack:** React 19 + TypeScript (strict), Vite, Vitest + Testing
Library (already installed — no new dependencies), plain CSS.

**Spec:** `docs/superpowers/specs/2026-08-23-frontend-results-ui-design.md`

## Global Constraints

- No new dependencies — stay inside React, TypeScript, Vite, Vitest,
  `@testing-library/react`, `@testing-library/jest-dom`. Use `fireEvent`
  from `@testing-library/react` for test interactions, not
  `@testing-library/user-event` (not installed).
- `types.ts` already defines `RepScore`/`AnalysisResponse` matching the
  backend exactly — do not redefine these shapes anywhere else.
- The mock-data fallback lives ONLY in `mockReps.ts` — no other file
  branches on whether `reps` is real or mocked.
- Single fixed dark theme (energetic/dark) — no `prefers-color-scheme`
  adaptive light mode; the existing light-mode tokens in `index.css` are
  being replaced, not preserved as a media-query branch.
- Single page, no routing — status transitions (`idle | analyzing |
  results`) are local `App` state, not routes.
- Client-side file-type allowlist: `.mp4`, `.mov`, `.webm`.

---

## Task 1: `getReps()` mock-data seam

**Files:**
- Create: `frontend/src/mockReps.ts`
- Test: `frontend/src/mockReps.test.ts`

**Interfaces:**
- Consumes: `AnalysisResponse`, `RepScore` from `frontend/src/types.ts`
  (already defined — `RepScore = {rep_index, start_sec, end_sec,
  form_accuracy, faults: string[]}`, `AnalysisResponse = {exercise,
  frame_count, reps: RepScore[]}`).
- Produces: `getReps(response: AnalysisResponse, durationSec: number):
  RepScore[]`. Consumed by Task 7 (`ResultsView`).

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/src/mockReps.test.ts
import { describe, expect, it } from 'vitest'
import { getReps } from './mockReps'
import type { AnalysisResponse } from './types'

const baseResponse: AnalysisResponse = { exercise: 'squat', frame_count: 100, reps: [] }

describe('getReps', () => {
  it('returns real reps unchanged when present', () => {
    const realReps = [
      { rep_index: 0, start_sec: 0, end_sec: 2, form_accuracy: 0.9, faults: [] },
    ]
    const response: AnalysisResponse = { ...baseResponse, reps: realReps }
    expect(getReps(response, 10)).toBe(realReps)
  })

  it('generates mock reps within [0, durationSec] when reps is empty', () => {
    const reps = getReps(baseResponse, 20)
    expect(reps.length).toBeGreaterThan(0)
    for (const rep of reps) {
      expect(rep.start_sec).toBeGreaterThanOrEqual(0)
      expect(rep.end_sec).toBeLessThanOrEqual(20)
      expect(rep.start_sec).toBeLessThan(rep.end_sec)
    }
  })

  it('caps mock rep count at 8 for long videos', () => {
    const reps = getReps(baseResponse, 1000)
    expect(reps.length).toBe(8)
  })

  it('returns empty array for zero/negative duration', () => {
    expect(getReps(baseResponse, 0)).toEqual([])
    expect(getReps(baseResponse, -5)).toEqual([])
  })

  it('is deterministic across calls', () => {
    expect(getReps(baseResponse, 20)).toEqual(getReps(baseResponse, 20))
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/mockReps.test.ts`
Expected: FAIL — `mockReps.ts` doesn't exist yet.

- [ ] **Step 3: Write `mockReps.ts`**

```ts
// frontend/src/mockReps.ts
import type { AnalysisResponse, RepScore } from './types'

const MOCK_ACCURACIES = [0.92, 0.78, 0.95, 0.88, 0.91, 0.73, 0.97, 0.85]
const MOCK_FAULTS = ['Knee valgus', 'Insufficient depth', 'Back rounding', 'Heel rise']
const SECONDS_PER_MOCK_REP = 4
const MAX_MOCK_REPS = 8

// Real reps if the backend provided any; otherwise deterministic mock reps
// seeded from the video's own duration, so boundaries always land inside
// the real clip. This is the ONLY file that knows mock data exists — every
// other component (Timeline, RepCard, ResultsView) is written against the
// real RepScore shape with no branching on where the data came from.
// Delete this file + mockReps.test.ts outright once backend
// rep-segmentation ships real reps.
export function getReps(response: AnalysisResponse, durationSec: number): RepScore[] {
  if (response.reps.length > 0) return response.reps
  if (durationSec <= 0) return []

  const repCount = Math.min(
    MAX_MOCK_REPS,
    Math.max(1, Math.round(durationSec / SECONDS_PER_MOCK_REP)),
  )
  const segmentLength = durationSec / repCount

  return Array.from({ length: repCount }, (_, i) => {
    const formAccuracy = MOCK_ACCURACIES[i % MOCK_ACCURACIES.length]
    const hasFault = formAccuracy < 0.85
    return {
      rep_index: i,
      start_sec: i * segmentLength,
      end_sec: (i + 1) * segmentLength,
      form_accuracy: formAccuracy,
      faults: hasFault ? [MOCK_FAULTS[i % MOCK_FAULTS.length]] : [],
    }
  })
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/mockReps.test.ts`
Expected: PASS, 5/5 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/mockReps.ts frontend/src/mockReps.test.ts
git commit -m "feat: add getReps mock-data fallback seam"
```

---

## Task 2: `Timeline` component

**Files:**
- Create: `frontend/src/components/Timeline.tsx`
- Create: `frontend/src/components/Timeline.css`
- Test: `frontend/src/components/Timeline.test.tsx`

**Interfaces:**
- Consumes: `RepScore` from `frontend/src/types.ts`.
- Produces: `Timeline({reps: RepScore[], durationSec: number, currentTime:
  number, onSeek: (seconds: number) => void})` — a React component.
  Consumed by Task 7 (`ResultsView`).

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/components/Timeline.test.tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Timeline } from './Timeline'
import type { RepScore } from '../types'

const reps: RepScore[] = [
  { rep_index: 0, start_sec: 0, end_sec: 5, form_accuracy: 0.9, faults: [] },
  { rep_index: 1, start_sec: 5, end_sec: 10, form_accuracy: 0.7, faults: ['Knee valgus'] },
]

describe('Timeline', () => {
  it('renders one segment per rep', () => {
    render(<Timeline reps={reps} durationSec={10} currentTime={0} onSeek={vi.fn()} />)
    expect(screen.getAllByRole('button')).toHaveLength(2)
  })

  it('calls onSeek with the rep start time when a segment is clicked', () => {
    const onSeek = vi.fn()
    render(<Timeline reps={reps} durationSec={10} currentTime={0} onSeek={onSeek} />)
    fireEvent.click(screen.getByLabelText(/Rep 2/))
    expect(onSeek).toHaveBeenCalledWith(5)
  })

  it('marks the segment containing currentTime as active', () => {
    render(<Timeline reps={reps} durationSec={10} currentTime={6} onSeek={vi.fn()} />)
    expect(screen.getByLabelText(/Rep 2/)).toHaveClass('timeline-segment--active')
    expect(screen.getByLabelText(/Rep 1/)).not.toHaveClass('timeline-segment--active')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/Timeline.test.tsx`
Expected: FAIL — `Timeline.tsx` doesn't exist yet.

- [ ] **Step 3: Write `Timeline.tsx`**

```tsx
// frontend/src/components/Timeline.tsx
import type { RepScore } from '../types'
import './Timeline.css'

interface TimelineProps {
  reps: RepScore[]
  durationSec: number
  currentTime: number
  onSeek: (seconds: number) => void
}

function segmentColorClass(rep: RepScore): string {
  return rep.faults.length > 0 ? 'timeline-segment--fault' : 'timeline-segment--good'
}

export function Timeline({ reps, durationSec, currentTime, onSeek }: TimelineProps) {
  return (
    <div className="timeline" role="group" aria-label="Rep timeline">
      {reps.map((rep) => {
        const widthPct = durationSec > 0 ? ((rep.end_sec - rep.start_sec) / durationSec) * 100 : 0
        const isActive = currentTime >= rep.start_sec && currentTime < rep.end_sec
        return (
          <button
            key={rep.rep_index}
            type="button"
            className={[
              'timeline-segment',
              segmentColorClass(rep),
              isActive ? 'timeline-segment--active' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            style={{ width: `${widthPct}%` }}
            onClick={() => onSeek(rep.start_sec)}
            aria-label={`Rep ${rep.rep_index + 1}, ${Math.round(rep.form_accuracy * 100)}%`}
          />
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Write `Timeline.css`**

```css
/* frontend/src/components/Timeline.css */
.timeline {
  display: flex;
  height: 20px;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 16px;
}

.timeline-segment {
  border: none;
  cursor: pointer;
  padding: 0;
}

.timeline-segment--good {
  background: var(--good);
}

.timeline-segment--fault {
  background: var(--warn);
}

.timeline-segment--active {
  outline: 2px solid var(--accent-cyan);
  outline-offset: -2px;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/Timeline.test.tsx`
Expected: PASS, 3/3 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Timeline.tsx frontend/src/components/Timeline.css \
        frontend/src/components/Timeline.test.tsx
git commit -m "feat: add Timeline component"
```

---

## Task 3: `RepCard` component

**Files:**
- Create: `frontend/src/components/RepCard.tsx`
- Create: `frontend/src/components/RepCard.css`
- Test: `frontend/src/components/RepCard.test.tsx`

**Interfaces:**
- Consumes: `RepScore` from `frontend/src/types.ts`.
- Produces: `RepCard({rep: RepScore, active: boolean, onSeek: (seconds:
  number) => void})` — a React component. Consumed by Task 7
  (`ResultsView`).

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/components/RepCard.test.tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RepCard } from './RepCard'
import type { RepScore } from '../types'

const rep: RepScore = {
  rep_index: 1,
  start_sec: 4,
  end_sec: 8,
  form_accuracy: 0.78,
  faults: ['Knee valgus'],
}

describe('RepCard', () => {
  it('renders the rep number, accuracy, and fault tags', () => {
    render(<RepCard rep={rep} active={false} onSeek={vi.fn()} />)
    expect(screen.getByText('Rep 2')).toBeInTheDocument()
    expect(screen.getByText('78%')).toBeInTheDocument()
    expect(screen.getByText('Knee valgus')).toBeInTheDocument()
  })

  it('renders no fault tags when faults is empty', () => {
    render(
      <RepCard
        rep={{ ...rep, faults: [] }}
        active={false}
        onSeek={vi.fn()}
      />,
    )
    expect(screen.queryByText('Knee valgus')).not.toBeInTheDocument()
  })

  it('calls onSeek with start_sec when clicked', () => {
    const onSeek = vi.fn()
    render(<RepCard rep={rep} active={false} onSeek={onSeek} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onSeek).toHaveBeenCalledWith(4)
  })

  it('applies active styling class when active', () => {
    render(<RepCard rep={rep} active onSeek={vi.fn()} />)
    expect(screen.getByRole('button')).toHaveClass('rep-card--active')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/RepCard.test.tsx`
Expected: FAIL — `RepCard.tsx` doesn't exist yet.

- [ ] **Step 3: Write `RepCard.tsx`**

```tsx
// frontend/src/components/RepCard.tsx
import type { RepScore } from '../types'
import './RepCard.css'

interface RepCardProps {
  rep: RepScore
  active: boolean
  onSeek: (seconds: number) => void
}

export function RepCard({ rep, active, onSeek }: RepCardProps) {
  const accuracyPct = Math.round(rep.form_accuracy * 100)
  return (
    <button
      type="button"
      className={`rep-card ${active ? 'rep-card--active' : ''}`.trim()}
      onClick={() => onSeek(rep.start_sec)}
    >
      <span className="rep-card__label">Rep {rep.rep_index + 1}</span>
      <span
        className={`rep-card__accuracy ${rep.faults.length > 0 ? 'rep-card__accuracy--warn' : ''}`.trim()}
      >
        {accuracyPct}%
      </span>
      {rep.faults.map((fault) => (
        <span key={fault} className="rep-card__fault">
          {fault}
        </span>
      ))}
    </button>
  )
}
```

- [ ] **Step 4: Write `RepCard.css`**

```css
/* frontend/src/components/RepCard.css */
.rep-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  color: var(--text);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.rep-card--active {
  border-color: var(--accent-cyan);
}

.rep-card__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
}

.rep-card__accuracy {
  font-size: 18px;
  font-weight: 700;
  color: var(--accent-cyan);
}

.rep-card__accuracy--warn {
  color: var(--warn);
}

.rep-card__fault {
  font-size: 11px;
  background: var(--danger);
  color: white;
  border-radius: 20px;
  padding: 2px 8px;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/RepCard.test.tsx`
Expected: PASS, 4/4 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/RepCard.tsx frontend/src/components/RepCard.css \
        frontend/src/components/RepCard.test.tsx
git commit -m "feat: add RepCard component"
```

---

## Task 4: Energetic/dark design tokens

**Files:**
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: CSS custom properties (`--text`, `--text-h`, `--text-muted`,
  `--bg`, `--bg-raised`, `--border`, `--accent-cyan`, `--accent-violet`,
  `--accent-gradient`, `--danger`, `--warn`, `--good`, `--sans`, `--mono`)
  on `:root`. Consumed by every component's CSS from this task onward
  (Task 2/3's CSS already reference `--good`/`--warn`/`--accent-cyan`/
  `--danger`/`--bg-raised`/`--border`/`--text`/`--text-muted` — those
  files were written first but this task's tokens are what make them
  resolve to real colors; order doesn't matter for CSS custom properties,
  but this task must land before anyone judges the app's actual rendered
  look).

This task has no unit test — it's a visual/token change. Verification is
running the dev server and looking at it.

- [ ] **Step 1: Replace `index.css`'s root tokens**

```css
/* frontend/src/index.css */
:root {
  --text: #c7ccd6;
  --text-h: #ffffff;
  --text-muted: #8b93a5;
  --bg: #111827;
  --bg-raised: #1f2937;
  --border: #374151;
  --accent-cyan: #22d3ee;
  --accent-violet: #a78bfa;
  --accent-gradient: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet));
  --danger: #dc2626;
  --warn: #fbbc04;
  --good: #34a853;

  --sans: 'Segoe UI', system-ui, Roboto, sans-serif;
  --mono: ui-monospace, Consolas, monospace;

  font: 16px/145% var(--sans);
  color: var(--text);
  background: var(--bg);
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

body {
  margin: 0;
}

h1 {
  font-family: var(--sans);
  font-weight: 800;
  letter-spacing: -0.5px;
  color: var(--text-h);
}

code,
pre {
  font-family: var(--mono);
}
```

This removes the old light-mode default tokens, the
`@media (prefers-color-scheme: dark)` override block, and
`color-scheme: light dark` — per the Global Constraints, this is now a
single fixed dark theme, not an adaptive one.

- [ ] **Step 2: Verify visually**

Run: `cd frontend && npm run dev`, open the printed localhost URL.
Expected: dark background, light text, no console errors. (The page will
look unstyled/plain until Task 5 rewrites the form — that's expected, this
task only lands the tokens.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat: replace light/dark adaptive tokens with fixed energetic/dark palette"
```

---

## Task 5: `UploadForm` component

**Files:**
- Create: `frontend/src/components/UploadForm.tsx`
- Create: `frontend/src/components/UploadForm.css`

**Interfaces:**
- Consumes: `EXERCISES`, `Exercise` from `frontend/src/types.ts`. CSS
  tokens from Task 4.
- Produces: `UploadForm({onSubmit: (exercise: Exercise, video: File) =>
  void})` — a React component. Consumed by Task 8 (`App.tsx`).

No dedicated unit test file for this component per the spec's Testing
section (it's exercised via Task 8's `App.test.tsx` integration test,
which already covers "disables submit until a video is selected" and
drives a real submit through it).

- [ ] **Step 1: Write `UploadForm.tsx`**

```tsx
// frontend/src/components/UploadForm.tsx
import { useState } from 'react'
import type { FormEvent } from 'react'
import { EXERCISES } from '../types'
import type { Exercise } from '../types'
import './UploadForm.css'

const ALLOWED_EXTENSIONS = ['.mp4', '.mov', '.webm']

interface UploadFormProps {
  onSubmit: (exercise: Exercise, video: File) => void
}

function hasAllowedExtension(filename: string): boolean {
  const lower = filename.toLowerCase()
  return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

export function UploadForm({ onSubmit }: UploadFormProps) {
  const [exercise, setExercise] = useState<Exercise>(EXERCISES[0])
  const [video, setVideo] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)

  const handleFileChange = (file: File | null) => {
    if (file && !hasAllowedExtension(file.name)) {
      setFileError('Unsupported file type — use .mp4, .mov, or .webm')
      setVideo(null)
      return
    }
    setFileError(null)
    setVideo(file)
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!video) return
    onSubmit(exercise, video)
  }

  return (
    <form onSubmit={handleSubmit} className="upload-form">
      <div className="upload-form__label">Exercise</div>
      <div className="upload-form__pills" role="radiogroup" aria-label="Exercise">
        {EXERCISES.map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={exercise === option}
            className={`upload-form__pill ${exercise === option ? 'upload-form__pill--active' : ''}`.trim()}
            onClick={() => setExercise(option)}
          >
            {option.replace('_', ' ')}
          </button>
        ))}
      </div>

      <label htmlFor="video" className="upload-form__dropzone">
        {video ? video.name : 'Drop a video or click to browse'}
        <input
          id="video"
          type="file"
          accept="video/*"
          onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
        />
      </label>
      {fileError && <p className="error">{fileError}</p>}

      <button type="submit" className="upload-form__submit" disabled={!video}>
        Analyze
      </button>
    </form>
  )
}
```

- [ ] **Step 2: Write `UploadForm.css`**

```css
/* frontend/src/components/UploadForm.css */
.upload-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
}

.upload-form__label {
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  margin-bottom: 4px;
}

.upload-form__pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.upload-form__pill {
  background: var(--bg-raised);
  color: var(--text);
  border: none;
  padding: 7px 14px;
  border-radius: 20px;
  font-size: 13px;
  cursor: pointer;
  text-transform: capitalize;
}

.upload-form__pill--active {
  background: var(--accent-cyan);
  color: var(--bg);
  font-weight: 700;
}

.upload-form__dropzone {
  border: 2px dashed var(--border);
  border-radius: 10px;
  padding: 36px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  margin-bottom: 20px;
  cursor: pointer;
  display: block;
}

.upload-form__dropzone input {
  display: none;
}

.upload-form__submit {
  background: var(--accent-gradient);
  color: var(--bg);
  font-weight: 700;
  padding: 12px;
  border-radius: 8px;
  border: none;
  font-size: 14px;
  cursor: pointer;
}

.upload-form__submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

- [ ] **Step 3: Verify it type-checks**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors (this component isn't wired into `App.tsx` yet — Task
8 does that — so this just confirms the file itself is valid TypeScript in
isolation).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/UploadForm.tsx frontend/src/components/UploadForm.css
git commit -m "feat: add UploadForm component"
```

---

## Task 6: `AnalyzingView` component

**Files:**
- Create: `frontend/src/components/AnalyzingView.tsx`
- Create: `frontend/src/components/AnalyzingView.css`

**Interfaces:**
- Consumes: `Exercise` from `frontend/src/types.ts`. CSS tokens from Task 4.
- Produces: `AnalyzingView({exercise: Exercise})` — a React component.
  Consumed by Task 8 (`App.tsx`).

No dedicated unit test file — trivial presentational component, exercised
via Task 8's integration test (which asserts the "Analyzing your squat
set…" text appears mid-flow).

- [ ] **Step 1: Write `AnalyzingView.tsx`**

```tsx
// frontend/src/components/AnalyzingView.tsx
import type { Exercise } from '../types'
import './AnalyzingView.css'

interface AnalyzingViewProps {
  exercise: Exercise
}

export function AnalyzingView({ exercise }: AnalyzingViewProps) {
  return (
    <div className="analyzing">
      <div className="analyzing__spinner" />
      <p className="analyzing__title">Analyzing your {exercise.replace('_', ' ')} set…</p>
      <p className="analyzing__subtitle">Extracting pose keypoints frame by frame</p>
    </div>
  )
}
```

- [ ] **Step 2: Write `AnalyzingView.css`**

```css
/* frontend/src/components/AnalyzingView.css */
.analyzing {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
}

.analyzing__spinner {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 4px solid var(--bg-raised);
  border-top-color: var(--accent-cyan);
  margin-bottom: 18px;
  animation: analyzing-spin 0.8s linear infinite;
}

@keyframes analyzing-spin {
  to {
    transform: rotate(360deg);
  }
}

.analyzing__title {
  color: var(--text-h);
  font-weight: 600;
  font-size: 15px;
  margin: 0 0 6px;
}

.analyzing__subtitle {
  color: var(--text-muted);
  font-size: 12px;
  margin: 0;
}
```

- [ ] **Step 3: Verify it type-checks**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AnalyzingView.tsx frontend/src/components/AnalyzingView.css
git commit -m "feat: add AnalyzingView component"
```

---

## Task 7: `ResultsView` component

**Files:**
- Create: `frontend/src/components/ResultsView.tsx`
- Create: `frontend/src/components/ResultsView.css`

**Interfaces:**
- Consumes: `AnalysisResponse` from `frontend/src/types.ts`;
  `getReps(response, durationSec)` from `frontend/src/mockReps.ts` (Task
  1); `Timeline` from `frontend/src/components/Timeline.tsx` (Task 2);
  `RepCard` from `frontend/src/components/RepCard.tsx` (Task 3).
- Produces: `ResultsView({response: AnalysisResponse, video: File})` — a
  React component with a `data-testid="results-video"` on its `<video>`
  element (needed because Task 8's test fires `loadedmetadata` on it —
  video elements have no distinguishing accessible role). Consumed by
  Task 8 (`App.tsx`).

No dedicated unit test file for this component — it owns real browser
media/URL APIs (`URL.createObjectURL`, video element events) that are
better exercised once, end-to-end, via Task 8's `App.test.tsx` integration
test (which is also where the jsdom `URL.createObjectURL` polyfill this
component needs gets added, since that's the first test that renders it).

- [ ] **Step 1: Write `ResultsView.tsx`**

```tsx
// frontend/src/components/ResultsView.tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import type { AnalysisResponse } from '../types'
import { getReps } from '../mockReps'
import { Timeline } from './Timeline'
import { RepCard } from './RepCard'
import './ResultsView.css'

interface ResultsViewProps {
  response: AnalysisResponse
  video: File
}

export function ResultsView({ response, video }: ResultsViewProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [durationSec, setDurationSec] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [playbackError, setPlaybackError] = useState(false)

  const videoUrl = useMemo(() => URL.createObjectURL(video), [video])
  useEffect(() => {
    return () => URL.revokeObjectURL(videoUrl)
  }, [videoUrl])

  const reps = useMemo(() => getReps(response, durationSec), [response, durationSec])

  const handleSeek = (seconds: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = seconds
    }
    setCurrentTime(seconds)
  }

  return (
    <div className="results">
      <video
        ref={videoRef}
        src={videoUrl}
        controls
        data-testid="results-video"
        className="results__video"
        onLoadedMetadata={(event) => setDurationSec(event.currentTarget.duration)}
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        onError={() => setPlaybackError(true)}
      />
      {playbackError && (
        <p className="error">
          This browser can't play this video for preview — your results below are still valid.
        </p>
      )}

      {reps.length > 0 && (
        <>
          <Timeline reps={reps} durationSec={durationSec} currentTime={currentTime} onSeek={handleSeek} />
          <div className="results__reps">
            {reps.map((rep) => (
              <RepCard
                key={rep.rep_index}
                rep={rep}
                active={currentTime >= rep.start_sec && currentTime < rep.end_sec}
                onSeek={handleSeek}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Write `ResultsView.css`**

```css
/* frontend/src/components/ResultsView.css */
.results__video {
  width: 100%;
  border-radius: 8px;
  margin-bottom: 16px;
  background: black;
}

.results__reps {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
```

- [ ] **Step 3: Verify it type-checks**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ResultsView.tsx frontend/src/components/ResultsView.css
git commit -m "feat: add ResultsView component"
```

---

## Task 8: Rewire `App.tsx`, trim `App.css`, extend integration test

**Files:**
- Modify: `frontend/src/App.tsx` (full rewrite)
- Modify: `frontend/src/App.css` (trimmed)
- Modify: `frontend/src/App.test.tsx` (extended)
- Modify: `frontend/src/test/setup.ts` (add `URL.createObjectURL` polyfill)

**Interfaces:**
- Consumes: `UploadForm` (Task 5), `AnalyzingView` (Task 6), `ResultsView`
  (Task 7), `analyzeVideo`/`checkHealth` (existing, unchanged, from
  `frontend/src/api.ts`), `AnalysisResponse`/`Exercise` (existing, from
  `frontend/src/types.ts`).
- Produces: nothing further consumed — this is the top-level component.

- [ ] **Step 1: Extend the failing integration test**

Replace `frontend/src/App.test.tsx` with:

```tsx
// frontend/src/App.test.tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const mockAnalysisResponse = { exercise: 'squat', frame_count: 100, reps: [] }

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => mockAnalysisResponse }),
  )
})

describe('App', () => {
  it('renders the heading and reports backend health', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'FormIQ' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/Backend: online/)).toBeInTheDocument())
  })

  it('disables submit until a video is selected', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: /analyze/i })).toBeDisabled()
  })

  it('walks from idle through analyzing to results with mock rep cards', async () => {
    render(<App />)
    await waitFor(() => expect(screen.getByText(/Backend: online/)).toBeInTheDocument())

    const file = new File(['fake video content'], 'clip.mp4', { type: 'video/mp4' })
    const input = screen.getByLabelText(/drop a video/i)
    fireEvent.change(input, { target: { files: [file] } })

    fireEvent.click(screen.getByRole('button', { name: /analyze/i }))

    expect(await screen.findByText(/Analyzing your squat set/i)).toBeInTheDocument()

    const video = await screen.findByTestId('results-video')
    Object.defineProperty(video, 'duration', { configurable: true, value: 12 })
    fireEvent.loadedMetadata(video)

    expect((await screen.findAllByText(/^Rep \d/)).length).toBeGreaterThan(0)
  })
})
```

- [ ] **Step 2: Add the `URL.createObjectURL` test polyfill**

jsdom (Vitest's test environment) doesn't implement `URL.createObjectURL`/
`URL.revokeObjectURL` — `ResultsView` (Task 7) calls these, so any test
that reaches the results view needs them stubbed. Add to
`frontend/src/test/setup.ts`:

```ts
// frontend/src/test/setup.ts
import '@testing-library/jest-dom/vitest'

if (!URL.createObjectURL) {
  URL.createObjectURL = () => 'blob:mock-url'
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = () => {}
}
```

- [ ] **Step 3: Run the test suite to verify it fails**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: FAIL — `App.tsx` doesn't render `UploadForm`/`AnalyzingView`/
`ResultsView` yet, so the third test can't find the expected text/elements.

- [ ] **Step 4: Rewrite `App.tsx`**

```tsx
// frontend/src/App.tsx
import { useEffect, useState } from 'react'
import { analyzeVideo, checkHealth } from './api'
import type { AnalysisResponse, Exercise } from './types'
import { UploadForm } from './components/UploadForm'
import { AnalyzingView } from './components/AnalyzingView'
import { ResultsView } from './components/ResultsView'
import './App.css'

type Status = 'idle' | 'analyzing' | 'results'

function App() {
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [exercise, setExercise] = useState<Exercise | null>(null)
  const [video, setVideo] = useState<File | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    checkHealth()
      .then(setBackendHealthy)
      .catch(() => setBackendHealthy(false))
  }, [])

  const handleSubmit = async (selectedExercise: Exercise, selectedVideo: File) => {
    setExercise(selectedExercise)
    setVideo(selectedVideo)
    setStatus('analyzing')
    setError(null)
    try {
      const response = await analyzeVideo(selectedExercise, selectedVideo)
      setResult(response)
      setStatus('results')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setStatus('idle')
    }
  }

  return (
    <main className="app">
      <h1>FormIQ</h1>
      <p className="status">
        Backend: {backendHealthy === null ? 'checking…' : backendHealthy ? 'online' : 'offline'}
      </p>

      {status === 'idle' && <UploadForm onSubmit={handleSubmit} />}
      {status === 'analyzing' && exercise && <AnalyzingView exercise={exercise} />}
      {status === 'results' && result && video && <ResultsView response={result} video={video} />}

      {error && <p className="error">{error}</p>}
    </main>
  )
}

export default App
```

- [ ] **Step 5: Trim `App.css`**

```css
/* frontend/src/App.css */
.app {
  max-width: 720px;
  margin: 0 auto;
  padding: 32px 16px;
}

.status {
  color: var(--text-muted);
  font-size: 13px;
  margin-bottom: 24px;
}

.error {
  color: var(--danger);
  margin-top: 16px;
  font-size: 14px;
}
```

- [ ] **Step 6: Run the test suite to verify it passes**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: PASS, 3/3 tests. If the third test's `findAllByText(/^Rep \d/)`
comes back empty, check that `fireEvent.loadedMetadata(video)` actually
fired after `Object.defineProperty(video, 'duration', ...)` — React's
`onLoadedMetadata` reads `event.currentTarget.duration`, so the property
must be set before the event fires, not after.

- [ ] **Step 7: Run the full frontend test suite**

Run: `cd frontend && npm test`
Expected: all test files pass (`App.test.tsx`, `mockReps.test.ts`,
`components/Timeline.test.tsx`, `components/RepCard.test.tsx`).

- [ ] **Step 8: Run the type checker and linter**

Run: `cd frontend && npx tsc -b --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.css frontend/src/App.test.tsx \
        frontend/src/test/setup.ts
git commit -m "feat: rewire App to idle/analyzing/results state machine"
```

---

## Post-plan state

After Task 8, the frontend shows a real upload form (exercise pills,
dropzone, energetic/dark styling), a real analyzing spinner, and a real
results view with actual video playback, a color-coded rep timeline, and
per-rep cards — all driven by the backend's real response when `reps` is
populated, and by deterministic mock data (invisible to every component
except `mockReps.ts`) when it isn't. The moment backend rep-segmentation
ships real `reps`, this frontend needs zero changes beyond deleting
`mockReps.ts`/`mockReps.test.ts` and removing the one `getReps()` call
site in `ResultsView.tsx` (replaced with `response.reps` directly).
