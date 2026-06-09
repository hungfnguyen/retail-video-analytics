import { useEffect, useRef, useState } from 'react'
import { Play, X } from 'lucide-react'
import type { Alert } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type AlertDetailProps = {
  alert: Alert
  onClose: () => void
}

const severityStyles = {
  high: 'bg-red-100 text-red-700 ring-red-200',
  medium: 'bg-orange-100 text-orange-700 ring-orange-200',
  low: 'bg-amber-100 text-amber-700 ring-amber-200',
}

function formatTs(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

export function AlertDetail({ alert, onClose }: AlertDetailProps) {
  const [ackStatus, setAckStatus] = useState<'idle' | 'loading' | 'done'>('idle')
  const [showVideo, setShowVideo] = useState(false)
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose()
  }

  const handleAck = async () => {
    if (ackStatus !== 'idle') return
    setAckStatus('loading')
    try {
      await fetch(`${API_BASE_URL}/api/v1/alerts/${alert.alert_id}/ack`, { method: 'POST' })
      onClose()
    } catch {
      setAckStatus('idle')
    }
  }

  const clipUrl = alert.clip_s3_key
    ? `${API_BASE_URL}/api/v1/alerts/${alert.alert_id}/clip`
    : null

  // Show snapshot for all alerts that have one, including HIGH severity.
  // For HIGH alerts with a clip, the snapshot is always shown first; the
  // video is only fetched when the user explicitly requests it.
  const snapshotUrl = alert.snapshot_key
    ? `${API_BASE_URL}/api/v1/alerts/${alert.alert_id}/snapshot`
    : null

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"
      onClick={handleOverlayClick}
    >
      <div className="w-full max-w-xl rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 p-5">
          <div className="min-w-0">
            <h2 className="m-0 truncate text-[17px] font-bold text-slate-950">{alert.title}</h2>
            <p className="m-0 mt-0.5 text-sm text-slate-500">{alert.description}</p>
          </div>
          <button
            className="shrink-0 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            onClick={onClose}
            type="button"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-5">
          {/* Snapshot + lazy video — shown before video is requested */}
          {!showVideo && (
            <>
              {snapshotUrl && (
                <div className="relative mb-5 overflow-hidden rounded-lg bg-slate-100">
                  <img alt="Alert snapshot" className="w-full object-cover" src={snapshotUrl} />
                  {clipUrl && (
                    <button
                      className="absolute bottom-3 right-3 flex items-center gap-2 rounded-lg bg-black/70 px-3 py-2 text-xs font-bold text-white backdrop-blur-sm transition hover:bg-black/90"
                      onClick={() => setShowVideo(true)}
                      type="button"
                    >
                      <Play size={13} />
                      Watch video clip
                    </button>
                  )}
                </div>
              )}

              {/* No snapshot but clip available — show standalone button */}
              {clipUrl && !snapshotUrl && (
                <button
                  className="mb-5 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-slate-50 py-5 text-sm font-bold text-slate-700 transition hover:bg-slate-100"
                  onClick={() => setShowVideo(true)}
                  type="button"
                >
                  <Play size={16} />
                  Watch video clip
                </button>
              )}
            </>
          )}

          {/* Video — only mounted after user clicks */}
          {clipUrl && showVideo && (
            <div className="mb-5 overflow-hidden rounded-lg bg-slate-950">
              <video autoPlay className="w-full" controls src={clipUrl} />
            </div>
          )}

          {/* Alert metadata */}
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-sm">
            <div>
              <dt className="font-semibold text-slate-500">Camera</dt>
              <dd className="text-slate-900">{alert.camera_id}</dd>
            </div>
            <div>
              <dt className="font-semibold text-slate-500">Zone</dt>
              <dd className="text-slate-900">{alert.zone.replace(/_/g, ' ')}</dd>
            </div>
            <div>
              <dt className="font-semibold text-slate-500">Type</dt>
              <dd className="text-slate-900">{alert.alert_type.replace(/_/g, ' ')}</dd>
            </div>
            <div>
              <dt className="font-semibold text-slate-500">Severity</dt>
              <dd>
                <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-bold ring-1 ${severityStyles[alert.severity]}`}>
                  {alert.severity.charAt(0).toUpperCase() + alert.severity.slice(1)}
                </span>
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="font-semibold text-slate-500">Time</dt>
              <dd className="text-slate-900">{formatTs(alert.event_ts)}</dd>
            </div>
          </dl>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-2.5 border-t border-slate-100 p-4">
          <button
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
          <button
            className={`rounded-lg px-4 py-2 text-sm font-bold text-white transition ${
              ackStatus === 'done'
                ? 'bg-emerald-500 cursor-default'
                : ackStatus === 'loading'
                  ? 'bg-blue-400 cursor-wait'
                  : 'bg-blue-600 hover:bg-blue-700'
            }`}
            disabled={ackStatus !== 'idle'}
            onClick={() => void handleAck()}
            type="button"
          >
            {ackStatus === 'done' ? 'Acknowledged' : ackStatus === 'loading' ? 'Saving...' : 'Acknowledge'}
          </button>
        </div>
      </div>
    </div>
  )
}
