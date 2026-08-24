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
