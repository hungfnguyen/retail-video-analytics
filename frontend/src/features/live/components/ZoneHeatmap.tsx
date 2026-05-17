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
    <section className="panel heatmap-panel">
      <div className="panel-header">
        <h2>Zone heatmap</h2>
      </div>
      <div className="zone-grid">
        {rows.map((row) =>
          cols.map((col) => {
            const value = getValue(cells, row, col)
            return (
              <span
                className="zone-cell"
                key={`${row}-${col}`}
                style={{ '--heat': `${value}%` } as CSSProperties}
                title={`${row}-${col}: ${value}`}
              />
            )
          }),
        )}
      </div>
      <div className="heatmap-scale">
        <span>Low</span>
        <div />
        <span>High</span>
      </div>
    </section>
  )
}
