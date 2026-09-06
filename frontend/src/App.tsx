import { useEffect, useState } from 'react'
import { analyzeVideo, checkHealth } from './api'
import type { AnalysisResponse, Exercise } from './types'
import { UploadForm } from './components/UploadForm'
import { AnalyzingView } from './components/AnalyzingView'
import { ResultsView } from './components/ResultsView'
import { HistoryView } from './components/HistoryView'
import './App.css'

type Status = 'idle' | 'analyzing' | 'results' | 'history'

function App() {
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [exercise, setExercise] = useState<Exercise | null>(null)
  const [video, setVideo] = useState<File | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    checkHealth()
      .then(setBackendHealthy)
      .catch(() => setBackendHealthy(false))
  }, [])

  const handleSubmit = async (selectedExercise: Exercise, selectedVideo: File) => {
    setExercise(selectedExercise)
    setVideo(selectedVideo)
    setStatus('analyzing')
    setError(null)
    try {
      const response = await analyzeVideo(selectedExercise, selectedVideo)
      setResult(response)
      setStatus('results')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setStatus('idle')
      setResult(null)
      setVideo(null)
    }
  }

  const handleReset = () => {
    setStatus('idle')
    setResult(null)
    setVideo(null)
    setExercise(null)
    setError(null)
  }

  return (
    <main className="app">
      <h1>FormIQ</h1>
      <nav className="app__nav">
        <button
          type="button"
          className={`app__nav-link ${status !== 'history' ? 'app__nav-link--active' : ''}`.trim()}
          onClick={handleReset}
        >
          New Analysis
        </button>
        <button
          type="button"
          className={`app__nav-link ${status === 'history' ? 'app__nav-link--active' : ''}`.trim()}
          onClick={() => setStatus('history')}
        >
          History
        </button>
      </nav>
      <p className="status">
        Backend: {backendHealthy === null ? 'checking…' : backendHealthy ? 'online' : 'offline'}
      </p>

      {status === 'idle' && <UploadForm onSubmit={handleSubmit} />}
      {status === 'analyzing' && exercise && <AnalyzingView exercise={exercise} />}
      {status === 'results' && result && video && (
        <ResultsView response={result} video={video} onReset={handleReset} />
      )}
      {status === 'history' && <HistoryView />}

      {error && <p className="error">{error}</p>}
    </main>
  )
}

export default App
