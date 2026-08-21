import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }),
  )
})

describe('App', () => {
  it('renders the heading and reports backend health', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'FormIQ' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/Backend: online/)).toBeInTheDocument())
  })

  it('disables submit until a video is selected', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: /analyze/i })).toBeDisabled()
  })
})
