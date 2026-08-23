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
