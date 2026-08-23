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
