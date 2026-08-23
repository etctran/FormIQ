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
        // Absolute (not flex-contiguous) so gaps between reps — rest
        // periods, once real rep-segmentation ships — render as actual
        // gaps at the correct point on the timeline, rather than every
        // segment after a gap rendering earlier than the video moment it
        // actually corresponds to.
        const leftPct = durationSec > 0 ? (rep.start_sec / durationSec) * 100 : 0
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
            style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
            onClick={() => onSeek(rep.start_sec)}
            aria-label={`Rep ${rep.rep_index + 1}, ${Math.round(rep.form_accuracy * 100)}%`}
          />
        )
      })}
    </div>
  )
}
