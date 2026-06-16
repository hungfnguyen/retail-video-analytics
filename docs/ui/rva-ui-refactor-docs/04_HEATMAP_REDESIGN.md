# Heatmap Redesign Plan

Target file:

```text
features/heatmap/HeatmapPage.tsx
```

Current related files:

```text
features/heatmap/components/TrafficHeatmap.tsx
features/heatmap/components/HeatmapCanvas.tsx
features/heatmap/hooks/useHeatmapData.ts
features/analytics/api/analyticsApi.ts
features/analytics/types.ts
```

---

## 1. Page purpose

Heatmap page should answer:

- Where do customers spend most time?
- Which zones are congested?
- What are the hottest areas in the selected period?
- What should the store manager do with this spatial insight?

Current heatmap overlay is visually strong. The missing part is insight and action.

Target:

```text
Visual heatmap + business interpretation + controls
```

---

## 2. Current issues

Current page has:

```text
Camera selector
Days selector
Refresh button
TrafficHeatmap with overlay
Low -> High legend
```

Issues:

1. It shows the heatmap but does not explain what it means.
2. It exposes technical label `silver_detections_v2` and `log norm` in the main UI.
3. There is no side panel with top hotspots or interpretation.
4. Camera/date controls are separate from Analytics filter style.
5. No layer/opacity controls.

---

## 3. Target layout

Recommended layout:

```text
PageHeader: Heatmap                         [Camera] [Date Range] [Refresh]

Main grid:
+------------------------------------------------------+---------------------------+
| Traffic Density Map                                  | Heatmap Settings          |
| Camera snapshot + heatmap overlay                    | Insight Summary           |
| Legend                                               | Top Hotspots              |
+------------------------------------------------------+---------------------------+

Bottom grid:
+------------------------------------+------------------------------------+
| Hourly Hotspot Pattern             | Zone Summary                       |
+------------------------------------+------------------------------------+
```

If backend only supports current heatmap cells, implement the main grid and insight panel with partial derived data.

---

## 4. Header and filters

Replace current segmented controls with shared `FilterBar` style.

For Heatmap, controls should be:

```text
Camera: Cam 1 - Checkout Area
Date Range: Last 7 days
Refresh
```

Optional later controls:

```text
Layer: Visitors | Dwell | Queue Wait
Opacity: slider
Normalize: Linear | Log
Show zones: checkbox
Show people count: checkbox
```

Current backend only supports:

```text
camera_id
days
metric=presence
```

Therefore Phase 1 should implement:

- Camera selector.
- Date range selector mapped to days.
- Refresh button.
- Optional opacity purely client side.

Do not add layer dropdown unless it is disabled or only has one supported value.

---

## 5. Main heatmap card

Current `TrafficHeatmap` can be refactored into:

```text
HeatmapViewer
HeatmapControlsPanel
HeatmapInsightPanel
```

Recommended component structure:

```text
HeatmapPage
  PageHeader
  HeatmapMainGrid
    HeatmapViewer
      CameraSnapshot
      HeatmapCanvas
      Legend
    HeatmapSidePanel
      HeatmapSettings
      HeatmapInsights
      TopHotspots
  HeatmapSecondaryGrid
```

---

## 6. Heatmap viewer improvements

Keep `HeatmapCanvas` logic if it already works.

Improve viewer UI:

- Clear title: `Traffic Density Map`.
- Subtitle: `Presence density from selected camera and period`.
- Badge: `Gold/Silver source` should be small and not dominant.
- Overlay legend under image.
- Optional top-left timestamp/camera label.

Replace technical label:

```text
32x24 grid - silver_detections_v2 - log norm
```

with:

```text
Presence density - normalized
```

Move technical source into a tooltip or small data source label:

```text
Data source: Silver detections, 32x24 grid, log normalized
```

---

## 7. Heatmap settings panel

Create component:

```text
features/heatmap/components/HeatmapSettingsPanel.tsx
```

Controls:

```text
Layer: Presence density (disabled unless more layers exist)
Opacity: 0% - 100%
Normalization: Log (read only or dropdown if supported)
Show zones: checkbox
Show detection boxes: checkbox if snapshot has boxes, otherwise hide
```

Props:

```ts
type HeatmapSettings = {
  opacity: number
  showZones: boolean
  showPeopleCount: boolean
  normalization: 'log' | 'linear'
  layer: 'presence'
}
```

Phase 1: only `opacity` needs to actually affect UI. Others can be disabled or hidden.

Update `HeatmapCanvas` to accept opacity multiplier:

```ts
type Props = {
  cells: HeatmapCell[]
  gridRows: number
  gridCols: number
  opacity?: number
}
```

Then multiply alpha by opacity.

---

## 8. Heatmap insights panel

Create component:

```text
features/heatmap/components/HeatmapInsightsPanel.tsx
```

Purpose:

- Translate visual blobs into business language.

Derived data from cells:

```ts
const maxCell = max by value
const avgValue = average cell value
const hotCellCount = count value >= threshold
const concentrationScore = top 10% cell sum / total sum
```

Suggested insights:

```text
Hottest area: lower-right checkout lane
Traffic concentration: High
Number of hotspots: 4
Recommended action: Review checkout queue staffing during peak period
```

If there is no zone mapping, do not name zones incorrectly. Use spatial language:

```text
top-left area
center aisle
lower-right area
```

If zone polygons are available from backend later, map cell coordinates to zone names.

---

## 9. Top hotspots list

Create component:

```text
features/heatmap/components/TopHotspotsList.tsx
```

Input:

```ts
cells: HeatmapCell[]
gridRows: number
gridCols: number
```

Output top 3-5 hotspots:

```text
1. Lower-right area - high density
2. Center checkout lane - medium density
3. Right shelf area - medium density
```

Client-side location labeling:

```ts
function describeCellLocation(row, col, gridRows, gridCols) {
  const vertical = row < gridRows / 3 ? 'upper' : row > (gridRows * 2) / 3 ? 'lower' : 'middle'
  const horizontal = col < gridCols / 3 ? 'left' : col > (gridCols * 2) / 3 ? 'right' : 'center'
  return `${vertical}-${horizontal} area`
}
```

Keep labels simple.

---

## 10. Secondary panels

Only add secondary panels if useful data is available.

Potential panels:

### 10.1 Hotspot summary

```text
Metric cards:
- Hotspot count
- Concentration score
- Max density
- Active camera
```

### 10.2 Zone summary

If zone aggregation is available:

```text
Zone | Density share | Dwell | Status
```

If not available, show empty state:

```text
Zone-level heatmap summary requires Gold zone aggregates.
```

### 10.3 Time pattern

If hourly heatmap is available later:

```text
Peak hours by area
```

Do not invent this from a single aggregated heatmap.

---

## 11. Data adapter

Create:

```text
features/heatmap/adapters/heatmapViewModels.ts
```

Functions:

```ts
export function getHeatmapStats(data: PresenceHeatmapData | null): HeatmapStats
export function getTopHotspots(data: PresenceHeatmapData | null, limit = 5): HotspotItem[]
export function describeCellLocation(row: number, col: number, rows: number, cols: number): string
```

Types:

```ts
type HeatmapStats = {
  maxValue: number
  averageValue: number
  hotspotCount: number
  concentrationScore: number
  dataAvailable: boolean
}

type HotspotItem = {
  id: string
  label: string
  value: number
  intensity: 'low' | 'medium' | 'high'
}
```

---

## 12. Error and empty states

Heatmap states:

```text
Loading -> skeleton overlay or centered spinner
No data -> clear empty state with selected camera/range
Error -> Data warehouse unavailable, refresh button
Image missing -> Camera snapshot unavailable
Cells missing -> No heatmap data for selected period
```

Keep the page stable. Do not collapse layout when data is unavailable.

---

## 13. Implementation steps for Codex

1. Add shared `PageHeader`, `FilterBar`, `SectionCard`, `EmptyState` if not already done.
2. Create `HeatmapFilterBar` or use shared FilterBar with camera/date only.
3. Refactor `HeatmapPage.tsx` to use new layout.
4. Refactor `TrafficHeatmap.tsx` into `HeatmapViewer` or keep it and add side panel around it.
5. Add `HeatmapSettingsPanel.tsx` with opacity state.
6. Add `HeatmapInsightsPanel.tsx` and adapter functions.
7. Add `TopHotspotsList.tsx`.
8. Update `HeatmapCanvas` to accept opacity safely.
9. Run build.

---

## 14. Acceptance criteria

Heatmap page is done when:

- Heatmap remains visually clear.
- User gets top hotspots and summary insight without interpreting colors manually.
- Camera/date filter matches overall UI style.
- Technical table names are not prominent.
- Empty/error states are clear.
- Opacity control works or is not displayed.
