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
