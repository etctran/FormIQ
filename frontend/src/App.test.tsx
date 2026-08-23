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

    // Resolving proves the cards rendered; the real assertion is specific,
    // known content. For a 12s mock video, mockReps.ts's getReps derives
    // repCount = round(12 / 4) = 3 reps of 4s each, so rep index 0 gets
    // MOCK_ACCURACIES[0] = 0.92 -> "92%". A generic "some Rep text
    // exists" check can't fail independently of findAllByText itself;
    // this proves the cards are actually data-driven from the mock.
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
})
