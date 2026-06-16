import { useEffect, useRef } from 'react'
import type { HeatmapCell } from '../../analytics/types'

// Pre-built JET colormap LUT (256 entries): blue→cyan→green→yellow→red
const LUT_SIZE = 256
const colorLUT = new Uint8ClampedArray(LUT_SIZE * 3)
;(function buildLut() {
  for (let i = 0; i < LUT_SIZE; i++) {
    const t = i / (LUT_SIZE - 1)
    const clamp = (v: number) => Math.max(0, Math.min(1, v))
    const r = clamp(1.5 - Math.abs(4 * t - 3))
    const g = clamp(1.5 - Math.abs(4 * t - 2))
    const b = clamp(1.5 - Math.abs(4 * t - 1))
    colorLUT[i * 3]     = Math.round(r * 255)
    colorLUT[i * 3 + 1] = Math.round(g * 255)
    colorLUT[i * 3 + 2] = Math.round(b * 255)
  }
})()

function renderHeatmap(
  canvas: HTMLCanvasElement,
  cells: HeatmapCell[],
  gridRows: number,
  gridCols: number,
  opacity = 100,
): void {
  const { width, height } = canvas
  const ctx = canvas.getContext('2d')
  if (!ctx || width === 0 || height === 0) return

  ctx.clearRect(0, 0, width, height)
  if (cells.length === 0) return

  // Offscreen canvas for grayscale blob accumulation
  const off = document.createElement('canvas')
  off.width = width
  off.height = height
  const octx = off.getContext('2d')!

  // Black base so 'lighter' blending accumulates into bright regions
  octx.fillStyle = '#000'
  octx.fillRect(0, 0, width, height)
  octx.globalCompositeOperation = 'lighter'

  const cellW = width / gridCols
  const cellH = height / gridRows
  // 1.3× cell size: just enough to soften cell edges, minimal cross-cell bleed
  const radius = Math.max(cellW, cellH) * 1.3

  for (const cell of cells) {
    const cx = (cell.col + 0.5) * cellW
    const cy = (cell.row + 0.5) * cellH
    // Cap at 180 so even the hottest isolated cell stays in orange range;
    // dense clusters accumulate past 200+ → deep red via 'lighter' blending
    const v = Math.min(180, Math.round(cell.value * 1.8))
    const v55 = Math.round(v * 0.55)

    const grad = octx.createRadialGradient(cx, cy, 0, cx, cy, radius)
    grad.addColorStop(0,    `rgb(${v},${v},${v})`)
    grad.addColorStop(0.45, `rgb(${v55},${v55},${v55})`)
    grad.addColorStop(1,    'rgb(0,0,0)')
    octx.fillStyle = grad
    octx.beginPath()
    octx.arc(cx, cy, radius, 0, Math.PI * 2)
    octx.fill()
  }

  // Read grayscale accumulation, apply JET colormap
  const raw = octx.getImageData(0, 0, width, height).data
  const out = ctx.createImageData(width, height)
  const outData = out.data

  for (let i = 0; i < raw.length; i += 4) {
    const v = raw[i] // R channel = grayscale intensity
    // Higher threshold: cells with value ≤ ~20 become fully transparent
    if (v < 38) continue

    const lutIdx = Math.min(LUT_SIZE - 1, v) * 3
    outData[i]     = colorLUT[lutIdx]
    outData[i + 1] = colorLUT[lutIdx + 1]
    outData[i + 2] = colorLUT[lutIdx + 2]
    // Steeper power curve (2.2): low values nearly invisible, only true hotspots show colour
    // Max alpha 150 (~59% opacity) so camera is always visible through the overlay
    outData[i + 3] = Math.round(Math.pow(v / 255, 2.2) * 150 * (opacity / 100))
  }

  ctx.putImageData(out, 0, 0)
}

type Props = {
  cells: HeatmapCell[]
  gridRows: number
  gridCols: number
  opacity?: number
}

export function HeatmapCanvas({ cells, gridRows, gridCols, opacity = 100 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const propsRef = useRef({ cells, gridRows, gridCols, opacity })
  propsRef.current = { cells, gridRows, gridCols, opacity }

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || canvas.width === 0) return
    renderHeatmap(canvas, cells, gridRows, gridCols, opacity)
  }, [cells, gridRows, gridCols, opacity])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        canvas.width = Math.round(width)
        canvas.height = Math.round(height)
        const { cells: c, gridRows: r, gridCols: cols, opacity: op } = propsRef.current
        renderHeatmap(canvas, c, r, cols, op)
      }
    })
    ro.observe(canvas)
    return () => ro.disconnect()
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{ display: 'block', position: 'absolute', inset: 0, width: '100%', height: '100%' }}
    />
  )
}
