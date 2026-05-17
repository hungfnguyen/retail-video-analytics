import type { LiveFrame } from '../types'

type VideoPanelProps = {
  frame: LiveFrame
}

export function VideoPanel({ frame }: VideoPanelProps) {
  return (
    <section className="video-panel">
      <div className="video-overlay-status">
        FPS {frame.fps.toFixed(1)} | Latency {frame.latency_ms}ms
      </div>
      <div className="mock-video-surface">
        <div className="aisle aisle-left" />
        <div className="aisle aisle-right" />
        <div className="store-entry" />
        {frame.heatmap_points.map((point) => (
          <span
            className="heat-point"
            key={`${point.x}-${point.y}-${point.intensity}`}
            style={{
              left: `${point.x * 100}%`,
              top: `${point.y * 100}%`,
              opacity: 0.35 + point.intensity * 0.45,
              transform: `translate(-50%, -50%) scale(${0.8 + point.intensity})`,
            }}
          />
        ))}
        {frame.detections.map((detection) => (
          <div
            className="bbox"
            key={detection.track_id}
            style={{
              left: `${detection.bbox_norm.x * 100}%`,
              top: `${detection.bbox_norm.y * 100}%`,
              width: `${detection.bbox_norm.w * 100}%`,
              height: `${detection.bbox_norm.h * 100}%`,
            }}
          >
            <span>ID {detection.track_id}</span>
          </div>
        ))}
      </div>
      <div className="video-footer">
        <span>Camera: {frame.camera_id}</span>
        <span>Frame {frame.frame_id}</span>
      </div>
    </section>
  )
}
