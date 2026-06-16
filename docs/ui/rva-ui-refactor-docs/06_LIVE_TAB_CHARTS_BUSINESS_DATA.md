# Live Monitor Tab - Business Data and Chart Specification

This document defines what the **Live Monitor** tab should show, why each panel matters to the user, and which business data should drive it.

The goal is not to display every realtime field. The goal is to help a store operator answer:

```text
What is happening now?
Where is the problem?
What action should I take?
Can I verify it visually?
```

---

## 1. Target user

Primary user:

```text
Store manager / floor supervisor / security operator
```

They do not care about raw model internals such as FPS, detection confidence, Trino, Pulsar, or frame encoding latency on this page.

They care about:

- current occupancy;
- checkout queue pressure;
- long waits;
- active incidents;
- where the issue is happening;
- whether they should open another checkout lane, move staff, or review an alert.

Technical runtime data belongs to the **System** page, not the Live tab.

---

## 2. Live tab information hierarchy

Recommended screen order:

```text
Page header
  -> Store / camera selector / refresh status

KPI row
  -> Visitors in store
  -> Queue length
  -> Longest wait
  -> Active alerts
  -> Live freshness

Main operational grid
  -> Live camera evidence
  -> Active alerts + recommended actions

Secondary grid
  -> Queue status table
  -> Visitor trend today
  -> Zone occupancy
```

The page should prioritize **actionable state** over visual spectacle. The camera feed is evidence, not the whole product.

---

## 3. Required panels and charts

| Priority | Panel / chart | Business question | Visualization | Data source | User value |
|---|---|---|---|---|---|
| P0 | Live KPI row | Is the store operating normally right now? | Metric cards | `LiveDashboardData.stats`, `frame.zone_counts`, `alerts` | Fast situational awareness |
| P0 | Live camera evidence | Can I verify the issue visually? | Video/image panel with zone overlays | `frame.image_url`, `frame.detections`, `frame.zone_counts` | Trust and validation |
| P0 | Active alerts | What needs immediate review? | Sorted alert list | `alerts` | Triage incidents |
| P0 | Queue status table | Which checkout queue is problematic? | Table with status badges | `frame.zone_counts` filtered by `zone_type === 'queue'` | Staffing action |
| P1 | Visitors trend today | Is traffic increasing or decreasing now? | Line chart | `traffic`, `traffic_summary` | Staffing and crowd planning |
| P1 | Zone occupancy | Which area is crowded? | Horizontal bar chart | `frame.zone_counts` | Floor operation |
| P1 | Recommended actions | What should the operator do? | Rule-based action cards | Derived from queue + alerts | Converts data into decision |
| P2 | Live density snapshot | Where are people concentrated in camera view? | Small heatmap / density panel | `zone_heatmap` or `frame.heatmap_points` | Additional spatial context |

---

## 4. KPI row specification

### 4.1 Visitors in store

Business meaning:

```text
Estimated number of people currently visible / counted in the selected store or camera scope.
```

Use this instead of `Current count` if possible.

Data mapping:

```ts
const visitorsInStore = Math.max(
  data.stats.current_count,
  uniquePeopleFromZoneCounts(data.frame.zone_counts),
)
```

Display:

```text
Visitors in Store
248
Updated 10:30:45
```

Optional trend if data is available:

```text
+18% vs 30 minutes ago
```

Do not show:

```text
raw active_tracks
raw detections
model confidence
```

---

### 4.2 Queue length

Business meaning:

```text
Total number of people currently waiting in queue zones.
```

Data mapping:

```ts
const queueLength = data.frame.zone_counts
  .filter(z => z.zone_type === 'queue')
  .reduce((sum, z) => sum + Math.max(0, z.count), 0)
```

Display:

```text
Queue Length
7 people
Across 3 checkout queues
```

Threshold suggestions:

| Status | Condition |
|---|---|
| Normal | total queue length < 3 |
| Warning | total queue length between 3 and 6 |
| Critical | total queue length >= 7 |

These thresholds can be constants in the frontend until backend configuration exists.

---

### 4.3 Longest wait

Business meaning:

```text
The longest current wait time among checkout queues.
```

Data mapping:

```ts
const longestWaitSec = Math.max(
  0,
  ...queueZones.map(z => Math.floor(Math.max(0, z.max_wait_ms ?? 0) / 1000)),
)
```

Display:

```text
Longest Wait
2m 07s
Checkout Queue 03
```

Threshold suggestions:

| Status | Condition |
|---|---|
| Normal | < 60 seconds |
| Warning | 60-120 seconds |
| Critical | > 120 seconds |

Business action if critical:

```text
Consider opening another checkout lane.
```

---

### 4.4 Active alerts

Business meaning:

```text
Number of unresolved incidents that require review.
```

Data mapping:

```ts
const activeAlertCount = data.alerts.filter(a => a.status === 'new').length
const highAlertCount = data.alerts.filter(a => a.status === 'new' && a.severity === 'high').length
```

Display:

```text
Active Alerts
5
3 high priority
```

Sort order in alert list:

```text
High severity first
Newest first within severity
```

---

### 4.5 Live freshness

Business meaning:

```text
Can the user trust the live numbers right now?
```

Use fields:

```text
stats.updated_at
stats.metadata_status
frame.media_status
frame.capture_ts
```

Display options:

```text
Live
Data fresh - updated 2s ago
```

or:

```text
Lagging
Metadata delayed - last update 18s ago
```

This should be a small status chip in the header or KPI row.

---

## 5. Live camera evidence panel

The camera panel should answer:

```text
Where is the issue happening and can I verify it visually?
```

Recommended content:

- selected camera name;
- selected store/zone context;
- live status badge;
- annotated stream;
- small footer with camera id and timestamp;
- optional overlay toggles: boxes / zones / labels.

Data:

```text
frame.camera_id
frame.image_url
frame.image_size
frame.capture_ts
frame.detections
frame.zone_counts
```

Important UX rule:

```text
Do not let the camera feed push all operational insights below the fold.
```

Recommended layout:

```text
Desktop:
  camera: 60-65% width
  operations panel: 35-40% width

Laptop:
  camera first, alerts panel still visible above fold
```

---

## 6. Active alerts panel

The alert panel should not just list alerts. It should help triage.

Recommended fields:

```text
Title
Severity
Zone
Camera
Relative time
Short reason
Action button: View / Acknowledge
```

Sort logic:

```ts
const severityRank = { high: 3, medium: 2, low: 1 }
alerts.sort((a, b) =>
  severityRank[b.severity] - severityRank[a.severity]
  || new Date(b.event_ts).getTime() - new Date(a.event_ts).getTime()
)
```

Business-oriented examples:

```text
Long wait - Checkout Queue 03
Avg wait 2m07s
High

High density detected
Checkout area
High
```

Avoid vague technical messages such as:

```text
Incident clip - density high
```

Prefer:

```text
Crowding detected near checkout
5-second incident clip available
```

---

## 7. Queue status table

This is one of the most important business panels in the Live tab.

Recommended columns:

| Column | Meaning | Data |
|---|---|---|
| Queue | Business zone name | `zone.zone_name || zone.zone_id` |
| People | Current queue length | `zone.count` |
| Avg wait | Average wait for people in queue | `zone.avg_wait_ms` |
| Max wait | Longest current wait | `zone.max_wait_ms` |
| Status | Normal / Warning / Critical | derived |
| Action | Suggested action | derived |

Derived status:

```ts
function queueStatus(zone) {
  const maxWaitSec = (zone.max_wait_ms ?? 0) / 1000
  if (maxWaitSec > 120 || zone.count >= 5) return 'critical'
  if (maxWaitSec > 60 || zone.count >= 3) return 'warning'
  return 'normal'
}
```

Suggested action rules:

| Condition | Action text |
|---|---|
| Critical queue | Open another checkout lane |
| Warning queue | Monitor queue closely |
| Normal queue | No action needed |

---

## 8. Visitors trend today

Business question:

```text
Is the store getting busier or quieter during the current day?
```

Visualization:

```text
Line chart
```

Data:

```text
LiveDashboardData.traffic[]
traffic.time
traffic.current_count
traffic.people_in
traffic.people_out
```

Recommended chart:

- primary line: current occupancy;
- optional bars: people in / people out;
- show peak marker if `traffic_summary.peak_time` exists.

Do not overcomplicate this chart. It is a quick operational trend, not a full historical BI chart.

---

## 9. Zone occupancy panel

Business question:

```text
Which part of the store is crowded right now?
```

Visualization:

```text
Horizontal bar chart or ranked list
```

Data:

```text
frame.zone_counts
```

Recommended display:

```text
Checkout Area     78%  High
Beverage Aisle    62%  Medium
Entrance          38%  Low
```

If no capacity field exists, calculate relative share:

```ts
share = zone.count / maxZoneCount
```

Label it as:

```text
Relative occupancy
```

not absolute utilization.

---

## 10. Recommended actions panel

This can be a simple frontend-derived panel. No new AI is required.

Examples:

```text
Open another checkout lane
Reason: Checkout Queue 03 has max wait 2m07s.

Review high density alert
Reason: Checkout area triggered a high severity crowding event.

Monitor entrance area
Reason: sudden increase in occupancy in last few minutes.
```

This panel is optional but valuable because it converts analytics into user action.

Implementation can start with deterministic rules from existing data.

---

## 11. Data that should not be primary on Live tab

Avoid primary display of:

- model confidence;
- inference latency;
- draw latency;
- frame encode time;
- Pulsar/Flink/Trino state;
- container status;
- raw detection totals.

These belong to the System tab or technical debug views.

---

## 12. Empty and degraded states

The Live tab should handle:

### No live frame

```text
No live camera frame available.
Check Vision Service or camera source.
```

### Metadata stale

```text
Live video is available, but analytics metadata is delayed.
Last metadata update: 18s ago.
```

### No alerts

```text
No active alerts.
Store operation is normal.
```

### No queue zones

```text
No queue zones configured for this camera.
```

Do not show blank cards.

---

## 13. Acceptance criteria for Codex

The Live Monitor refactor is successful when:

- the user can identify the worst queue without scrolling;
- active alerts are visible above the fold;
- the camera feed remains available as evidence;
- queue wait time has clear severity status;
- no technical metrics dominate the Live tab;
- empty states are user-readable;
- existing camera switching and alert detail modal still work.
