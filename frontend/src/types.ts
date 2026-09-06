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

export interface HistoryEntry {
  id: number
  exercise: Exercise
  date: string
  source: 'manual' | 'video'
  created_at: string
  sets: number | null
  reps: number | null
  weight: number | null
  notes: string | null
  rep_count: number | null
  avg_form_accuracy: number | null
  rep_scores: RepScore[] | null
}

export interface ManualEntryCreate {
  exercise: Exercise
  date: string
  sets: number
  reps: number
  weight?: number | null
  notes?: string | null
}
