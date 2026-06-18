import { Camera, Maximize2, Volume2 } from 'lucide-react'
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
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div
        className="relative min-h-[520px] overflow-hidden bg-slate-950"
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

        <div className="absolute left-3 top-3 rounded-lg bg-slate-950/70 px-2 py-1 text-xs font-medium text-white backdrop-blur">
          {frame.capture_ts ? new Date(frame.capture_ts).toLocaleString([], {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          }) : 'Live feed'}
        </div>

        <div className="absolute bottom-3 left-3 inline-flex items-center gap-2 rounded-full bg-slate-950/70 px-3 py-1.5 text-xs font-medium text-white backdrop-blur">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          Live
        </div>

        <div className="absolute bottom-3 right-3 flex items-center gap-2 rounded-xl bg-slate-950/70 px-2 py-1.5 text-white backdrop-blur">
          <button
            className="grid h-7 w-7 place-items-center rounded-lg bg-white/10 transition hover:bg-white/15"
            type="button"
          >
            <Volume2 size={14} />
          </button>
          <button
            className="grid h-7 w-7 place-items-center rounded-lg bg-white/10 transition hover:bg-white/15"
            type="button"
          >
            <Camera size={14} />
          </button>
          <button
            className="grid h-7 w-7 place-items-center rounded-lg bg-white/10 transition hover:bg-white/15"
            type="button"
          >
            <Maximize2 size={14} />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-[13px] text-slate-500">
        <span>Camera: {frame.camera_id}</span>
        <div className="flex flex-wrap items-center gap-3">
          <span>Metadata {frame.metadata_status}</span>
          <span>{frame.latency_ms}ms latency</span>
        </div>
      </div>
    </section>
  )
}
