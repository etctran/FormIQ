// frontend/src/App.test.tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const mockAnalysisResponse = { exercise: 'squat', frame_count: 100, reps: [] }

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => mockAnalysisResponse }),
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

  it('walks from idle through analyzing to results with mock rep cards', async () => {
    render(<App />)
    await waitFor(() => expect(screen.getByText(/Backend: online/)).toBeInTheDocument())

    const file = new File(['fake video content'], 'clip.mp4', { type: 'video/mp4' })
    const input = screen.getByLabelText(/drop a video/i)
    fireEvent.change(input, { target: { files: [file] } })

    fireEvent.click(screen.getByRole('button', { name: /analyze/i }))

    // Resolving is the assertion: findByText throws if the text never
    // appears. Don't chain `.toBeInTheDocument()` on the resolved node —
    // RTL's async utilities deliberately drain one extra microtask/macrotask
    // tick between finding the node and returning it (so in-flight React
    // updates settle before control returns to the test). With this
    // mocked `fetch` resolving instantly, that drain is enough time for
    // the app to advance all the way to 'results', unmounting
    // AnalyzingView and detaching the very node just found — a rechecked
    // `.toBeInTheDocument()` would then fail on a stale-but-non-null
    // reference even though the text genuinely rendered.
    await screen.findByText(/Analyzing your squat set/i)

    const video = await screen.findByTestId('results-video')
    Object.defineProperty(video, 'duration', { configurable: true, value: 12 })
    fireEvent.loadedMetadata(video)

    expect((await screen.findAllByText(/^Rep \d/)).length).toBeGreaterThan(0)
  })
})
