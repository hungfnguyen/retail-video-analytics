# Live Monitor Redesign Plan

Target file:

```text
features/live/LivePage.tsx
```

Current related components:

```text
features/live/components/LiveMetricCards.tsx
features/live/components/VideoPanel.tsx
features/live/components/ZoneRuntimePanel.tsx
features/live/components/AlertList.tsx
features/live/components/ZoneHeatmap.tsx
features/live/components/TrafficChart.tsx
features/live/components/AlertDetail.tsx
features/live/hooks/useLiveData.ts
features/live/types.ts
```

---

## 1. Page purpose

Live Monitor is for real-time store operations.

It should answer:

- How crowded is the store now?
- Is queue wait time acceptable?
- Which queue needs staff attention?
- Are there active alerts?
- Which camera/zone is currently risky?
- What should the operator do now?

This page should not feel like a raw camera page. It should feel like an operations command center.

---

## 2. Current issues

Current Live page already has useful data:

- current count
- queue length
- longest wait
- active alerts
- camera overview
- annotated video
- zone occupancy
- alert list
- density heatmap

But the camera currently dominates the page. The operational decision panels are below or beside the camera and can feel secondary.

Main issue:

```text
Camera is visually primary.
Actionable operations insight is secondary.
```

Target:

```text
Operation status is primary.
Camera is evidence/supporting view.
```

---

## 3. Target layout

Recommended layout:

```text
PageHeader: Live Monitor                           [Camera selector] [Refresh/live state]
KPI row: Visitors | Queue Wait | Queue Length | Peak Zone | Active Alerts

Main grid:
+------------------------------------------------------+---------------------------+
| Live Camera                                          | Active Alerts             |
| Cam 1 - Checkout Area                                | Queue actions             |
| Annotated stream                                     | Zone risk summary         |
+------------------------------------------------------+---------------------------+

Secondary grid:
+-------------------------------+-------------------------------+-------------------------------+
| Queue Status                  | Visitors Trend Today          | Zone Occupancy                |
+-------------------------------+-------------------------------+-------------------------------+

Optional below:
+--------------------------------------------------------------------------+
| Compact Density Strip / Mini Heatmap                                     |
+--------------------------------------------------------------------------+
```

CSS suggestion:

```tsx
<div className="grid grid-cols-[minmax(0,1.45fr)_420px] gap-5">
  <VideoPanel />
  <LiveOperationsPanel />
</div>
```

---

## 4. Header

Replace the current simple camera dropdown with a clearer live toolbar.

Header contents:

```text
Title: Live Monitor
Subtitle: Store A - updated 10:30:45 AM
Actions:
- Camera selector: All cameras / Cam 1 / Cam 2
- Live status badge
- Refresh button
```

If the live API is polling automatically, the refresh button can be optional but useful.

---

## 5. KPI row

Current metrics:

```text
Current count
Queue length
Longest wait
Active alerts
```

Recommended metrics:

```text
Visitors in Store
Avg Queue Wait
Longest Wait
Busiest Zone
Active Alerts
```

If only current data is available, map as follows:

```text
Visitors in Store = currentPeopleCount
Avg Queue Wait = weighted or simple average of queue zone avg_wait_ms
Longest Wait = max queue max_wait_ms
Busiest Zone = zone with max count
Active Alerts = alerts with status new
```

If `avg_queue_wait` cannot be computed reliably, show `Longest Wait` and `Queue Length` only.

Suggested KPI labels and intent:

| KPI | Source | Business meaning |
|---|---|---|
| Visitors in Store | stats.current_count + zoneOccupancyCount fallback | Current occupancy |
| Queue Length | sum queue zone counts | Checkout load |
| Longest Wait | max queue max_wait_ms | Urgency |
| Busiest Zone | max zone count | Where crowd is concentrated |
| Active Alerts | new alerts | Required review |

Color rules:

- Normal traffic: blue/green.
- Queue wait above threshold: amber/red.
- Active high alert: red.
- No alert: green/slate.

---

## 6. Main camera panel

Keep `VideoPanel`, but make it more useful:

Header inside card:

```text
Live Camera - Cam 1 - Checkout Area       LIVE
```

Footer controls/metadata:

```text
FPS | latency | metadata status | frame timestamp
```

Do not overload the video with too much technical text. Keep technical details small or in a collapsible diagnostics row.

Recommended camera panel actions:

- Switch camera.
- Snapshot button placeholder if backend supports later.
- Fullscreen button optional.
- Toggle overlays optional: boxes, zones, labels.

---

## 7. Right operations panel

Create new component:

```text
features/live/components/LiveOperationsPanel.tsx
```

It should contain:

1. Active Alerts
2. Queue Actions
3. Zone Risk Summary

### 7.1 Active Alerts

Use current `AlertList`, but visually prioritize high severity.

For each alert:

```text
Title
Description
Zone/camera
Relative time
Severity badge
Click -> AlertDetail
```

### 7.2 Queue Actions

Create from queue zones.

Example output:

```text
Checkout Queue 03
Longest wait: 2m 07s
Queue length: 1
Status: Warning
Suggested action: Monitor queue / open another checkout if wait exceeds threshold
```

Threshold suggestion:

```text
low: wait < 60s
medium: wait 60s to 120s
high: wait > 120s
```

This can be calculated client side from zone max_wait_ms and avg_wait_ms.

### 7.3 Zone Risk Summary

Show top 3 zones by occupancy:

```text
1. Checkout Queue 03 - 1 person - high wait
2. Checkout Queue 01 - 0 people
3. Checkout Queue 02 - 0 people
```

If all zones are empty, show `No active congestion`.

---

## 8. Queue Status table

Refactor `ZoneRuntimePanel` or create:

```text
features/live/components/QueueStatusTable.tsx
```

Columns:

```text
Zone | Count | Avg wait | Max wait | Status | Trend
```

Status can be calculated from max wait:

```ts
function queueStatus(maxWaitMs: number) {
  if (maxWaitMs >= 120000) return 'high'
  if (maxWaitMs >= 60000) return 'medium'
  return 'low'
}
```

Trend is optional unless `traffic` or previous samples are available.

---

## 9. Visitors trend chart

Current `TrafficChart.tsx` exists but is not used in the Live page layout. Reintroduce it below the video or in secondary grid.

Chart purpose:

```text
Traffic today or last 60 minutes
```

Use existing fields:

```text
data.traffic
data.traffic_summary
```

Recommended title:

```text
Visitors Trend Today
```

If only last 60 minutes is available, label exactly:

```text
Visitors Last 60 Minutes
```

Do not imply daily data if data is only 60 minutes.

---

## 10. Zone occupancy panel

Current `ZoneRuntimePanel` has occupancy and line crossings. Split it:

```text
ZoneOccupancyPanel
LineCrossingPanel
```

For business user, line crossings are secondary. Put line crossings smaller or hide in details.

ZoneOccupancyPanel should show:

```text
Zone name
Zone type
Current count
Wait info for queue zones
Utilization bar
```

---

## 11. Density heatmap on Live page

Current `ZoneHeatmap` is a synthetic grid. It is useful as secondary context, but should not consume too much vertical space.

Options:

- Keep as compact card below the secondary grid.
- Rename to `Live Density Snapshot`.
- Provide legend low/high.

Do not confuse this with the main historical Heatmap page.

---

## 12. Component tree target

```text
LivePage
  PageHeader
  LiveMetricCards or LiveKpiRow
  MainGrid
    VideoPanel
    LiveOperationsPanel
      AlertList
      QueueActionList
      ZoneRiskSummary
  SecondaryGrid
    QueueStatusTable
    TrafficChart
    ZoneOccupancyPanel
  LiveDensitySnapshot
  AlertDetail modal
```

---

## 13. Implementation steps for Codex

1. Create shared UI components first from `01_UI_FOUNDATION_AND_COMPONENTS.md`.
2. Add `features/live/components/LiveOperationsPanel.tsx`.
3. Add `features/live/components/QueueStatusTable.tsx`.
4. Add `features/live/components/ZoneOccupancyPanel.tsx` or refactor `ZoneRuntimePanel`.
5. Update `LivePage.tsx` layout.
6. Reuse current data from `useLiveData` without backend changes.
7. Keep `AlertDetail` behavior unchanged.
8. Run TypeScript build.

---

## 14. Empty/error states

Live page states:

```text
No live data -> show centered loading/empty state with retry.
Camera missing media -> show media unavailable card.
No alerts -> show calm green/no active alerts state.
No zones -> show no zone data but keep camera visible.
```

Do not render blank cards.

---

## 15. Acceptance criteria

Live page is done when:

- User can identify current queue issue without scrolling.
- High alerts are visible above the fold.
- Camera remains visible and useful.
- Queue status table shows action priority.
- Chart labels use business language.
- No technical metrics dominate the page.
