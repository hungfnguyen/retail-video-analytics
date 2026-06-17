import { memo } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TrafficPoint, TrafficSummary } from '../types'

type TrafficChartProps = {
  traffic: TrafficPoint[]
  summary: TrafficSummary
}

export const TrafficChart = memo(function TrafficChart({ traffic, summary }: TrafficChartProps) {
  const peakPoint = traffic.reduce(
    (best, p) => (p.current_count > best.current_count ? p : best),
    traffic[0] ?? { current_count: 0, time: '' },
  )

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Visitors Trend</h3>
          <p className="text-xs text-slate-400">Last 60 minutes</p>
        </div>
        <span className="rounded-lg border border-slate-100 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-500">
          Today
        </span>
      </div>

      <div className="px-4 pb-4 pt-3">
        <div className="h-44">
          <ResponsiveContainer height="100%" width="100%">
            <LineChart data={traffic} margin={{ top: 12, right: 8, bottom: 0, left: -8 }}>
              <CartesianGrid stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="time" tickLine={false} tick={{ fontSize: 10 }} interval={9} />
              <YAxis tickLine={false} width={28} tick={{ fontSize: 10 }} allowDecimals={false} />
              <Tooltip
                isAnimationActive={false}
                formatter={(v) => [Number(v ?? 0), 'Visitors']}
              />
              {peakPoint && peakPoint.current_count > 0 && (
                <>
                  <ReferenceLine
                    x={peakPoint.time}
                    stroke="#cbd5e1"
                    strokeDasharray="4 4"
                  />
                  <ReferenceDot
                    x={peakPoint.time}
                    y={peakPoint.current_count}
                    fill="#4f46e5"
                    r={4}
                    stroke="white"
                    strokeWidth={2}
                  />
                </>
              )}
              <Line
                dataKey="current_count"
                dot={false}
                isAnimationActive={false}
                name="Visitors"
                stroke="#4f46e5"
                strokeWidth={2.5}
                type="monotone"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-3 flex gap-4 border-t border-slate-100 pt-2.5 text-xs text-slate-500">
          <span>Total in: <strong className="text-slate-700">{summary.total_in.toLocaleString()}</strong></span>
          <span>Total out: <strong className="text-slate-700">{summary.total_out.toLocaleString()}</strong></span>
          <span>Peak: <strong className="text-slate-700">{summary.peak_count}</strong></span>
        </div>
      </div>
    </div>
  )
})
