# Heatmap Tab - Business Chart and Data Specification

This file defines the visual components and business data needed for the **Heatmap** tab.

The Heatmap tab should not only show a nice colored overlay. It should help the user answer:

```text
Where do customers spend time?
Which areas are overused or ignored?
Which zones may need layout, staffing, or promotion changes?
How does traffic concentration change by camera and date range?
```

---

## 1. Target user

Primary user:

```text
Store manager / retail analyst / layout planner
```

They care about:

- hot zones;
- cold zones;
- traffic concentration;
- dwell or presence intensity;
- checkout congestion areas;
- layout/promotion decisions.

They do not mainly care about:

- grid algorithm internals;
- raw cell values;
- exact model confidence;
- table names such as `silver_detections_v2`.

---

## 2. Current data available

Current API:

```ts
getPresenceHeatmapData(cameraId, days)
```

Current response shape:

```ts
type PresenceHeatmapData = {
  generated_at: string
  range_label: string
  camera_id: string
  data_status: 'ready' | 'empty' | 'error'
  error_message: string | null
  grid_rows: number
  grid_cols: number
  cells: HeatmapCell[]
}

type HeatmapCell = {
  row: number
  col: number
  value: number
}
```

Current UI also uses:

```text
/media/live/{cameraId}/snapshot.jpg
```

for the reference camera image.

---

## 3. Recommended Heatmap layout

```text
PageHeader
  Title: Heatmap
  Subtitle: Spatial traffic insights
  Controls: Camera selector, Date range, Refresh

Main Grid
  Left:  Camera Heatmap Overlay
  Right: Heatmap Settings + Insight Summary

Bottom Grid
  Top Hotspots | Zone Utilization | Time Pattern Summary
```

If screen width is limited, the insight panel can move below the image.

---

# 4. P0 visual components

## 4.1 Camera Heatmap Overlay

Chart type:

```text
Image overlay + canvas heatmap
```

Business question:

```text
Where are customers most concentrated in this camera view?
```

Current data:

```ts
data.cells
data.grid_rows
data.grid_cols
cameraId
snapshot.jpg
```

Display rules:

- keep the camera image visible;
- heatmap opacity should be adjustable;
- show a clear Low -> High legend;
- avoid technical label as primary text;
- display current period, for example `Last 7 days`;
- show loading/error/empty states clearly.

Recommended title:

```text
Traffic Density
```

Recommended subtitle:

```text
Customer presence intensity for selected camera and date range
```

Avoid primary title/subtitle like:

```text
32x24 grid · silver_detections_v2 · log norm
```

This can be moved to a small technical tooltip if needed.

Business action:

- identify high-traffic areas;
- evaluate whether checkout, shelf, or promotion placement is attracting attention;
- find bottlenecks.

---

## 4.2 Heatmap Settings Panel

Component type:

```text
Control panel
```

Business question:

```text
Can I adjust the visualization to inspect a specific behavior?
```

Current controls:

```text
Camera
Date Range
Refresh
```

Recommended controls:

| Control | Current support | Purpose |
|---|---|---|
| Camera | supported | choose physical viewpoint |
| Date Range | supported through `days` | compare recent vs longer pattern |
| Layer | future | switch Presence / Dwell / Queue Wait |
| Opacity | frontend only | make overlay easier to read |
| Show Zones | if zone polygons available | connect heatmap to store areas |
| Show People Count | optional | show current/live context |

For the first refactor, implement `Opacity` in frontend if simple. Mark `Layer` as disabled unless backend supports it.

---

## 4.3 Insight Summary Cards

Component type:

```text
Small KPI cards next to heatmap
```

Business question:

```text
What are the key takeaways from this heatmap?
```

Recommended cards:

| Card | Current data | Future ideal data | Business meaning |
|---|---|---|---|
| Hottest Area | max heatmap cell or mapped zone | zone with max traffic | Most concentrated area |
| Traffic Concentration | top 10% cell share | top zone share | Whether traffic is concentrated or spread out |
| Active Cells | count cells above threshold | active zones count | How much of the space is used |
| Suggested Focus | derived insight | rule-based recommendation | What user should inspect |

Current-data formulas:

```ts
maxCell = cell with highest value
activeCells = cells.filter(c => c.value >= threshold).length
activeCellRatio = activeCells / (grid_rows * grid_cols)
```

Traffic concentration approximate formula:

```ts
sorted = cells sorted by value desc
topN = ceil(cells.length * 0.1)
concentration = sum(sorted.slice(0, topN).value) / sum(all cell.value)
```

Suggested focus rule:

```text
If concentration is high -> "Traffic is concentrated in a small area. Check for bottleneck or promotion hotspot."
If active cell ratio is low -> "Large parts of this camera view have low activity. Review layout or camera coverage."
Else -> "Traffic is relatively distributed."
```

Do not overclaim exact business causality. Use careful wording.

---

## 4.4 Top Hotspots

Component type:

```text
Ranked list/table
```

Business question:

```text
Which areas should I inspect first?
```

Current data:

```ts
cells ranked by value
```

Better future data:

```ts
zone_id
zone_name
traffic_share
avg_dwell_sec
peak_hour
```

Current fallback display:

```text
Hotspot 1: Grid row 12, col 18
Hotspot 2: Grid row 13, col 18
```

Better if zone mapping is available:

```text
Checkout Queue 03 · 42% of traffic
Fresh Food · 18% of traffic
Entrance · 11% of traffic
```

Recommended columns:

```text
Rank
Area / Zone
Intensity
Share
Suggested action
```

Suggested action examples:

| Pattern | Suggested action |
|---|---|
| Hotspot near checkout | Check queue staffing |
| Hotspot near shelf/promotion | Validate product placement effectiveness |
| Hotspot in walkway | Check obstruction or congestion |
| Cold area | Consider layout/promotion change |

---

## 4.5 Zone Utilization

Component type:

```text
Horizontal progress bars
```

Business question:

```text
Which business zones are overused or underused?
```

Future ideal data:

```ts
type ZoneHeatmapSummary = {
  zone_id: string
  zone_name: string
  zone_type: string
  traffic_share: number
  avg_intensity: number
  avg_dwell_sec?: number
}
```

Current fallback:

- If zone polygon/cell mapping is not available, do not fake zone utilization.
- Show a placeholder: `Zone utilization requires zone-to-grid mapping`.

Business action:

- identify underperforming areas;
- compare checkout vs aisle vs entrance behavior;
- adjust layout.

---

## 4.6 Time Pattern Summary

Component type:

```text
Small bar chart / mini heatmap
```

Business question:

```text
When does this area become hot?
```

Future data needed:

```text
heatmap intensity by hour/day
```

Recommended visual options:

| Visual | Purpose |
|---|---|
| Hourly intensity bar chart | identify peak hours |
| Day-of-week mini heatmap | identify recurring busy days |
| Before/after comparison | compare layout or promotion periods |

Current fallback:

- Hide this section unless backend has time-bucketed heatmap data.
- Do not derive time pattern from a single aggregated heatmap.

---

# 5. P1/P2 advanced components

## 5.1 Layer switcher

Future layers:

```text
Presence Density
Dwell Time
Queue Wait
Alert Density
```

Business meaning:

| Layer | Business meaning |
|---|---|
| Presence Density | Where people appear most often |
| Dwell Time | Where people stay longest |
| Queue Wait | Where customer wait experience is worst |
| Alert Density | Where incidents happen most often |

Do not add layer options until backend can provide correct data.

---

## 5.2 Compare mode

Use case:

```text
Compare this week vs last week
Compare before vs after promotion
Compare cam_01 vs cam_02
```

Visual options:

- side-by-side heatmaps;
- delta heatmap;
- top changed zones table.

Business action:

- evaluate layout/promotion changes.

---

# 6. Data transformation rules

## 6.1 Normalize without hiding meaning

The backend may already return normalized/log-scaled values. UI should not over-normalize again unless necessary.

Display:

```text
Low -> High
```

rather than raw numeric cell values.

## 6.2 Thresholds

For active cell count:

```ts
threshold = max(10, p50_or_user_defined)
```

For hotspot list:

```ts
show top 5 cells or top 5 zones
```

## 6.3 Empty states

Use business-oriented empty states:

```text
No traffic data for this camera and date range.
Try a longer date range or verify the camera pipeline.
```

Avoid:

```text
No rows in silver_detections_v2
```

unless in a technical tooltip.

---

# 7. Labels to prefer

Use:

```text
Traffic Density
Hot Areas
Underused Areas
Top Hotspots
Zone Utilization
Presence Intensity
Selected Period
```

Avoid as primary labels:

```text
silver_detections_v2
log1p norm
32x24 grid
cell value
```

Technical information can be placed in a small `Data details` popover.

---

# 8. Implementation notes for Codex

Recommended components:

```text
features/heatmap/components/HeatmapToolbar.tsx
features/heatmap/components/HeatmapInsightPanel.tsx
features/heatmap/components/TopHotspotsPanel.tsx
features/heatmap/components/ZoneUtilizationPanel.tsx
features/heatmap/components/HeatmapSettingsPanel.tsx
```

Reuse existing:

```text
TrafficHeatmap.tsx
HeatmapCanvas.tsx
useHeatmapData.ts
```

Refactor approach:

```text
1. Keep existing heatmap rendering working.
2. Rename labels to business-friendly language.
3. Add insight panel from current cells.
4. Add opacity control if low risk.
5. Add placeholders only for unsupported future charts.
```

---

# 9. Acceptance checklist

Heatmap tab is acceptable when:

- user can identify hot areas without reading technical labels;
- heatmap has an insight panel explaining what matters;
- camera/date controls are clear;
- unsupported analytics are not faked;
- technical details are hidden or secondary;
- the page supports a business decision such as staffing, layout, or promotion evaluation.
