import type {
  AnalysisResponse,
  Exercise,
  HistoryEntry,
  ManualEntryCreate,
  ManualEntryUpdate,
} from './types'

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

export async function getHistory(): Promise<HistoryEntry[]> {
  const response = await fetch(`${API_BASE_URL}/history`)
  if (!response.ok) {
    throw new Error(`Failed to load history: ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as HistoryEntry[]
}

export async function createHistoryEntry(data: ManualEntryCreate): Promise<HistoryEntry> {
  const response = await fetch(`${API_BASE_URL}/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error(`Failed to save entry: ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as HistoryEntry
}

export async function updateHistoryEntry(
  id: number,
  data: ManualEntryUpdate,
): Promise<HistoryEntry> {
  const response = await fetch(`${API_BASE_URL}/history/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error(`Failed to update entry: ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as HistoryEntry
}

export async function deleteHistoryEntry(id: number): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/history/${id}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Failed to delete entry: ${response.status} ${response.statusText}`)
  }
}
