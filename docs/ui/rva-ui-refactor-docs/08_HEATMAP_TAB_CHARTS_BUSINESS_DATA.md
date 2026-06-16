# Heatmap Tab - Business Data and Chart Specification

This document defines what the **Heatmap** tab should show, why it matters, and how to prevent it from becoming only a visually attractive but low-value screen.

The Heatmap tab should answer:

```text
Where do customers spend time?
Which zones are hot or cold?
When does congestion happen?
What business action should the store consider?
```

---

## 1. Target user

Primary users:

```text
Store manager
Retail analyst
Visual merchandiser
Operations planner
```

They care about:

- store layout performance;
- customer attention zones;
- congestion zones;
- underused areas;
- checkout pressure;
- whether product placement or staff allocation should change.

They do not care about the internal grid algorithm as the main story.

Technical labels such as `32x24 grid`, `silver_detections_v2`, and `log1p normalized` can exist as small metadata or tooltip, but should not dominate the UI.

---

## 2. Recommended Heatmap tab structure

```text
PageHeader: Heatmap
FilterBar: Camera / Area | Date Range | Layer | Refresh
Main grid:
  Left: Camera-view heatmap overlay
  Right: Heatmap insights + settings
Bottom:
  Top hotspots / Zone contribution / Time-of-day density
```

The heatmap image should remain the hero visual, but the user needs interpretation next to it.

---

## 3. Required controls

| Control | Business meaning | Implementation guidance |
|---|---|---|
| Camera / Area | Select physical camera coverage | current `cameraId` state |
| Date Range | Historical period | current `days` state |
| Layer | What the colors mean | start with `Visitors`; future: `Dwell`, `Queue pressure` |
| Opacity | Make overlay more/less visible | frontend-only setting |
| Show zones | Show/hide zone polygons/labels | if zone geometry exists |
| Show people count | Show/hide current detections | if overlay available |
| Refresh | Reload heatmap data | existing `refresh()` |

Do not expose raw metric names as primary labels.

Recommended labels:

```text
Visitors
Dwell Time
Queue Pressure
```

not:

```text
presence
log1p normalized
silver_detections_v2
```

---

## 4. Main heatmap overlay

### 4.1 Business question

```text
Where are customer presence hotspots in the selected camera area?
```

### 4.2 Visualization

```text
Camera snapshot background + transparent density overlay
```

### 4.3 Current data

```text
PresenceHeatmapData
- camera_id
- range_label
- grid_rows
- grid_cols
- cells[]
  - row
  - col
  - value
```

Image:

```text
/media/live/{cameraId}/snapshot.jpg
```

### 4.4 Display guidance

The main card title should be business-friendly:

```text
Customer presence density
```

Metadata can be small:

```text
Visitors layer · Last 7 days · normalized density
```

Avoid making this the main title:

```text
32x24 grid · silver_detections_v2 · log1p norm
```

That is a technical debug label.

---

## 5. Heatmap insight panel

This is the most important missing piece in the current design.

The panel should translate colors into business meaning.

Recommended insight cards:

| Insight | Business question | Data needed | Example output |
|---|---|---|---|
| Hottest area | Where is traffic concentrated? | max density cell mapped to zone | Checkout Queue 03 |
| Busiest time | When does the area peak? | hourly heatmap aggregation | 12:00 - 13:00 |
| Traffic concentration | Is traffic spread or concentrated? | top cells / total density | High concentration |
| Avg dwell in hot zone | Are people staying or just passing? | dwell layer / zone metric | 63s avg dwell |
| Queue pressure | Is heat caused by waiting? | queue metrics for queue zones | High wait pressure |

If zone mapping is not available yet, say:

```text
Hottest area: upper-right camera region
```

Do not pretend to know the business zone if the data does not provide it.

---

## 6. Top hotspots table

Business question:

```text
Which areas need attention first?
```

Visualization:

```text
Ranked table or compact horizontal bars
```

Recommended columns:

```text
Rank | Area / Zone | Density Share | Business Interpretation
```

Examples:

```text
1 | Checkout Queue 03 | 34% | Queue congestion
2 | Beverage Aisle | 21% | Strong product engagement
3 | Entrance | 15% | Normal entry flow
```

Current implementation path:

- If zone mapping exists, aggregate grid cells by zone.
- If zone mapping does not exist, show region names such as `Top-right`, `Center`, `Bottom-left`.
- Add a TODO for real zone mapping.

---

## 7. Zone contribution chart

Business question:

```text
How much of total presence belongs to each zone?
```

Visualization:

```text
Horizontal bar chart
```

Data needed:

```text
zone_id
zone_name
presence_score
presence_share
```

Future Gold source:

```text
gold.zone_metrics_daily
```

Fallback:

If only grid cells exist, aggregate by coarse camera regions.

Recommended labels:

```text
Checkout Queue 03    34%
Beverage Aisle       21%
Entrance             15%
```

Do not label raw grid cells as zones.

---

## 8. Time-of-day density chart

Business question:

```text
When does this area become crowded?
```

Visualization options:

```text
Option A: Hourly bar chart
Option B: Day-of-week x hour heatmap
```

Data needed:

```text
camera_id
hour_bucket
presence_score
```

Business value:

- staff planning;
- checkout scheduling;
- shelf restocking timing;
- campaign impact analysis.

This chart is optional for first refactor if backend does not provide hourly heatmap data.

---

## 9. Layer definitions

### 9.1 Visitors layer

Meaning:

```text
Where people were detected most often.
```

Current data:

```text
PresenceHeatmapData.cells.value
```

Good for:

- traffic density;
- layout flow;
- hotspot detection.

### 9.2 Dwell Time layer - future

Meaning:

```text
Where customers stayed longest.
```

Data needed:

```text
cell or zone dwell seconds
```

Good for:

- product engagement;
- promotion effectiveness;
- shelf interest.

### 9.3 Queue Pressure layer - future

Meaning:

```text
Where crowding is caused by waiting rather than browsing.
```

Data needed:

```text
queue zone wait metrics
queue length
max wait
```

Good for:

- checkout staffing;
- queue redesign;
- customer experience.

---

## 10. Normalization and legend

The heatmap legend should communicate business meaning.

Recommended legend:

```text
Low presence  ->  High presence
```

or:

```text
Low traffic  ->  High traffic
```

Use technical normalization details only in tooltip or metadata:

```text
Normalized using log1p to reduce extreme hotspot dominance.
```

Do not make users interpret raw numeric density values unless they ask.

---

## 11. Empty and degraded states

### No heatmap rows

```text
No traffic density data for this camera and date range.
Try a longer date range or check whether the Vision pipeline has produced Silver detection rows.
```

### Snapshot unavailable

```text
Camera snapshot is unavailable.
Heatmap data loaded, but the background image cannot be displayed.
```

### Zone mapping unavailable

```text
Zone-level interpretation is not available yet.
Showing camera-region hotspots instead.
```

### Backend unavailable

```text
Analytics warehouse is unavailable.
Trino may still be starting. Please refresh in a moment.
```

---

## 12. Data that belongs in Heatmap vs Analyst

### Heatmap tab should show

- spatial customer density;
- zone hotspots;
- traffic concentration;
- layer settings;
- camera-based visual evidence.

### Analyst tab should show

- historical traffic trends;
- queue KPIs;
- alert trends;
- day-of-week patterns;
- summary tables.

Do not duplicate the entire Analyst dashboard inside Heatmap. Heatmap should focus on **space**.

---

## 13. Future backend / Gold layer wishlist

To make Heatmap more business-grade, add these datasets later.

### gold.heatmap_cells_hourly

```text
store_id
camera_id
hour_bucket
grid_row
grid_col
presence_score
dwell_score
queue_pressure_score
```

### gold.zone_spatial_metrics_daily

```text
store_id
camera_id
zone_id
zone_name
business_date
presence_score
presence_share
avg_dwell_sec
max_occupancy
queue_wait_sec
```

### zone geometry metadata

```text
camera_id
zone_id
zone_name
zone_type
polygon_points
```

This allows the UI to explain hotspots by actual business zone names.

---

## 14. What not to do

Do not make the Heatmap tab only:

```text
image + colored overlay + low/high legend
```

That looks impressive but does not answer enough business questions.

Do not show technical text as the main value:

```text
32x24 grid · silver_detections_v2 · log1p normalized
```

Keep that as debug metadata.

Do not create fake zone insights unless the data supports zone mapping.

---

## 15. Acceptance criteria for Codex

The Heatmap tab refactor is successful when:

- the heatmap remains visually clear;
- the page explains what the hotspot means;
- users can identify the hottest area without guessing;
- layer/date/camera controls are clear;
- technical metadata is de-emphasized;
- empty states explain missing data;
- the design can grow from visitors density to dwell and queue pressure layers.
