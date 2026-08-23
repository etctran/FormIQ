import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Timeline } from './Timeline'
import type { RepScore } from '../types'

const reps: RepScore[] = [
  { rep_index: 0, start_sec: 0, end_sec: 5, form_accuracy: 0.9, faults: [] },
  { rep_index: 1, start_sec: 5, end_sec: 10, form_accuracy: 0.7, faults: ['Knee valgus'] },
]

describe('Timeline', () => {
  it('renders one segment per rep', () => {
    render(<Timeline reps={reps} durationSec={10} currentTime={0} onSeek={vi.fn()} />)
    expect(screen.getAllByRole('button')).toHaveLength(2)
  })

  it('calls onSeek with the rep start time when a segment is clicked', () => {
    const onSeek = vi.fn()
    render(<Timeline reps={reps} durationSec={10} currentTime={0} onSeek={onSeek} />)
    fireEvent.click(screen.getByLabelText(/Rep 2/))
    expect(onSeek).toHaveBeenCalledWith(5)
  })

  it('marks the segment containing currentTime as active', () => {
    render(<Timeline reps={reps} durationSec={10} currentTime={6} onSeek={vi.fn()} />)
    expect(screen.getByLabelText(/Rep 2/)).toHaveClass('timeline-segment--active')
    expect(screen.getByLabelText(/Rep 1/)).not.toHaveClass('timeline-segment--active')
  })
})
