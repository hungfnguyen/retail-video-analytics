import { RefreshCw } from 'lucide-react'

export type DatePreset = 'today' | 'last_7_days' | 'last_14_days' | 'last_30_days'

export const datePresetToDays: Record<DatePreset, number> = {
  today: 1,
  last_7_days: 7,
  last_14_days: 14,
  last_30_days: 30,
}

const presetLabels: Record<DatePreset, string> = {
  today: 'Today',
  last_7_days: 'Last 7 days',
  last_14_days: 'Last 14 days',
  last_30_days: 'Last 30 days',
}

type AnalyticsFilterBarProps = {
  preset: DatePreset
  onPresetChange: (p: DatePreset) => void
  onRefresh: () => void
}

export function AnalyticsFilterBar({ preset, onPresetChange, onRefresh }: AnalyticsFilterBarProps) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1">
        <span className="text-xs font-medium text-slate-500">Date range:</span>
        <select
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm focus:border-blue-400 focus:outline-none"
          value={preset}
          onChange={(e) => onPresetChange(e.target.value as DatePreset)}
        >
          {(Object.entries(presetLabels) as [DatePreset, string][]).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </div>

      <div
        className="flex items-center gap-1.5 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-400"
        title="Camera filter available after backend supports per-camera queries"
      >
        Camera: All
      </div>

      <button
        className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm hover:border-blue-300 hover:text-blue-700 transition"
        onClick={onRefresh}
        title="Refresh data"
        type="button"
      >
        <RefreshCw size={15} />
      </button>
    </div>
  )
}
