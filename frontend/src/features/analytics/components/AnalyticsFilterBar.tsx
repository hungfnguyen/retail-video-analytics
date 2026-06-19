import { CalendarDays, RefreshCw } from 'lucide-react'
import { datePresetLabels, type DatePreset } from '../datePresets'

type AnalyticsFilterBarProps = {
  preset: DatePreset
  onPresetChange: (p: DatePreset) => void
  onRefresh: () => void
}

function StaticSelect({ label, value, disabled = false }: { label: string; value: string; disabled?: boolean }) {
  return (
    <div aria-label={label} className={`flex min-w-[140px] items-center justify-between rounded-xl border px-3.5 py-2.5 text-sm shadow-sm ${
      disabled ? 'border-slate-100 bg-slate-50 text-slate-400' : 'border-slate-200 bg-white text-slate-700'
    }`}>
      <span>{value}</span>
      <span className="text-slate-400">⌄</span>
    </div>
  )
}

export function AnalyticsFilterBar({ preset, onPresetChange, onRefresh }: AnalyticsFilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2.5">
      <StaticSelect label="Store" value="Store A" />
      <StaticSelect label="Camera" value="All Cameras" disabled />
      <StaticSelect label="Zone" value="All Zones" disabled />

      <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-700 shadow-sm">
        <CalendarDays size={16} className="text-slate-400" />
        <select
          className="bg-transparent font-medium text-slate-700 outline-none"
          value={preset}
          onChange={(e) => onPresetChange(e.target.value as DatePreset)}
        >
          {(Object.entries(datePresetLabels) as [DatePreset, string][]).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>

      <button
        className="grid h-11 w-11 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-slate-300 hover:text-slate-800"
        onClick={onRefresh}
        title="Refresh analytics"
        type="button"
      >
        <RefreshCw size={16} />
      </button>
    </div>
  )
}
