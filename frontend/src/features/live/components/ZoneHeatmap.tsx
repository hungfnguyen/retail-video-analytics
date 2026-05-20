import type { CSSProperties } from 'react'
import type { ZoneHeatmapCell } from '../types'

type ZoneHeatmapProps = {
  cells: ZoneHeatmapCell[]
}

const rows = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
const cols = [1, 2, 3, 4, 5, 6, 7]

function getValue(cells: ZoneHeatmapCell[], row: string, col: number) {
  return cells.find((cell) => cell.zone_row === row && cell.zone_col === col)
    ?.value ?? 24
}

export function ZoneHeatmap({ cells }: ZoneHeatmapProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
      <div className="mb-3.5 flex items-center justify-between">
        <h2 className="m-0 text-[17px] font-bold text-slate-950">Zone heatmap</h2>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {rows.map((row) =>
          cols.map((col) => {
            const value = getValue(cells, row, col)
            return (
              <span
                className="block h-7.5 rounded-sm"
                key={`${row}-${col}`}
                style={{
                  '--heat': `${value}%`,
                  background:
                    'linear-gradient(135deg, #60a5fa, hsl(138 65% calc(78% - var(--heat) * 0.18)), hsl(31 92% calc(74% - var(--heat) * 0.2)))',
                } as CSSProperties}
                title={`${row}-${col}: ${value}`}
              />
            )
          }),
        )}
      </div>

      <div className="mt-3.5 grid grid-cols-[auto_1fr_auto] items-center gap-2 text-xs text-slate-500">
        <span>Low</span>
        <div className="h-2 rounded-full bg-gradient-to-r from-blue-400 via-green-300 via-yellow-300 to-orange-500" />
        <span>High</span>
      </div>
    </section>
  )
}
