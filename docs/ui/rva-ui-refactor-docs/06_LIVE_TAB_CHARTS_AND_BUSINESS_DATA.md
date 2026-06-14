# Live Monitor Tab - Business Charts and Data Specification

Target page:

```text
features/live/LivePage.tsx
```

Related current components:

```text
features/live/components/LiveMetricCards.tsx
features/live/components/VideoPanel.tsx
features/live/components/AlertList.tsx
features/live/components/ZoneRuntimePanel.tsx
features/live/components/TrafficChart.tsx
features/live/components/ZoneHeatmap.tsx
features/live/types.ts
```

Main data source:

```text
useLiveData()
```

This document defines what the Live Monitor tab should show and why each item is useful to a store user. The goal is not to show every available field. The goal is to support immediate operational decisions.

---

## 1. User and page purpose

Primary user:

```text
Store supervisor / floor manager / operations staff
```

The Live Monitor tab should answer these questions in less than 10 seconds:

1. Is the store busy right now?
2. Which queue or zone needs attention?
3. Are there active incidents?
4. What evidence supports the alert?
5. What action should the staff take?

The page should feel like an operations command center, not a computer vision debug screen.

---

## 2. Business principle

Prioritize user decisions over raw telemetry.

Good Live Monitor data:

```text
Queue 03 wait time is high.
Open another checkout counter.
There are 5 active alerts.
Checkout area is the most crowded zone.
```

Bad primary Live Monitor data:

```text
Detection confidence is 83.3%.
Pulsar latency is 12 ms.
Silver table row count is 12826.
JPEG size is 400 KB.
```

Technical telemetry belongs in the System page unless it directly affects the manager's ability to trust the current screen.

---

## 3. Recommended Live layout

```text
PageHeader
  title: Live Monitor
  subtitle: Store A - realtime operations
  controls: Store selector, Camera selector, Refresh, Live status

KPI row
  Visitors in Store | Avg Queue Wait | Longest Wait | Active Alerts | Data Freshness

Primary grid
  Left: Live Camera Evidence
  Right: Operations Panel

Secondary grid
  Queue Status Table | Visitor Trend Today | Zone Occupancy

Optional lower section
  Small Live Density Snapshot or recent line crossings
```

The camera is important evidence, but it should not be the only thing the user sees.

---

## 4. KPI cards

### 4.1 Visitors in Store

Business question:

```text
How busy is the store right now?
```

Data source:

```ts
data.stats.current_count
data.frame.zone_counts
```

Current code already computes a safer current count by taking the max of stats.current_count and zone occupancy. Keep that idea.

Display:

```text
Visitors in Store
248
Live count from selected camera / zones
```

Derived value:

```ts
currentVisitors = max(stats.current_count, uniqueGlobalIdsFromZonesOrZoneCountSum)
```

Trend indicator:

Use `stats.count_change_percent` if reliable.

```text
+18% vs last interval
```

User action:

- If visitors are high and queue wait is high, user may open more checkout counters.
- If visitors are high but queue wait is low, operations are healthy.

Empty state:

```text
No live count yet
```

Do not label it as `detections`.

---

### 4.2 Average Queue Wait

Business question:

```text
Are customers waiting too long right now?
```

Data source:

```ts
data.frame.zone_counts[].avg_wait_ms
data.frame.zone_counts[].zone_type === 'queue'
```

Derived value:

```ts
queueZones = zone_counts where zone_type === 'queue'
avgQueueWaitMs = weighted average by zone.count if possible
fallback = average of avg_wait_ms values greater than 0
```

Display:

```text
Avg Queue Wait
2m 07s
+32s vs previous interval
```

Priority rule:

This KPI is more important than generic `Queue length`, because a queue of 2 people can still be bad if both are waiting too long.

Threshold examples:

```text
0-60s: Healthy
61-120s: Watch
>120s: Action needed
```

User action:

- Assign staff to checkout.
- Investigate slow checkout lane.
- Trigger service recovery if threshold is exceeded.

---

### 4.3 Longest Wait

Business question:

```text
Is any customer currently experiencing a bad waiting experience?
```

Data source:

```ts
data.frame.zone_counts[].max_wait_ms
```

Derived value:

```ts
maxWaitMs = max(queueZones.map(z => z.max_wait_ms ?? 0))
slowestZone = zone with maxWaitMs
```

Display:

```text
Longest Wait
3m 12s
Checkout Queue 03
```

User action:

- Prioritize the slowest queue, not the largest queue.

Design note:

Show this in amber/red when threshold is breached.

---

### 4.4 Active Alerts

Business question:

```text
How many issues require human review now?
```

Data source:

```ts
data.alerts.filter(a => a.status === 'new')
```

Display:

```text
Active Alerts
5
3 high priority
```

Derived sub-metrics:

```ts
activeAlerts = alerts where status === 'new'
highAlerts = activeAlerts where severity === 'high'
```

User action:

- Click to inspect alert details.
- Acknowledge alert after verification.

Do not hide high alerts below the fold.

---

### 4.5 Data Freshness

Business question:

```text
Can the user trust this live view right now?
```

Data source:

```ts
data.stats.updated_at
data.stats.metadata_status
data.frame.media_status
data.frame.metadata_latency_ms
data.frame.media_latency_ms
```

Display:

```text
Live Status
Fresh
Updated 10:30:45
```

Rules:

```text
fresh + online: green
lagging or warning: amber
stale, missing, offline: red
```

User action:

- If stale, manager should not rely on the view.
- Direct user to System page only when necessary.

---

## 5. Primary evidence panel: Live Camera

Component:

```text
VideoPanel
```

Business question:

```text
What is happening visually, and does it support the metrics?
```

Data source:

```ts
data.frame.image_url
data.frame.detections
data.frame.zone_counts
data.cameras
data.selected_camera_id
```

Required UI behavior:

1. Keep the video large enough to verify incidents.
2. Add a clear label for selected camera and business area.
3. Show live badge only if data is fresh.
4. Keep bounding boxes visible but not visually overwhelming.
5. Provide full-screen action if possible.

Recommended title:

```text
Live Camera - Cam 1 - Checkout Area
```

Do not show internal frame id or raw inference timing in this card.

---

## 6. Operations Panel

This is the most important new panel for Live Monitor.

Purpose:

```text
Convert live metrics into prioritized operational tasks.
```

Recommended items:

### 6.1 Critical Queue Alert

Data source:

```ts
queue zone with highest max_wait_ms
```

Display:

```text
Action needed
Checkout Queue 03 wait time is 3m 12s.
Recommendation: Open another checkout counter.
```

### 6.2 High Density Area

Data source:

```ts
zone_counts sorted by count desc
```

Display:

```text
Crowded area
Checkout Area has 78% occupancy.
Recommendation: Send staff to assist.
```

### 6.3 Active Incident

Data source:

```ts
high severity active alerts
```

Display:

```text
Incident detected
High density detected near checkout.
Review evidence.
```

Implementation note:

Create component:

```text
features/live/components/LiveOperationsPanel.tsx
```

Inputs:

```ts
alerts: Alert[]
zoneCounts: ZoneCount[]
stats: LiveStats
```

Output should be a ranked list of 3 to 5 actions.

---

## 7. Queue Status Table

Component to create or refactor:

```text
features/live/components/QueueStatusTable.tsx
```

Business question:

```text
Which queue should staff handle first?
```

Data source:

```ts
data.frame.zone_counts where zone_type === 'queue'
```

Columns:

```text
Queue | People | Avg Wait | Longest Wait | Status | Trend
```

Recommended derivations:

```ts
people = zone.count
avgWait = zone.avg_wait_ms
longestWait = zone.max_wait_ms
status = based on longestWait or avgWait threshold
```

Status thresholds:

```text
Low: longest wait <= 60s
Medium: 61s to 120s
High: > 120s
```

Sort order:

```text
High status first, then longest wait desc, then people desc
```

User action:

- The top row should be the queue to address first.

Design note:

Use compact rows and a clear severity badge.

---

## 8. Visitor Trend Today

Component:

```text
TrafficChart.tsx
```

Business question:

```text
Is traffic increasing or decreasing during the day?
```

Data source:

```ts
data.traffic
data.traffic_summary
```

Recommended chart:

```text
Line chart
```

Series:

```text
current_count or people_in
optional people_out if reliable
```

Preferred display:

```text
Visitor Trend Today
```

Use this chart to answer:

- Are we approaching a peak?
- Did traffic suddenly drop?
- Is staffing adequate for the next hour?

Do not use this as a pure technical throughput chart.

---

## 9. Zone Occupancy Panel

Component to create or refactor:

```text
features/live/components/ZoneOccupancyPanel.tsx
```

Business question:

```text
Which parts of the store are currently crowded?
```

Data source:

```ts
data.frame.zone_counts
```

Recommended visualization:

```text
Horizontal progress bars sorted by occupancy/count
```

Fields:

```text
Zone name
Current people count
Zone type
Occupancy level
```

If true capacity is not available:

- Show count-based ranking.
- Do not claim percentage occupancy unless capacity exists.
- If you show a percent, label it as `relative activity`, not occupancy.

Sort order:

```text
count desc
```

User action:

- Send staff to crowded zones.
- Compare queue zones against general shopping zones.

---

## 10. Live Density Snapshot

Current component:

```text
ZoneHeatmap.tsx
```

Business question:

```text
Where is live activity concentrated?
```

Recommendation:

Use it as a compact supporting card, not a primary chart.

Better title:

```text
Live Activity Density
```

Do not show only colored blocks without interpretation. Add one sentence:

```text
Highest activity: Checkout Queue 03
```

---

## 11. Active Alerts list

Current component:

```text
AlertList.tsx
```

Business question:

```text
Which incident should be reviewed first?
```

Required behavior:

- Sort high severity first.
- Then newest first.
- Show title, zone, camera, time, severity.
- Click opens alert detail with snapshot or clip.

Recommended labels:

```text
Active Alerts
```

instead of:

```text
New alerts
```

because the user cares about open work, not just new events.

---

## 12. Filters and controls

Live page should keep controls simple.

Recommended controls:

```text
Store selector
Camera selector
Auto-refresh state
Manual refresh
Live/Delayed badge
```

Do not add heavy historical filters to Live. Historical analysis belongs in Analyst.

---

## 13. What not to show on Live

Do not make these primary:

```text
Detection confidence
Raw frame id
Inference ms
Postprocess ms
JPEG size
Pulsar backlog
Trino status
Silver row count
```

These are useful for developers, not store users. Move them to System.

---

## 14. Empty and degraded states

### No camera frame

```text
No live camera frame available.
Last metadata update: ...
```

### No zones

```text
No configured zones for this camera.
```

### No alerts

```text
No active alerts. Store operations are normal.
```

### Stale metadata

```text
Live data is delayed. Metrics may not reflect the current store state.
```

---

## 15. Minimum implementation checklist

Create or refactor these components:

```text
features/live/components/LiveKpiRow.tsx
features/live/components/LiveOperationsPanel.tsx
features/live/components/QueueStatusTable.tsx
features/live/components/ZoneOccupancyPanel.tsx
```

Keep these existing components, but reposition and relabel them:

```text
VideoPanel.tsx
AlertList.tsx
TrafficChart.tsx
ZoneHeatmap.tsx
AlertDetail.tsx
```

Acceptance criteria:

1. The top of the page tells the user if operations are healthy or not.
2. The highest priority queue/alert is visible without scrolling.
3. Camera feed is used as evidence, not the only value of the page.
4. Technical telemetry is not shown as primary business UI.
5. All current backend calls continue to work.
