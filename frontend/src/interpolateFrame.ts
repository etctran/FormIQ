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
