import type { AnalysisResponse, Exercise } from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function checkHealth(): Promise<boolean> {
  const response = await fetch(`${API_BASE_URL}/health`)
  return response.ok
}

export async function analyzeVideo(exercise: Exercise, video: File): Promise<AnalysisResponse> {
  const formData = new FormData()
  formData.append('video', video)

  const response = await fetch(`${API_BASE_URL}/analyze/${exercise}`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error(`Analysis failed: ${response.status} ${response.statusText}`)
  }

  return (await response.json()) as AnalysisResponse
}
