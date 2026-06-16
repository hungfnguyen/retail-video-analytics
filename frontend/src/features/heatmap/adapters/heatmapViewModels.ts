import type { PresenceHeatmapData } from '../../analytics/types'

export type HeatmapStats = {
  maxValue: number
  averageValue: number
  hotspotCount: number
  concentrationScore: number
  dataAvailable: boolean
  hottestAreaLabel: string
}

export type HotspotItem = {
  id: string
  label: string
  value: number
  intensity: 'low' | 'medium' | 'high'
}

export function describeCellLocation(row: number, col: number, gridRows: number, gridCols: number): string {
  const vertical = row < gridRows / 3 ? 'upper' : row > (gridRows * 2) / 3 ? 'lower' : 'middle'
  const horizontal = col < gridCols / 3 ? 'left' : col > (gridCols * 2) / 3 ? 'right' : 'center'
  if (horizontal === 'center') return `${vertical} area`
  return `${vertical}-${horizontal} area`
}

export function getHeatmapStats(data: PresenceHeatmapData | null): HeatmapStats {
  if (!data || data.data_status !== 'ready' || data.cells.length === 0) {
    return { maxValue: 0, averageValue: 0, hotspotCount: 0, concentrationScore: 0, dataAvailable: false, hottestAreaLabel: '—' }
  }

  const values = data.cells.map((c) => c.value)
  const maxValue = Math.max(...values)
  const averageValue = values.reduce((s, v) => s + v, 0) / values.length
  const hotspotCount = values.filter((v) => v >= 60).length

  const totalCells = data.grid_rows * data.grid_cols
  const concentrationScore = totalCells > 0 ? hotspotCount / totalCells : 0

  const hottestCell = data.cells.reduce((best, c) => (c.value > best.value ? c : best))
  const hottestAreaLabel = describeCellLocation(hottestCell.row, hottestCell.col, data.grid_rows, data.grid_cols)

  return { maxValue, averageValue, hotspotCount, concentrationScore, dataAvailable: true, hottestAreaLabel }
}

export function getTopHotspots(data: PresenceHeatmapData | null, limit = 5): HotspotItem[] {
  if (!data || data.cells.length === 0) return []

  return [...data.cells]
    .sort((a, b) => b.value - a.value)
    .slice(0, limit)
    .map((cell) => ({
      id: `${cell.row}-${cell.col}`,
      label: describeCellLocation(cell.row, cell.col, data.grid_rows, data.grid_cols),
      value: cell.value,
      intensity: cell.value >= 150 ? 'high' : cell.value >= 60 ? 'medium' : 'low',
    }))
}
