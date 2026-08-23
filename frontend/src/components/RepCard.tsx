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
