import { useState } from 'react'
import type { FormEvent } from 'react'
import { createHistoryEntry, updateHistoryEntry } from '../api'
import { EXERCISES } from '../types'
import type { Exercise, HistoryEntry } from '../types'
import './ManualEntryForm.css'

interface ManualEntryFormProps {
  entry?: HistoryEntry
  onSaved: (entry: HistoryEntry) => void
  onCancel?: () => void
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

export function ManualEntryForm({ entry, onSaved, onCancel }: ManualEntryFormProps) {
  const isEditing = entry != null
  const [exercise, setExercise] = useState<Exercise>(entry?.exercise ?? EXERCISES[0])
  const [date, setDate] = useState(entry?.date ?? today())
  const [sets, setSets] = useState(String(entry?.sets ?? 3))
  const [reps, setReps] = useState(String(entry?.reps ?? 8))
  const [weight, setWeight] = useState(entry?.weight != null ? String(entry.weight) : '')
  const [notes, setNotes] = useState(entry?.notes ?? '')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const payload = {
      exercise,
      date,
      sets: Number(sets),
      reps: Number(reps),
      weight: weight === '' ? null : Number(weight),
      notes: notes === '' ? null : notes,
    }
    try {
      const saved = isEditing
        ? await updateHistoryEntry(entry.id, payload)
        : await createHistoryEntry(payload)
      onSaved(saved)
      if (!isEditing) {
        setWeight('')
        setNotes('')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save entry')
    }
  }

  return (
    <form onSubmit={handleSubmit} className="manual-entry-form">
      <div className="manual-entry-form__label">{isEditing ? 'Edit workout' : 'Log a workout'}</div>

      <select
        aria-label="Exercise"
        value={exercise}
        onChange={(event) => setExercise(event.target.value as Exercise)}
      >
        {EXERCISES.map((option) => (
          <option key={option} value={option}>
            {option.replace('_', ' ')}
          </option>
        ))}
      </select>

      <input
        aria-label="Date"
        type="date"
        value={date}
        onChange={(event) => setDate(event.target.value)}
      />
      <input
        aria-label="Sets"
        type="number"
        min={1}
        value={sets}
        onChange={(event) => setSets(event.target.value)}
      />
      <input
        aria-label="Reps"
        type="number"
        min={1}
        value={reps}
        onChange={(event) => setReps(event.target.value)}
      />
      <input
        aria-label="Weight"
        type="number"
        placeholder="Weight (optional)"
        value={weight}
        onChange={(event) => setWeight(event.target.value)}
      />
      <input
        aria-label="Notes"
        type="text"
        placeholder="Notes (optional)"
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
      />

      <button type="submit" className="manual-entry-form__submit">
        {isEditing ? 'Save' : 'Add entry'}
      </button>
      {isEditing && onCancel && (
        <button type="button" className="manual-entry-form__cancel" onClick={onCancel}>
          Cancel
        </button>
      )}
      {error && <p className="error">{error}</p>}
    </form>
  )
}
