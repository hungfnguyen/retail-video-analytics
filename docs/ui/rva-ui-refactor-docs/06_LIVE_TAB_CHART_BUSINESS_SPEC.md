# Live Monitor Tab - Business Chart and Data Specification

This file defines which visual components should exist in the **Live Monitor** tab, what business question each component answers, which data it needs, and what user action it should support.

The goal is not to show all available realtime data. The goal is to help a store operator answer:

```text
What is happening right now?
Where is the problem?
Do I need to act?
What action should I take?
```

---

## 1. Target user

Primary user:

```text
Store supervisor / floor operator / security operator
```

They are not debugging the data pipeline. They need fast operational awareness.

They care about:

- current customer occupancy;
- queue pressure;
- longest waiting customer/session;
- active incidents;
- which camera/zone requires attention;
- whether staff should open another checkout lane or investigate a crowded area.

They do not primarily care about:

- model confidence;
- raw detection count;
- Trino table name;
- Flink/Pulsar state;
- FPS/debug latency, unless the system is failing.

Technical health belongs mainly in the **System** page.

---

## 2. Current data available

Use existing `useLiveData()` output.

Current useful fields:

```ts
data.stats.current_count
data.stats.updated_at
data.stats.status
data.stats.metadata_status
data.stats.media_status
data.stats.latency_ms

data.frame.camera_id
data.frame.image_url
data.frame.image_size
data.frame.zone_counts
data.frame.line_crossings
data.frame.detections

data.alerts
data.cameras

data.traffic
data.traffic_summary
data.zone_heatmap
```

Do not require backend changes for the first UI refactor. Add future-only sections as optional placeholders only when they are clearly marked as unavailable.

---

## 3. Recommended Live Monitor layout

```text
PageHeader
  Title: Live Monitor
  Subtitle: Store A · Updated HH:mm:ss
  Controls: Camera selector, Fullscreen, Refresh, Alert bell

KPI Row
  Visitors in Store | Queue Length | Longest Wait | Active Alerts | System Live Status

Main Grid
  Left:  Live Camera Evidence
  Right: Active Operations Panel

Secondary Grid
  Queue Status Table | Visitors Trend Today | Zone Occupancy

Optional Bottom
  Live Density Snapshot / Line Crossings
```

The camera should still be prominent, but the right-side action panel must make the page feel like an operations dashboard, not only a video viewer.

---

## 4. P0 visual components

### 4.1 Operational KPI row

| KPI | Business question | Current data | Display rule | User action |
|---|---|---|---|---|
| Visitors in Store | How busy is the store right now? | `stats.current_count`, fallback from `frame.zone_counts` | Large number + updated time | Decide whether store is unusually busy |
| Queue Length | How many people are waiting now? | Sum `zone_counts.count` where `zone_type === 'queue'` | Large number | Check checkout pressure |
| Longest Wait | Is anyone waiting too long? | Max `zone.max_wait_ms` for queue zones | Duration, red if over threshold | Open another checkout / assist cashier |
| Active Alerts | How many issues need review? | Count alerts where `status === 'new'` | Count + severity dot | Review high priority incidents |
| Live Status | Can I trust this data? | `media_status`, `metadata_status`, `stats.status` | `Live`, `Lagging`, `Offline`, `Warning` badge | Switch camera or inspect System page |

Recommended thresholds:

```ts
const QUEUE_WAIT_HIGH_SEC = 120
const QUEUE_WAIT_MEDIUM_SEC = 60
const ACTIVE_ALERT_HIGH = 3
```

Visual behavior:

- Use green for healthy/live.
- Use amber for attention.
- Use red for urgent action.
- Add small comparison text only when meaningful, for example `+18% vs previous hour` if data exists.
- Do not force comparison text if backend does not provide previous-period values.

---

### 4.2 Live Camera Evidence

Component type:

```text
Video / image evidence panel
```

Business question:

```text
What is the visual evidence behind the current metrics and alerts?
```

Current data:

```ts
frame.image_url
frame.image_size
frame.detections
frame.zone_counts
frame.camera_id
```

Required UI:

- camera feed with annotations;
- small `LIVE` status badge;
- camera name/zone in title;
- bottom toolbar for snapshot/fullscreen/mute if available;
- do not show raw debug labels in the main visual unless useful to the operator.

Recommended label style on boxes:

```text
#67 · 2.1m wait
```

instead of overly technical labels.

User action:

- verify a queue or crowding alert;
- switch camera;
- capture evidence;
- open alert detail.

---

### 4.3 Active Operations Panel

Component type:

```text
Prioritized alert/action list
```

Business question:

```text
What should I deal with first?
```

Current data:

```ts
data.alerts
```

Sort order:

```text
1. severity: high > medium > low
2. status: new before acknowledged/resolved
3. event_ts: latest first
```

Each alert card should show:

| Field | Data |
|---|---|
| Alert title | `alert.title` |
| Location | `alert.zone` + `alert.camera_id` |
| Severity | `alert.severity` |
| Time | relative `event_ts` |
| Suggested action | derived from `alert_type` |

Suggested action mapping:

| Alert type pattern | Suggested action |
|---|---|
| `long_wait` / title contains `Long wait` | Open another checkout lane or assist queue |
| `density` / title contains `density` | Check crowded area and remove obstruction |
| `line_crossing` | Review restricted zone crossing |
| unknown | Review camera evidence |

User action:

- click alert to open `AlertDetail`;
- acknowledge after review;
- understand priority without reading raw data.

---

### 4.4 Queue Status Table

Component type:

```text
Operational table + status badges
```

Business question:

```text
Which checkout queue needs staff intervention?
```

Current data:

```ts
frame.zone_counts.filter(zone => zone.zone_type === 'queue')
```

Columns:

| Column | Source | Business meaning |
|---|---|---|
| Queue | `zone.zone_name || zone.zone_id` | Checkout lane / queue zone |
| People | `zone.count` | Current people waiting |
| Avg wait | `zone.avg_wait_ms` | Normal wait pressure |
| Max wait | `zone.max_wait_ms` | Worst customer experience now |
| Status | derived threshold | Low / Medium / High |
| Action | derived threshold | Monitor / Prepare / Open lane |

Status logic:

```ts
if max_wait_sec >= 120 or count >= 4 => High
else if max_wait_sec >= 60 or count >= 2 => Medium
else Low
```

Visual:

- keep table compact;
- use red/amber/green badges;
- sort by status and max wait descending;
- highlight the top problematic queue.

User action:

- prioritize checkout intervention.

---

### 4.5 Visitors Trend Today

Component type:

```text
Line chart
```

Business question:

```text
Is traffic increasing, decreasing, or peaking right now?
```

Current data:

```ts
data.traffic
```

Recommended series:

| Series | Source | Meaning |
|---|---|---|
| Current visitors | `traffic.current_count` | live occupancy trend |
| People in | `traffic.people_in` | inbound flow |
| People out | `traffic.people_out` | outbound flow |

Chart rules:

- If space is limited, show only `current_count` as main line.
- Use `people_in` and `people_out` as optional thin lines or tooltip values.
- Show peak marker if `traffic_summary.peak_time` exists.
- Do not render an empty chart if there are fewer than 2 points.

User action:

- anticipate staffing demand;
- verify whether a queue issue is temporary or worsening.

---

### 4.6 Zone Occupancy Panel

Component type:

```text
Progress bars / ranked list
```

Business question:

```text
Which store areas are crowded right now?
```

Current data:

```ts
frame.zone_counts
```

Columns/fields:

| Field | Source |
|---|---|
| Zone name | `zone.zone_name || zone.zone_id` |
| Zone type | `zone.zone_type` |
| Current people | `zone.count` |
| Occupancy level | derived from count or configured capacity |

If zone capacity is unavailable, use relative occupancy:

```ts
zone_share = zone.count / max(1, total_zone_count)
```

Visual:

- ranked bars;
- queue zones should be visually separated from retail browsing zones;
- show top 5 zones only, with `View all` if needed.

User action:

- check congested area;
- understand distribution beyond the camera feed.

---

### 4.7 Line Crossing Activity

Component type:

```text
Small event feed
```

Business question:

```text
Are people entering, exiting, or crossing configured boundaries?
```

Current data:

```ts
frame.line_crossings
```

Display:

```text
Entrance Line: IN · 12s ago
Checkout Boundary: OUT · 22s ago
```

Do not overemphasize this component unless line crossings are a core business metric.

---

## 5. Components that should not dominate Live Monitor

Avoid making these primary UI elements on the Live tab:

| Technical data | Better location |
|---|---|
| FPS | System page |
| inference_ms / postprocess_ms | System page |
| model confidence | System page or debug overlay |
| Pulsar/Flink/Redis status | System page |
| raw detection count | Analyst/System depending context |

Live Monitor must be an operation page, not a technical telemetry page.

---

## 6. Implementation notes for Codex

Recommended components:

```text
features/live/components/LiveKpiRow.tsx
features/live/components/LiveOperationsPanel.tsx
features/live/components/QueueStatusTable.tsx
features/live/components/ZoneOccupancyPanel.tsx
features/live/components/LiveTrendCard.tsx
```

Can reuse existing components:

```text
VideoPanel.tsx
AlertList.tsx or AlertDetail.tsx
TrafficChart.tsx
ZoneRuntimePanel.tsx, partially
ZoneHeatmap.tsx, optional
```

Refactor rule:

```text
Preserve existing data fetching and behavior.
Change composition and labels first.
Only add new derived UI logic in frontend.
```

---

## 7. Acceptance checklist

Live Monitor is acceptable when:

- the user sees the most urgent problem without scrolling;
- queue status is clearer than the raw camera view alone;
- high severity alerts are visually prioritized;
- camera feed remains available as evidence;
- no primary card uses technical labels such as `Silver`, `detections`, or `confidence`;
- System/debug metrics are not mixed into store operations.
