# Heatmap Tab - Business Charts and Data Specification

Target page:

```text
features/heatmap/HeatmapPage.tsx
```

Related current components:

```text
features/heatmap/components/TrafficHeatmap.tsx
features/heatmap/components/HeatmapCanvas.tsx
features/heatmap/hooks/useHeatmapData.ts
features/analytics/api/analyticsApi.ts
features/analytics/types.ts
```

Main data source:

```text
useHeatmapData(cameraId, days)
getPresenceHeatmapData(cameraId, days)
```

This document defines what the Heatmap tab should show and why each item matters to store users. The current visual overlay is valuable, but the page needs business interpretation so users know what action to take.

---

## 1. User and page purpose

Primary users:

```text
Store manager
Retail analyst
Merchandising planner
Operations lead
```

The Heatmap tab should answer:

1. Where do customers spend the most time?
2. Which zones are underused?
3. Which areas are congested?
4. Did traffic concentrate around checkout, entrance, or promotion areas?
5. What should the store change based on the heatmap?

The heatmap must be more than an attractive picture. It should become a store layout insight tool.

---

## 2. Business principle

The heatmap should connect visual density to decisions:

```text
Move staff to crowded checkout zones.
Improve signage for low-traffic aisles.
Place promotions in high-visibility areas.
Investigate bottlenecks near entrance or checkout.
```

Avoid exposing only technical implementation labels:

```text
32x24 grid
silver_detections_v2
log1p normalized
raw cell values
```

These may appear in a tooltip or small source badge, not as the primary message.

---

## 3. Recommended Heatmap layout

```text
PageHeader
  title: Heatmap
  subtitle: Customer presence and zone activity
  controls: Store, Camera, Date Range, Layer, Refresh

Main grid
  Left: Camera heatmap overlay
  Right: Heatmap Insights Panel

Lower grid
  Top Hotspots | Zone Activity Ranking | Intensity Distribution or Time Comparison
```

The right-side insight panel is essential. Without it, the heatmap is hard to interpret for non-technical users.

---

## 4. Filter and control design

Current controls:

```text
cam_01 cam_02 | 1d 7d 14d 30d | refresh
```

Target controls:

```text
Store: Store A
Camera: Cam 1 - Checkout Area
Date Range: Last 7 days
Layer: Visitor Presence
Refresh
```

Recommended type:

```ts
type HeatmapLayer = 'presence' | 'dwell' | 'queue_wait'

type HeatmapFilters = {
  storeId: string
  cameraId: string
  dateRange: 'today' | 'yesterday' | 'last_7_days' | 'last_14_days' | 'last_30_days'
  layer: HeatmapLayer
}
```

Current backend only supports:

```text
metric=presence
```

Implementation rule:

- Enable only `Visitor Presence` layer now.
- Show `Dwell Time` and `Queue Wait` as disabled future options if desired.
- Do not pretend unsupported layers work.

---

## 5. Primary chart: Camera Heatmap Overlay

Current component:

```text
TrafficHeatmap.tsx + HeatmapCanvas.tsx
```

Business question:

```text
Where is customer presence concentrated in this camera view?
```

Data source:

```ts
PresenceHeatmapData.cells
PresenceHeatmapData.grid_rows
PresenceHeatmapData.grid_cols
camera snapshot image
```

Current data type:

```ts
type HeatmapCell = {
  row: number
  col: number
  value: number
}
```

Display title:

```text
Customer Presence Heatmap
```

Subtitle:

```text
Higher intensity means more observed customer presence during the selected period.
```

Source badge:

```text
Gold/Silver lakehouse source
Last 7 days
```

Avoid using the main badge text:

```text
32x24 grid - silver_detections_v2 - log1p norm
```

If needed, move that to tooltip:

```text
Technical details: 32x24 grid, log normalized from silver detections.
```

User action:

- Identify hotspots and cold areas.
- Use heatmap to validate store layout, checkout bottlenecks, and promotion placement.

---

## 6. Heatmap Insights Panel

Component to create:

```text
features/heatmap/components/HeatmapInsightsPanel.tsx
```

Purpose:

```text
Explain the heatmap in business language.
```

Inputs:

```ts
data: PresenceHeatmapData
cameraId: string
days: number
```

Recommended insight cards:

### 6.1 Hottest Area

Business question:

```text
Where is the highest concentration of customer presence?
```

Current derivation from grid:

```ts
hottestCell = max cells by value
hotspotRegion = group nearby high-value cells if implemented
```

Display:

```text
Hottest Area
Right checkout lane
High concentration
```

If zone mapping is not available:

```text
Hottest Area
Grid row 12, col 18
```

But prefer business zone names when possible.

Future preferred data:

```text
cell to zone mapping or zone polygons
```

---

### 6.2 Traffic Concentration Score

Business question:

```text
Is traffic spread evenly, or concentrated in a few areas?
```

Simple derivation:

```ts
topCells = top 10 percent of cells by value
concentrationScore = sum(topCells.value) / sum(allCells.value)
```

Display:

```text
Traffic Concentration
High
Top 10% of areas contain 62% of observed presence
```

User value:

- High concentration suggests congestion or strong attraction.
- Low concentration suggests more even movement.

---

### 6.3 Low Activity Area

Business question:

```text
Which visible area receives little customer attention?
```

Derivation:

```ts
coldCells = cells with value below low threshold
coldRegion = largest connected low-value region if implemented
```

Display:

```text
Low Activity Area
Left aisle area
Consider signage or product placement review
```

Do not show this if there is not enough coverage or if the camera view does not cover that area clearly.

---

### 6.4 Data Coverage

Business question:

```text
Is there enough data to trust this heatmap?
```

Data source:

```ts
cells.length
grid_rows
grid_cols
generated_at
```

Derived:

```ts
coverage = cells with value > 0 divided by grid_rows * grid_cols
```

Display:

```text
Data Coverage
68% active grid cells
Updated 10:30
```

User value:

- Helps avoid over-interpreting sparse data.

---

## 7. Top Hotspots chart

Component to create:

```text
features/heatmap/components/TopHotspotsPanel.tsx
```

Recommended chart:

```text
Ranked list or horizontal bar chart
```

Business question:

```text
What are the top areas by customer presence?
```

Current possible data:

```ts
HeatmapCell[]
```

Future preferred data:

```text
zone_name
presence_score
share_percent
avg_dwell_sec
```

Current derivation without zone mapping:

```ts
bucket hot cells into regions
or show Top Grid Areas with row/col labels
```

Recommended display with zone names:

```text
1. Checkout Queue 03 - 42% share
2. Checkout Counter 01 - 25% share
3. Entrance Path - 18% share
```

If only grid cells are available:

```text
1. Area R12-C18 - high
2. Area R13-C18 - high
3. Area R10-C21 - medium
```

Implementation note:

Zone names are much better for users. If the backend already knows polygons, expose a zone heatmap summary endpoint later.

---

## 8. Zone Activity Ranking

Chart type:

```text
Horizontal bar chart or table
```

Business question:

```text
Which business zones are most active in the selected period?
```

Preferred data:

```text
gold zone heatmap summary
```

Fields:

```text
zone_id
zone_name
presence_score
share_percent
rank
```

User action:

- Evaluate store layout.
- Compare promotion zones.
- Find underused areas.

Current fallback:

If no zone summary exists, show an empty/future state:

```text
Zone activity ranking requires heatmap-to-zone mapping.
```

Do not incorrectly derive business zones from grid cells unless there is a reliable mapping.

---

## 9. Intensity Distribution chart

Chart type:

```text
Histogram
```

Business question:

```text
Is the traffic pattern concentrated or evenly distributed?
```

Current data:

```ts
cells.map(c => c.value)
```

Fields:

```text
x: intensity bucket
y: number of cells
```

User value:

- Helps explain if only a few areas dominate.
- Supports the concentration score.

Design note:

This is a secondary analytical chart. Do not make it more prominent than the visual heatmap or top hotspots.

---

## 10. Time Comparison panel

Chart type:

```text
Comparison cards or small multiples
```

Business question:

```text
Did the traffic pattern change compared with the previous period?
```

Preferred future data:

```text
current period heatmap summary
previous period heatmap summary
```

Metrics:

```text
hottest zone changed from X to Y
concentration score changed +12%
active area coverage changed -8%
```

Current implementation:

Do not implement if backend cannot provide previous period data. Add as future requirement.

---

## 11. Layer design

### 11.1 Visitor Presence layer

Supported now.

Meaning:

```text
Where people were observed most often.
```

Data source:

```text
/api/v1/analytics/heatmap?metric=presence
```

### 11.2 Dwell Time layer

Future.

Meaning:

```text
Where people stayed longest.
```

Required backend data:

```text
avg_dwell_sec by grid cell or zone
```

Business value:

- Measure engagement.
- Evaluate product displays or promotion areas.

### 11.3 Queue Wait layer

Future.

Meaning:

```text
Where waiting time accumulates.
```

Required backend data:

```text
avg_wait_sec or total_wait_sec by queue zone/grid cell
```

Business value:

- Identify queue bottlenecks.
- Support staffing decisions.

Implementation rule:

Disabled layers should explain why they are disabled:

```text
Requires dwell-time heatmap aggregation.
```

---

## 12. Heatmap settings

Optional settings panel:

```text
Layer
Opacity
Color scale
Show zones
Show people boxes
```

Recommended defaults:

```text
Layer: Visitor Presence
Opacity: 70%
Color scale: Blue to Red
Show zones: On
Show people boxes: Off for historical heatmap
```

Why turn people boxes off by default?

Historical heatmap is about aggregate movement, not individual detections. Boxes can distract from the aggregate pattern.

---

## 13. Empty and error states

### No heatmap data

```text
No visitor presence data for this camera and period.
Try a longer date range or verify that the pipeline is writing Silver detections.
```

### Backend unavailable

```text
Lakehouse analytics is unavailable. Trino may still be starting.
```

### Sparse data

```text
Only limited activity was observed in this period. Use a longer date range for a reliable heatmap.
```

### Unsupported layer

```text
Dwell Time heatmap is not available yet. Backend aggregation is required.
```

---

## 14. What not to show as primary UI

Do not make these primary labels:

```text
silver_detections_v2
log1p norm
32x24 grid
raw cells
cell row/col ids
```

Good user-facing labels:

```text
Visitor Presence
Customer Density
Top Hotspots
High Activity Area
Low Activity Area
Data Coverage
```

Technical details can appear in:

```text
small source badge
tooltip
System page
```

---

## 15. Backend-friendly phased implementation

### Phase 1 - Frontend only, current heatmap API

Implement:

- Better title/subtitle.
- Date range dropdown mapped to `days`.
- Camera dropdown with business names if available.
- Heatmap overlay unchanged.
- Insight panel derived from cells.
- Top grid hotspots derived from cells.
- Data coverage metric.

### Phase 2 - Zone mapping

Add backend support for:

```text
zone_name per heatmap cell
zone heatmap summary
```

Then implement:

- Top hotspots by zone.
- Zone activity ranking.
- More useful insight text.

### Phase 3 - Additional layers

Add backend support for:

```text
dwell heatmap
queue wait heatmap
previous period comparison
```

Then enable layer selector.

---

## 16. Minimum implementation checklist

Create or refactor:

```text
features/heatmap/components/HeatmapInsightsPanel.tsx
features/heatmap/components/TopHotspotsPanel.tsx
features/heatmap/components/HeatmapSettingsPanel.tsx
features/heatmap/components/HeatmapSummaryCards.tsx
```

Keep:

```text
TrafficHeatmap.tsx
HeatmapCanvas.tsx
useHeatmapData.ts
```

Acceptance criteria:

1. User can identify the hottest area without interpreting raw colors manually.
2. User can see whether the data is reliable enough to trust.
3. The heatmap explains business meaning, not only rendering implementation.
4. Unsupported future layers are clearly marked and not faked.
5. Current backend API continues to work.
