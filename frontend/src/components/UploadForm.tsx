// frontend/src/components/UploadForm.tsx
import { useState } from 'react'
import type { ChangeEvent, DragEvent, FormEvent } from 'react'
import { EXERCISES } from '../types'
import type { Exercise } from '../types'
import './UploadForm.css'

const ALLOWED_EXTENSIONS = ['.mp4', '.mov', '.webm']

interface UploadFormProps {
  onSubmit: (exercise: Exercise, video: File) => void
}

function hasAllowedExtension(filename: string): boolean {
  const lower = filename.toLowerCase()
  return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

export function UploadForm({ onSubmit }: UploadFormProps) {
  const [exercise, setExercise] = useState<Exercise>(EXERCISES[0])
  const [video, setVideo] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)

  // Shared by both selection paths (file-input onChange and drag/drop) so
  // validation logic never drifts between the two. Returns whether the
  // file was accepted, so callers that need to react to rejection (e.g.
  // clearing the <input>'s own value) can do so.
  const selectFile = (file: File | null): boolean => {
    if (file && !hasAllowedExtension(file.name)) {
      setFileError('Unsupported file type — use .mp4, .mov, or .webm')
      setVideo(null)
      return false
    }
    setFileError(null)
    setVideo(file)
    return true
  }

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const accepted = selectFile(event.target.files?.[0] ?? null)
    if (!accepted) {
      // Without this, re-selecting the exact same rejected file fires no
      // `change` event (browsers only fire `change` when the selection
      // differs), so the error would never re-appear on a second attempt.
      event.target.value = ''
    }
  }

  const handleDragOver = (event: DragEvent<HTMLLabelElement>) => {
    // Required to allow a drop at all — without preventDefault() here the
    // browser's default dragover behavior blocks the drop event entirely.
    event.preventDefault()
  }

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    // Without preventDefault() the browser's default drop behavior
    // navigates the whole tab to the dropped file, destroying all React
    // state.
    event.preventDefault()
    selectFile(event.dataTransfer.files?.[0] ?? null)
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!video) return
    onSubmit(exercise, video)
  }

  return (
    <form onSubmit={handleSubmit} className="upload-form">
      <div className="upload-form__label">Exercise</div>
      <div className="upload-form__pills" role="radiogroup" aria-label="Exercise">
        {EXERCISES.map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={exercise === option}
            className={`upload-form__pill ${exercise === option ? 'upload-form__pill--active' : ''}`.trim()}
            onClick={() => setExercise(option)}
          >
            {option.replace('_', ' ')}
          </button>
        ))}
      </div>

      <label
        htmlFor="video"
        className="upload-form__dropzone"
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {video ? video.name : 'Drop a video or click to browse'}
        <input
          id="video"
          type="file"
          accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
          onChange={handleFileChange}
        />
      </label>
      {fileError && <p className="error">{fileError}</p>}

      <button type="submit" className="upload-form__submit" disabled={!video}>
        Analyze
      </button>
    </form>
  )
}
