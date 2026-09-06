import { useCallback, useEffect, useState } from 'react'
import { deleteHistoryEntry, getHistory } from '../api'
import type { HistoryEntry } from '../types'
import { ManualEntryForm } from './ManualEntryForm'
import './HistoryView.css'

function formatEntry(entry: HistoryEntry): string {
  if (entry.source === 'manual') {
    const setsReps = `${entry.sets} × ${entry.reps}`
    return entry.weight != null ? `${setsReps} @ ${entry.weight}` : setsReps
  }
  if (entry.rep_count === null || entry.rep_count === 0) {
    return 'no reps detected'
  }
  const accuracy =
    entry.avg_form_accuracy != null ? `${Math.round(entry.avg_form_accuracy * 100)}%` : null
  return accuracy ? `${entry.rep_count} reps · ${accuracy} avg form` : `${entry.rep_count} reps`
}

export function HistoryView() {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(() => {
    getHistory()
      .then(setEntries)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load history'))
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  const handleDelete = async (id: number) => {
    try {
      await deleteHistoryEntry(id)
      setEntries((prev) => (prev ? prev.filter((entry) => entry.id !== id) : prev))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete entry')
    }
  }

  const handleCreated = (entry: HistoryEntry) => {
    setEntries((prev) => (prev ? [entry, ...prev] : [entry]))
  }

  return (
    <div className="history-view">
      <ManualEntryForm onCreated={handleCreated} />

      {error && <p className="error">{error}</p>}
      {entries === null && !error && <p className="history-view__loading">Loading history…</p>}
      {entries !== null && entries.length === 0 && (
        <p className="history-view__empty">No workouts logged yet.</p>
      )}
      {entries !== null && entries.length > 0 && (
        <ul className="history-view__list">
          {entries.map((entry) => (
            <li key={entry.id} className="history-view__row">
              <span className="history-view__date">{entry.date}</span>
              <span className="history-view__exercise">{entry.exercise.replace('_', ' ')}</span>
              <span className="history-view__detail">{formatEntry(entry)}</span>
              <span className="history-view__source">{entry.source}</span>
              <button
                type="button"
                className="history-view__delete"
                onClick={() => handleDelete(entry.id)}
                aria-label={`Delete entry from ${entry.date}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
