type HeatmapSettingsPanelProps = {
  opacity: number
  onOpacityChange: (v: number) => void
}

export function HeatmapSettingsPanel({ opacity, onOpacityChange }: HeatmapSettingsPanelProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Display Settings</h3>

      <div className="grid gap-3">
        <div>
          <div className="mb-1 flex items-center justify-between">
            <label className="text-xs font-medium text-slate-600">Heatmap Opacity</label>
            <span className="text-xs font-bold text-blue-600">{opacity}%</span>
          </div>
          <input
            className="w-full accent-blue-600"
            max={100}
            min={0}
            step={5}
            type="range"
            value={opacity}
            onChange={(e) => onOpacityChange(Number(e.target.value))}
          />
        </div>

        <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
          <span className="text-xs font-medium text-slate-600">Layer</span>
          <span className="text-xs font-semibold text-slate-700">Visitors</span>
        </div>

        <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 opacity-40">
          <label className="text-xs font-medium text-slate-600">Show Zones</label>
          <input className="accent-blue-600" disabled type="checkbox" />
        </div>
        <p className="text-[11px] text-slate-400">Zone overlay requires zone geometry data</p>
      </div>
    </div>
  )
}
