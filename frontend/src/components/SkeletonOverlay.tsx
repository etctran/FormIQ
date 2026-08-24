// frontend/src/components/SkeletonOverlay.tsx
import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import type { Frame } from '../types'
import { interpolateFrame } from '../interpolateFrame'
import { POSE_CONNECTIONS } from '../poseConnections'
import './SkeletonOverlay.css'

interface SkeletonOverlayProps {
  frames: Frame[]
  videoRef: RefObject<HTMLVideoElement | null>
}

export function SkeletonOverlay({ frames, videoRef }: SkeletonOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const video = videoRef.current
    if (!canvas || !video) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let rafId: number

    const draw = () => {
      rafId = requestAnimationFrame(draw)

      if (video.videoWidth === 0 || video.videoHeight === 0) return

      // Match canvas resolution to its displayed size every tick -- cheap
      // for a 33-point skeleton, and avoids a separate ResizeObserver.
      const displayWidth = video.clientWidth
      const displayHeight = video.clientHeight
      if (canvas.width !== displayWidth || canvas.height !== displayHeight) {
        canvas.width = displayWidth
        canvas.height = displayHeight
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height)

      const keypoints = interpolateFrame(frames, video.currentTime)
      if (!keypoints) return

      const scaleX = displayWidth / video.videoWidth
      const scaleY = displayHeight / video.videoHeight

      ctx.strokeStyle = '#22d3ee'
      ctx.lineWidth = 3
      ctx.lineCap = 'round'
      for (const [aIdx, bIdx] of POSE_CONNECTIONS) {
        const a = keypoints[aIdx]
        const b = keypoints[bIdx]
        if (!a || !b) continue
        ctx.beginPath()
        ctx.moveTo(a.x * scaleX, a.y * scaleY)
        ctx.lineTo(b.x * scaleX, b.y * scaleY)
        ctx.stroke()
      }

      ctx.fillStyle = '#a78bfa'
      for (const kp of keypoints) {
        ctx.beginPath()
        ctx.arc(kp.x * scaleX, kp.y * scaleY, 5, 0, Math.PI * 2)
        ctx.fill()
      }
    }

    rafId = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(rafId)
  }, [frames, videoRef])

  return <canvas ref={canvasRef} className="skeleton-overlay" />
}
