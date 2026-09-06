import { useState } from 'react'
import type { FormEvent } from 'react'
import { createHistoryEntry } from '../api'
import { EXERCISES } from '../types'
import type { Exercise, HistoryEntry } from '../types'
import './ManualEntryForm.css'

interface ManualEntryFormProps {
  onCreated: (entry: HistoryEntry) => void
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

export function ManualEntryForm({ onCreated }: ManualEntryFormProps) {
  const [exercise, setExercise] = useState<Exercise>(EXERCISES[0])
  const [date, setDate] = useState(today())
  const [sets, setSets] = useState('3')
  const [reps, setReps] = useState('8')
  const [weight, setWeight] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      const entry = await createHistoryEntry({
        exercise,
        date,
        sets: Number(sets),
        reps: Number(reps),
        weight: weight === '' ? null : Number(weight),
        notes: notes === '' ? null : notes,
      })
      onCreated(entry)
      setWeight('')
      setNotes('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save entry')
    }
  }

  return (
    <form onSubmit={handleSubmit} className="manual-entry-form">
      <div className="manual-entry-form__label">Log a workout</div>

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
        Add entry
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  )
}
