import type { LiveFrame } from '../types'
import { LIVE_VIDEO_TRANSPORT, resolveMediaUrl } from '../api/liveVideoApi'
import { useWebRtcVideo } from '../hooks/useWebRtcVideo'

type VideoPanelProps = {
  frame: LiveFrame
}

export function VideoPanel({ frame }: VideoPanelProps) {
  const streamUrl = resolveMediaUrl(frame.image_url)
  const webRtcEnabled = Boolean(streamUrl) && LIVE_VIDEO_TRANSPORT !== 'mjpeg'
  const { fallbackRequired, videoRef } = useWebRtcVideo(frame.camera_id, webRtcEnabled)
  const renderMjpegFallback = Boolean(streamUrl) && (!webRtcEnabled || fallbackRequired)
  const imageAspectRatio = frame.image_size.width > 0 && frame.image_size.height > 0
    ? `${frame.image_size.width} / ${frame.image_size.height}`
    : '16 / 9'

  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
      <div
        className="relative max-h-[72vh] min-h-[520px] overflow-hidden bg-slate-950"
        style={{ aspectRatio: imageAspectRatio }}
      >
        {renderMjpegFallback ? (
          <img
            alt={`Live camera ${frame.camera_id}`}
            className="h-full w-full object-contain"
            src={streamUrl}
          />
        ) : streamUrl ? (
          <video
            ref={videoRef}
            autoPlay
            className="h-full w-full object-contain"
            muted
            playsInline
          />
        ) : (
          <>
            <div className="absolute left-0 top-0 h-full w-[21%] bg-slate-900/25" />
            <div className="absolute right-0 top-0 h-full w-[21%] bg-slate-900/25" />
            <div className="absolute left-[22%] top-0 h-[18%] w-[56%] border-b-2 border-slate-900/20 bg-white/50" />

            {frame.heatmap_points.map((point) => (
              <span
                className="absolute z-10 h-48 w-48 rounded-full bg-[radial-gradient(circle,rgba(250,204,21,0.95),rgba(34,197,94,0.62)_42%,rgba(37,99,235,0.32)_72%,transparent)]"
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
                className="absolute z-20 border-2 border-green-500"
                key={detection.track_id}
                style={{
                  left: `${detection.bbox_norm.x * 100}%`,
                  top: `${detection.bbox_norm.y * 100}%`,
                  width: `${detection.bbox_norm.w * 100}%`,
                  height: `${detection.bbox_norm.h * 100}%`,
                }}
              >
                <span className="absolute -left-0.5 -top-6 bg-green-600 px-1.5 py-0.5 text-xs font-bold text-white">
                  ID {detection.track_id}
                </span>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3.5 text-[13px] text-slate-500">
        <span>Camera: {frame.camera_id}</span>
        <span>Annotated live stream</span>
      </div>
    </section>
  )
}
