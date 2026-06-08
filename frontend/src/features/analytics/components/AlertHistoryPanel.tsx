import { memo } from 'react'
import { Bell } from 'lucide-react'
import type { AlertHistoryData, AlertHistoryRecord } from '../types'

const severityStyles = {
  high: 'bg-red-100 text-red-600',
  medium: 'bg-orange-100 text-orange-700',
  low: 'bg-amber-100 text-amber-700',
}

function formatTs(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function AlertRow({ r }: { r: AlertHistoryRecord }) {
  return (
    <tr className="hover:bg-slate-50">
      <td className="py-2.5 pr-4 text-[13px] text-slate-500">{formatTs(r.event_ts)}</td>
      <td className="py-2.5 pr-4 font-semibold text-slate-800">{r.title}</td>
      <td className="py-2.5 pr-4 text-[13px] text-slate-600">{r.camera_id}</td>
      <td className="py-2.5 pr-4 text-[13px] text-slate-500">{r.zone.replace(/_/g, ' ')}</td>
      <td className="py-2.5">
        <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${severityStyles[r.severity]}`}>
          {r.severity.charAt(0).toUpperCase() + r.severity.slice(1)}
        </span>
      </td>
    </tr>
  )
}

export const AlertHistoryPanel = memo(function AlertHistoryPanel({ data }: { data: AlertHistoryData }) {
  return (
    <div className="mt-8 border-t border-slate-200 pt-6">
      <div className="mb-4 flex items-center gap-2">
        <Bell className="text-red-500" size={20} />
        <h2 className="m-0 text-xl font-bold text-slate-950">Alert History</h2>
        <span className="rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-bold text-red-600 ring-1 ring-red-200">
          Gold lakehouse
        </span>
      </div>

      {data.data_status === 'ready' && data.records.length > 0 ? (
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="pb-2 pr-4">Time</th>
                  <th className="pb-2 pr-4">Alert</th>
                  <th className="pb-2 pr-4">Camera</th>
                  <th className="pb-2 pr-4">Zone</th>
                  <th className="pb-2">Severity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {data.records.map((r) => <AlertRow key={r.alert_id} r={r} />)}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <div className="grid min-h-24 place-items-center rounded-lg border border-dashed border-slate-200 bg-white text-sm text-slate-400">
          {data.data_status === 'error'
            ? `Query error: ${data.error_message}`
            : 'No alert history in Gold lakehouse yet — requires clip alerts enabled + GoldAlertsJob running.'}
        </div>
      )}
    </div>
  )
})
