import { describe, expect, it, vi } from 'vitest'
import { createHistoryEntry, deleteHistoryEntry, getHistory, updateHistoryEntry } from './api'
import type { HistoryEntry, ManualEntryCreate } from './types'

const sampleEntry: HistoryEntry = {
  id: 1,
  exercise: 'squat',
  date: '2026-09-01',
  source: 'manual',
  created_at: '2026-09-01T12:00:00Z',
  sets: 3,
  reps: 8,
  weight: 100,
  notes: null,
  rep_count: null,
  avg_form_accuracy: null,
  rep_scores: null,
}

describe('getHistory', () => {
  it('returns parsed history entries on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => [sampleEntry] }),
    )
    const entries = await getHistory()
    expect(entries).toEqual([sampleEntry])
  })

  it('throws when the response is not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500, statusText: 'Server Error' }),
    )
    await expect(getHistory()).rejects.toThrow('Failed to load history')
  })
})

describe('createHistoryEntry', () => {
  it('posts the payload and returns the created entry', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => sampleEntry })
    vi.stubGlobal('fetch', fetchMock)

    const payload: ManualEntryCreate = { exercise: 'squat', date: '2026-09-01', sets: 3, reps: 8 }
    const result = await createHistoryEntry(payload)

    expect(result).toEqual(sampleEntry)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/history'),
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
  })

  it('throws when the response is not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 422, statusText: 'Unprocessable Entity' }),
    )
    await expect(
      createHistoryEntry({ exercise: 'squat', date: '2026-09-01', sets: 3, reps: 8 }),
    ).rejects.toThrow('Failed to save entry')
  })
})

describe('updateHistoryEntry', () => {
  it('sends a PATCH with only the provided fields', async () => {
    const updated = { ...sampleEntry, sets: 5 }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => updated })
    vi.stubGlobal('fetch', fetchMock)

    const result = await updateHistoryEntry(1, { sets: 5 })

    expect(result).toEqual(updated)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/history/1'),
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ sets: 5 }) }),
    )
  })

  it('throws when the response is not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 400, statusText: 'Bad Request' }),
    )
    await expect(updateHistoryEntry(1, { sets: 5 })).rejects.toThrow('Failed to update entry')
  })
})

describe('deleteHistoryEntry', () => {
  it('sends a DELETE request', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)

    await deleteHistoryEntry(1)

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/history/1'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('throws when the response is not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 404, statusText: 'Not Found' }),
    )
    await expect(deleteHistoryEntry(999)).rejects.toThrow('Failed to delete entry')
  })
})
