import { useEffect, useState } from 'react'
import { analyzeVideo, checkHealth } from './api'
import { EXERCISES } from './types'
import type { AnalysisResponse, Exercise } from './types'
import './App.css'

function App() {
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null)
  const [exercise, setExercise] = useState<Exercise>(EXERCISES[0])
  const [video, setVideo] = useState<File | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    checkHealth()
      .then(setBackendHealthy)
      .catch(() => setBackendHealthy(false))
  }, [])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!video) return

    setSubmitting(true)
    setError(null)
    setResult(null)
    try {
      setResult(await analyzeVideo(exercise, video))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="app">
      <h1>FormIQ</h1>
      <p className="status">
        Backend:{' '}
        {backendHealthy === null ? 'checking…' : backendHealthy ? 'online' : 'offline'}
      </p>

      <form onSubmit={handleSubmit}>
        <label htmlFor="exercise">Exercise</label>
        <select
          id="exercise"
          value={exercise}
          onChange={(event) => setExercise(event.target.value as Exercise)}
        >
          {EXERCISES.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>

        <label htmlFor="video">Video</label>
        <input
          id="video"
          type="file"
          accept="video/*"
          onChange={(event) => setVideo(event.target.files?.[0] ?? null)}
        />

        <button type="submit" disabled={!video || submitting}>
          {submitting ? 'Analyzing…' : 'Analyze'}
        </button>
      </form>

      {error && <p className="error">{error}</p>}
      {result && <pre className="result">{JSON.stringify(result, null, 2)}</pre>}
    </main>
  )
}

export default App
