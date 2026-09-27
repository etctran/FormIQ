import type {
  AnalysisResponse,
  Exercise,
  HistoryEntry,
  ManualEntryCreate,
  ManualEntryUpdate,
} from './types'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/** Every request goes through here so the deployed instance's shared
 * secret (VITE_API_KEY, unset in local dev) is attached in exactly one
 * place. See backend/app/security.py. */
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const key = import.meta.env.VITE_API_KEY
  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { ...init.headers, ...(key ? { 'X-API-Key': key } : {}) },
  })
}

export async function checkHealth(): Promise<boolean> {
  const response = await apiFetch('/health')
  return response.ok
}

export async function analyzeVideo(exercise: Exercise, video: File): Promise<AnalysisResponse> {
  const formData = new FormData()
  formData.append('video', video)

  const response = await apiFetch(`/analyze/${exercise}`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error(`Analysis failed: ${response.status} ${response.statusText}`)
  }

  return (await response.json()) as AnalysisResponse
}

export async function getHistory(): Promise<HistoryEntry[]> {
  const response = await apiFetch('/history')
  if (!response.ok) {
    throw new Error(`Failed to load history: ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as HistoryEntry[]
}

export async function createHistoryEntry(data: ManualEntryCreate): Promise<HistoryEntry> {
  const response = await apiFetch('/history', {
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
  const response = await apiFetch(`/history/${id}`, {
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
  const response = await apiFetch(`/history/${id}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Failed to delete entry: ${response.status} ${response.statusText}`)
  }
}

/** The export used to be a plain <a href>, which can't carry the API-key
 * header. Fetch it and hand the browser a blob instead. */
export async function downloadExport(format: 'csv' | 'json' = 'csv'): Promise<void> {
  const response = await apiFetch(`/history/export?format=${format}`)
  if (!response.ok) {
    throw new Error(`Failed to export history: ${response.status} ${response.statusText}`)
  }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = `formiq-history.${format}`
  link.click()
  URL.revokeObjectURL(url)
}
