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
  const mediaFps = frame.media_fps > 0 ? frame.media_fps : frame.fps
  const mediaLatencyMs = frame.media_latency_ms || frame.latency_ms

  return (
    <section className="relative min-h-[490px] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
      <div className="absolute left-3.5 top-3.5 z-40 rounded-md bg-slate-900/75 px-2.5 py-1.5 text-[13px] text-white">
        Media FPS {mediaFps.toFixed(1)} | Media latency {mediaLatencyMs}ms | Infer {frame.inference_ms}ms
      </div>

      <div className="relative h-[440px] overflow-hidden bg-[linear-gradient(90deg,rgba(15,23,42,0.1)_1px,transparent_1px),linear-gradient(rgba(15,23,42,0.08)_1px,transparent_1px),linear-gradient(180deg,#dce7f1_0%,#cbd9e8_44%,#b7c6d3_100%)] bg-[length:58px_58px,58px_58px,100%_100%]">
        {renderMjpegFallback ? (
          <img
            alt={`Live camera ${frame.camera_id}`}
            className="h-full w-full object-cover"
            src={streamUrl}
          />
        ) : streamUrl ? (
          <video
            ref={videoRef}
            autoPlay
            className="h-full w-full object-cover"
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

      <div className="flex items-center justify-between px-4 py-3.5 text-[13px] text-slate-500">
        <span>Camera: {frame.camera_id}</span>
        <span>
          Frame {frame.frame_id} | Proc {frame.processing_fps.toFixed(1)} FPS | Enc {frame.encode_ms}ms | Drops{' '}
          {frame.reader_drop_count}
        </span>
      </div>
    </section>
  )
}
