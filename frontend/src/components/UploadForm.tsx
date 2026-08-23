// frontend/src/components/UploadForm.tsx
import { useState } from 'react'
import type { FormEvent } from 'react'
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

  const handleFileChange = (file: File | null) => {
    if (file && !hasAllowedExtension(file.name)) {
      setFileError('Unsupported file type — use .mp4, .mov, or .webm')
      setVideo(null)
      return
    }
    setFileError(null)
    setVideo(file)
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

      <label htmlFor="video" className="upload-form__dropzone">
        {video ? video.name : 'Drop a video or click to browse'}
        <input
          id="video"
          type="file"
          accept="video/*"
          onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
        />
      </label>
      {fileError && <p className="error">{fileError}</p>}

      <button type="submit" className="upload-form__submit" disabled={!video}>
        Analyze
      </button>
    </form>
  )
}
