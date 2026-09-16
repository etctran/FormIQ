import { useCallback, useEffect, useState } from 'react'
import { API_BASE_URL, deleteHistoryEntry, getHistory } from '../api'
import type { HistoryEntry } from '../types'
import { ManualEntryForm } from './ManualEntryForm'
import './HistoryView.css'

function formatEntry(entry: HistoryEntry): string {
  if (entry.source === 'manual') {
    const setsReps = `${entry.sets} × ${entry.reps}`
    return entry.weight != null ? `${setsReps} @ ${entry.weight}` : setsReps
  }
  if (entry.rep_count === null || entry.rep_count === 0) {
    return 'rep scoring not yet available'
  }
  const accuracy =
    entry.avg_form_accuracy != null ? `${Math.round(entry.avg_form_accuracy * 100)}%` : null
  return accuracy ? `${entry.rep_count} reps · ${accuracy} avg form` : `${entry.rep_count} reps`
}

export function HistoryView() {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)

  const refetch = useCallback(() => {
    getHistory()
      .then(setEntries)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load history'))
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  const handleDelete = async (id: number) => {
    setError(null)
    try {
      await deleteHistoryEntry(id)
      setEntries((prev) => (prev ? prev.filter((entry) => entry.id !== id) : prev))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete entry')
    }
  }

  const handleCreated = (entry: HistoryEntry) => {
    setError(null)
    setEntries((prev) => (prev ? [entry, ...prev] : [entry]))
  }

  const handleUpdated = (updated: HistoryEntry) => {
    setError(null)
    setEditingId(null)
    setEntries((prev) => (prev ? prev.map((e) => (e.id === updated.id ? updated : e)) : prev))
  }

  return (
    <div className="history-view">
      {editingId === null && <ManualEntryForm onSaved={handleCreated} />}
      <a
        className="history-view__export"
        href={`${API_BASE_URL}/history/export`}
        download="workout_history.csv"
      >
        Export CSV
      </a>

      {error && <p className="error">{error}</p>}
      {entries === null && !error && <p className="history-view__loading">Loading history…</p>}
      {entries !== null && entries.length === 0 && (
        <p className="history-view__empty">No workouts logged yet.</p>
      )}
      {entries !== null && entries.length > 0 && (
        <ul className="history-view__list">
          {entries.map((entry) =>
            editingId === entry.id ? (
              <li key={entry.id} className="history-view__row history-view__row--editing">
                <ManualEntryForm
                  entry={entry}
                  onSaved={handleUpdated}
                  onCancel={() => setEditingId(null)}
                />
              </li>
            ) : (
              <li key={entry.id} className="history-view__row">
                <span className="history-view__date">{entry.date}</span>
                <span className="history-view__exercise">{entry.exercise.replace('_', ' ')}</span>
                <span className="history-view__detail">
                  {formatEntry(entry)}
                  {entry.source === 'manual' && entry.notes && ` — ${entry.notes}`}
                </span>
                <span className="history-view__source">{entry.source}</span>
                {entry.source === 'manual' && (
                  <button
                    type="button"
                    className="history-view__edit"
                    onClick={() => setEditingId(entry.id)}
                    aria-label={`Edit entry from ${entry.date}`}
                  >
                    edit
                  </button>
                )}
                <button
                  type="button"
                  className="history-view__delete"
                  onClick={() => handleDelete(entry.id)}
                  aria-label={`Delete entry from ${entry.date}`}
                >
                  ×
                </button>
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  )
}
