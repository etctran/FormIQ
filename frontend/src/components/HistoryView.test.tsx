import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HistoryView } from './HistoryView'
import type { HistoryEntry } from '../types'

const manualEntry: HistoryEntry = {
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

const videoEntry: HistoryEntry = {
  id: 2,
  exercise: 'pushup',
  date: '2026-09-02',
  source: 'video',
  created_at: '2026-09-02T12:00:00Z',
  sets: null,
  reps: null,
  weight: null,
  notes: null,
  rep_count: 5,
  avg_form_accuracy: 0.85,
  rep_scores: [],
}

const manualEntryWithNotes: HistoryEntry = {
  ...manualEntry,
  id: 3,
  notes: 'felt strong today',
}

const zeroRepVideoEntry: HistoryEntry = {
  ...videoEntry,
  id: 4,
  rep_count: 0,
  avg_form_accuracy: null,
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => [manualEntry, videoEntry] }),
  )
})

describe('HistoryView', () => {
  it('renders fetched manual and video entries with formatted detail', async () => {
    render(<HistoryView />)

    await waitFor(() => expect(screen.getByText('3 × 8 @ 100')).toBeInTheDocument())
    expect(screen.getByText('5 reps · 85% avg form')).toBeInTheDocument()
  })

  it('renders notes for a manual entry that has them', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => [manualEntryWithNotes] }),
    )
    render(<HistoryView />)
    await waitFor(() => expect(screen.getByText(/3 × 8 @ 100/)).toBeInTheDocument())
    expect(screen.getByText(/felt strong today/)).toBeInTheDocument()
  })

  it('does not render a dangling separator for a manual entry without notes', async () => {
    render(<HistoryView />)
    await waitFor(() => expect(screen.getByText('3 × 8 @ 100')).toBeInTheDocument())
    expect(screen.queryByText(/—/)).not.toBeInTheDocument()
  })

  it('describes a zero-rep video entry as scoring-not-yet-available rather than a detection failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => [zeroRepVideoEntry] }),
    )
    render(<HistoryView />)
    await waitFor(() =>
      expect(screen.getByText(/rep scoring not yet available/i)).toBeInTheDocument(),
    )
  })

  it('shows an empty message when there are no entries', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
    render(<HistoryView />)
    await waitFor(() => expect(screen.getByText(/no workouts logged yet/i)).toBeInTheDocument())
  })

  it('removes an entry from the list when its delete button is clicked', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [manualEntry, videoEntry] })
      .mockResolvedValueOnce({ ok: true })
    vi.stubGlobal('fetch', fetchMock)

    render(<HistoryView />)
    await waitFor(() => expect(screen.getByText('3 × 8 @ 100')).toBeInTheDocument())

    fireEvent.click(screen.getByLabelText('Delete entry from 2026-09-01'))

    await waitFor(() => expect(screen.queryByText('3 × 8 @ 100')).not.toBeInTheDocument())
  })

  it('shows an error and keeps the row when deleting an entry fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [manualEntry, videoEntry] })
      .mockResolvedValueOnce({ ok: false, status: 500, statusText: 'Internal Server Error' })
    vi.stubGlobal('fetch', fetchMock)

    render(<HistoryView />)
    await waitFor(() => expect(screen.getByText('3 × 8 @ 100')).toBeInTheDocument())

    fireEvent.click(screen.getByLabelText('Delete entry from 2026-09-01'))

    await waitFor(() => expect(screen.getByText(/failed to delete entry/i)).toBeInTheDocument())
    expect(screen.getByText('3 × 8 @ 100')).toBeInTheDocument()
  })
})
