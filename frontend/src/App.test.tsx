// frontend/src/App.test.tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const mockAnalysisResponse = {
  exercise: 'squat',
  frame_count: 100,
  reps: [
    { rep_index: 0, start_sec: 0, end_sec: 4, form_accuracy: 0.92, faults: [] },
    { rep_index: 1, start_sec: 4, end_sec: 8, form_accuracy: 0.78, faults: ['Knee valgus'] },
    { rep_index: 2, start_sec: 8, end_sec: 12, form_accuracy: 0.95, faults: [] },
  ],
  frames: [],
}

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

  it('walks from idle through analyzing to results with rep cards', async () => {
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

    // Resolving proves the cards rendered; the real assertion is specific,
    // known content. mockAnalysisResponse.reps[0].form_accuracy = 0.92 ->
    // "92%". A generic "some Rep text exists" check can't fail
    // independently of findAllByText itself; this proves the cards are
    // actually data-driven from the backend's response, not synthesized
    // client-side (there is no mock-data fallback anymore — the backend's
    // real reps render directly).
    await screen.findAllByText(/^Rep \d/)
    expect(screen.getByText('92%')).toBeInTheDocument()
  })

  it('rejects a file with a disallowed extension and keeps submit disabled', () => {
    render(<App />)

    const file = new File(['fake video content'], 'clip.avi', { type: 'video/x-msvideo' })
    const input = screen.getByLabelText(/drop a video/i)
    fireEvent.change(input, { target: { files: [file] } })

    expect(screen.getByText(/unsupported file type/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^analyze$/i })).toBeDisabled()
  })

  it('resets to a clean idle state after results, and supports a second upload→results cycle', async () => {
    render(<App />)
    await waitFor(() => expect(screen.getByText(/Backend: online/)).toBeInTheDocument())

    const runUploadToResults = async (filename: string) => {
      const file = new File(['fake video content'], filename, { type: 'video/mp4' })
      const input = screen.getByLabelText(/drop a video/i)
      fireEvent.change(input, { target: { files: [file] } })
      fireEvent.click(screen.getByRole('button', { name: /^analyze$/i }))

      await screen.findByText(/Analyzing your squat set/i)

      const video = await screen.findByTestId('results-video')
      Object.defineProperty(video, 'duration', { configurable: true, value: 12 })
      fireEvent.loadedMetadata(video)

      await screen.findAllByText(/^Rep \d/)
    }

    await runUploadToResults('clip.mp4')

    fireEvent.click(screen.getByRole('button', { name: /analyze another video/i }))

    // Back to a genuinely clean idle state: the upload form is visible
    // again, results are gone (proxy for ResultsView's unmount, which is
    // where its object-URL cleanup effect runs), and the submit button is
    // disabled again because no video is selected.
    expect(screen.getByLabelText(/drop a video/i)).toBeInTheDocument()
    expect(screen.queryByTestId('results-video')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^analyze$/i })).toBeDisabled()

    // A second full cycle works too.
    await runUploadToResults('clip-2.mp4')
    expect(screen.getByTestId('results-video')).toBeInTheDocument()
  })

  it('does not yank the user back to results if they navigate to History while an analysis is in flight', async () => {
    let resolveAnalyze: (value: { ok: true; json: () => Promise<typeof mockAnalysisResponse> }) => void
    const analyzePromise = new Promise<{ ok: true; json: () => Promise<typeof mockAnalysisResponse> }>(
      (resolve) => {
        resolveAnalyze = resolve
      },
    )

    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (typeof url === 'string' && url.includes('/analyze/')) {
          return analyzePromise
        }
        if (typeof url === 'string' && url.includes('/history')) {
          return Promise.resolve({ ok: true, json: async () => [] })
        }
        return Promise.resolve({ ok: true, json: async () => true })
      }),
    )

    render(<App />)
    await waitFor(() => expect(screen.getByText(/Backend: online/)).toBeInTheDocument())

    const file = new File(['fake video content'], 'clip.mp4', { type: 'video/mp4' })
    const input = screen.getByLabelText(/drop a video/i)
    fireEvent.change(input, { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: /^analyze$/i }))

    await screen.findByText(/Analyzing your squat set/i)

    // Navigate away to History while the analysis request is still pending.
    fireEvent.click(screen.getByRole('button', { name: 'History' }))
    await screen.findByText(/no workouts logged yet/i)

    // Now let the in-flight analysis resolve. It must not silently pull
    // the user back to the results view.
    resolveAnalyze!({ ok: true, json: async () => mockAnalysisResponse })
    await waitFor(() => expect(screen.getByText(/no workouts logged yet/i)).toBeInTheDocument())
    expect(screen.queryByTestId('results-video')).not.toBeInTheDocument()
  })

  it('switches to the History view and back to idle via the nav', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (typeof url === 'string' && url.includes('/history')) {
          return Promise.resolve({ ok: true, json: async () => [] })
        }
        return Promise.resolve({ ok: true, json: async () => mockAnalysisResponse })
      }),
    )

    render(<App />)
    await waitFor(() => expect(screen.getByText(/Backend: online/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'History' }))
    await screen.findByText(/no workouts logged yet/i)

    fireEvent.click(screen.getByRole('button', { name: 'New Analysis' }))
    expect(screen.getByLabelText(/drop a video/i)).toBeInTheDocument()
  })

  it('shows a newly-analyzed video as a history entry after switching to History', async () => {
    const historyEntry = {
      id: 1,
      exercise: 'squat',
      date: '2026-09-15',
      source: 'video',
      created_at: '2026-09-15T12:00:00Z',
      sets: null,
      reps: null,
      weight: null,
      notes: null,
      rep_count: 3,
      avg_form_accuracy: 0.9,
      rep_scores: mockAnalysisResponse.reps,
    }

    let historyEntries: typeof historyEntry[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (typeof url === 'string' && url.includes('/analyze/')) {
          // Simulate the backend auto-logging a history entry as a side
          // effect of a successful analysis, the same way the real
          // /analyze route does.
          historyEntries = [historyEntry]
          return Promise.resolve({ ok: true, json: async () => mockAnalysisResponse })
        }
        if (typeof url === 'string' && url.includes('/history') && (!init || init.method === undefined)) {
          return Promise.resolve({ ok: true, json: async () => historyEntries })
        }
        return Promise.resolve({ ok: true, json: async () => true })
      }),
    )

    render(<App />)
    await waitFor(() => expect(screen.getByText(/Backend: online/)).toBeInTheDocument())

    const file = new File(['fake video content'], 'clip.mp4', { type: 'video/mp4' })
    const input = screen.getByLabelText(/drop a video/i)
    fireEvent.change(input, { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: /^analyze$/i }))

    await screen.findByText(/Analyzing your squat set/i)
    const video = await screen.findByTestId('results-video')
    Object.defineProperty(video, 'duration', { configurable: true, value: 12 })
    fireEvent.loadedMetadata(video)
    await screen.findAllByText(/^Rep \d/)

    fireEvent.click(screen.getByRole('button', { name: 'History' }))

    await screen.findByText(/3 reps/)
  })
})
