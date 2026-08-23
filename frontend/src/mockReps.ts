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
