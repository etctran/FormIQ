import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ManualEntryForm } from './ManualEntryForm'
import type { HistoryEntry } from '../types'

const createdEntry: HistoryEntry = {
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

describe('ManualEntryForm', () => {
  it('submits the form values and calls onSaved with the new entry', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => createdEntry })
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(<ManualEntryForm onSaved={onSaved} />)

    fireEvent.change(screen.getByLabelText('Sets'), { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('Reps'), { target: { value: '8' } })
    fireEvent.change(screen.getByLabelText('Weight'), { target: { value: '100' } })
    fireEvent.click(screen.getByRole('button', { name: /add entry/i }))

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(createdEntry))

    const [, requestInit] = fetchMock.mock.calls[0]
    const body = JSON.parse(requestInit.body as string)
    expect(body).toMatchObject({ sets: 3, reps: 8, weight: 100 })
  })

  it('shows an error message when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 422, statusText: 'Unprocessable Entity' }),
    )
    render(<ManualEntryForm onSaved={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /add entry/i }))

    await waitFor(() => expect(screen.getByText(/failed to save entry/i)).toBeInTheDocument())
  })
})

describe('ManualEntryForm in edit mode', () => {
  const existingEntry: HistoryEntry = {
    id: 7,
    exercise: 'row',
    date: '2026-09-01',
    source: 'manual',
    created_at: '2026-09-01T12:00:00Z',
    sets: 4,
    reps: 10,
    weight: 50,
    notes: 'existing note',
    rep_count: null,
    avg_form_accuracy: null,
    rep_scores: null,
  }

  it('pre-fills fields from the given entry and calls updateHistoryEntry on submit', async () => {
    const updated = { ...existingEntry, sets: 6 }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => updated })
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(<ManualEntryForm entry={existingEntry} onSaved={onSaved} />)

    expect(screen.getByLabelText('Sets')).toHaveValue(4)
    expect(screen.getByLabelText('Notes')).toHaveValue('existing note')

    fireEvent.change(screen.getByLabelText('Sets'), { target: { value: '6' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(updated))
    const [url, requestInit] = fetchMock.mock.calls[0]
    expect(url).toContain('/history/7')
    expect(requestInit.method).toBe('PATCH')
  })

  it('calls onCancel when the cancel button is clicked, without submitting', () => {
    const onCancel = vi.fn()
    render(<ManualEntryForm entry={existingEntry} onSaved={vi.fn()} onCancel={onCancel} />)

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    expect(onCancel).toHaveBeenCalled()
  })
})
