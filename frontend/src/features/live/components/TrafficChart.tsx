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

export function TrafficChart({ traffic, summary }: TrafficChartProps) {
  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <h2>Traffic last 60 minutes</h2>
      </div>
      <div className="chart-box">
        <ResponsiveContainer height={180} width="100%">
          <LineChart data={traffic}>
            <XAxis dataKey="time" tickLine={false} />
            <YAxis tickLine={false} width={32} />
            <Tooltip />
            <Line
              dataKey="people_in"
              dot={false}
              name="People in"
              stroke="#2563eb"
              strokeWidth={2.5}
            />
            <Line
              dataKey="people_out"
              dot={false}
              name="People out"
              stroke="#16a34a"
              strokeWidth={2.5}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="traffic-summary">
        <span>Total in: {summary.total_in.toLocaleString()}</span>
        <span>Total out: {summary.total_out.toLocaleString()}</span>
        <span>Peak: {summary.peak_count}</span>
      </div>
    </section>
  )
}
