import { useEffect, useMemo, useRef, useState } from 'react'
import type { AnalysisResponse } from '../types'
import { getReps } from '../mockReps'
import { Timeline } from './Timeline'
import { RepCard } from './RepCard'
import './ResultsView.css'

interface ResultsViewProps {
  response: AnalysisResponse
  video: File
  onReset: () => void
}

export function ResultsView({ response, video, onReset }: ResultsViewProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [durationSec, setDurationSec] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [playbackError, setPlaybackError] = useState(false)

  const [videoUrl, setVideoUrl] = useState('')
  // Tracks the URL that has actually been committed into `videoUrl`
  // state (and therefore rendered into the <video> element's `src`) by
  // the effect below. This is what lets the create-effect's cleanup
  // tell "this URL was superseded before it was ever committed" (React
  // Strict Mode's dev-only synthetic mount -> cleanup -> mount cycle
  // discards the first URL before it's ever rendered) apart from "this
  // URL WAS committed and may still be live in the DOM" (an ordinary
  // `video` prop change) -- only the former is ever safe to revoke here.
  const committedUrlRef = useRef<string | null>(null)

  // Effect 1: allocate a fresh object URL whenever the `video` File
  // changes. Deliberately does NOT unconditionally revoke its own URL
  // in cleanup -- see Effect 2 for why that would race the DOM.
  useEffect(() => {
    const url = URL.createObjectURL(video)
    setVideoUrl(url)
    return () => {
      if (committedUrlRef.current !== url) {
        // Never made it into state/the DOM (e.g. Strict Mode's
        // synthetic remount discarded it before this render ever
        // committed) -- nothing else will ever revoke it, and it's
        // safe to do so now since the DOM never referenced it.
        URL.revokeObjectURL(url)
      }
      // Otherwise this URL IS (or was) the committed one -- Effect 2
      // owns revoking it, and only does so once a *later* commit has
      // already moved the DOM's `src` past it.
    }
  }, [video])

  // Effect 2: runs only once `videoUrl` state -- and therefore the
  // <video>'s `src` in the DOM -- has actually committed a given URL
  // (effects that depend on a piece of state only ever run after a
  // commit that reflects that state's new value). Its cleanup fires
  // when `videoUrl` changes again (i.e. the DOM has already committed a
  // *newer* URL by the time this runs) or on unmount, so it can never
  // revoke a URL while the DOM is still pointing at it.
  useEffect(() => {
    if (!videoUrl) return
    committedUrlRef.current = videoUrl
    return () => URL.revokeObjectURL(videoUrl)
  }, [videoUrl])

  // If real video metadata never loads (playback error), fall back to an
  // estimated duration derived from frame_count at the project's standard
  // 30fps sampling rate, so getReps still has something to lay reps out
  // against instead of silently rendering nothing.
  const fallbackDurationSec = response.frame_count > 0 ? response.frame_count / 30 : 0
  const effectiveDurationSec =
    durationSec > 0 ? durationSec : playbackError ? fallbackDurationSec : 0

  const reps = useMemo(
    () => getReps(response, effectiveDurationSec),
    [response, effectiveDurationSec],
  )

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
        src={videoUrl || undefined}
        controls
        data-testid="results-video"
        className="results__video"
        onLoadedMetadata={(event) => {
          const value = event.currentTarget.duration
          setDurationSec(Number.isFinite(value) ? value : 0)
        }}
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        onError={() => setPlaybackError(true)}
      />
      {playbackError && (
        <p className="error">
          {reps.length > 0
            ? "This browser can't play this video for preview — your results below are still valid."
            : "This browser can't play this video for preview."}
        </p>
      )}

      <button type="button" className="results__reset" onClick={onReset}>
        Analyze another video
      </button>

      {reps.length > 0 && (
        <>
          <Timeline
            reps={reps}
            durationSec={effectiveDurationSec}
            currentTime={currentTime}
            onSeek={handleSeek}
          />
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
