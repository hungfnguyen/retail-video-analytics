import { memo } from 'react'
import {
  Line,
  LineChart,
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
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
      <div className="mb-3.5 flex items-center justify-between">
        <h2 className="m-0 text-[17px] font-bold text-slate-950">Traffic last 60 minutes</h2>
      </div>

      <div className="h-47">
        <ResponsiveContainer height={180} width="100%">
          <LineChart data={traffic}>
            <XAxis dataKey="time" tickLine={false} interval={9} />
            <YAxis tickLine={false} width={32} />
            <Tooltip isAnimationActive={false} />
            <Line
              dataKey="people_in"
              dot={false}
              isAnimationActive={false}
              name="People in"
              stroke="#2563eb"
              strokeWidth={2.5}
            />
            <Line
              dataKey="people_out"
              dot={false}
              isAnimationActive={false}
              name="People out"
              stroke="#16a34a"
              strokeWidth={2.5}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="flex gap-4.5 border-t border-slate-200 pt-3 text-[13px] text-slate-500">
        <span>Total in: {summary.total_in.toLocaleString()}</span>
        <span>Total out: {summary.total_out.toLocaleString()}</span>
        <span>Peak: {summary.peak_count}</span>
      </div>
    </section>
  )
})
