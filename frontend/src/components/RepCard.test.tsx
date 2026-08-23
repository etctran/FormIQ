import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RepCard } from './RepCard'
import type { RepScore } from '../types'

const rep: RepScore = {
  rep_index: 1,
  start_sec: 4,
  end_sec: 8,
  form_accuracy: 0.78,
  faults: ['Knee valgus'],
}

describe('RepCard', () => {
  it('renders the rep number, accuracy, and fault tags', () => {
    render(<RepCard rep={rep} active={false} onSeek={vi.fn()} />)
    expect(screen.getByText('Rep 2')).toBeInTheDocument()
    expect(screen.getByText('78%')).toBeInTheDocument()
    expect(screen.getByText('Knee valgus')).toBeInTheDocument()
  })

  it('renders no fault tags when faults is empty', () => {
    render(
      <RepCard
        rep={{ ...rep, faults: [] }}
        active={false}
        onSeek={vi.fn()}
      />,
    )
    expect(screen.queryByText('Knee valgus')).not.toBeInTheDocument()
  })

  it('calls onSeek with start_sec when clicked', () => {
    const onSeek = vi.fn()
    render(<RepCard rep={rep} active={false} onSeek={onSeek} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onSeek).toHaveBeenCalledWith(4)
  })

  it('applies active styling class when active', () => {
    render(<RepCard rep={rep} active onSeek={vi.fn()} />)
    expect(screen.getByRole('button')).toHaveClass('rep-card--active')
  })
})
