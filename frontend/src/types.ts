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
