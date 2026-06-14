# Codex Implementation Prompt

Use this file as the main instruction prompt for the Codex terminal agent.

---

## 1. Mission

Refactor the RVA frontend UI for 3 main pages:

1. Live Monitor
2. Analyst Dashboard (current Analytics page)
3. Heatmap

Do not build new backend features. Do not add GenAI/LLM features. Do not rewrite the data pipeline. This is a frontend product/UX refactor.

Main objective:

```text
Make the dashboard useful for a store manager and retail analyst.
Do not just display raw data for the sake of displaying data.
```

---

## 2. Read these docs first

Read these markdown files in order:

```text
00_README_UI_REFACTOR_PLAN.md
01_UI_FOUNDATION_AND_COMPONENTS.md
02_LIVE_MONITOR_REDESIGN.md
03_ANALYST_DASHBOARD_REDESIGN.md
04_HEATMAP_REDESIGN.md
```

Then inspect current source files:

```text
shared/components/AppShell.tsx
features/live/LivePage.tsx
features/analytics/AnalyticsPage.tsx
features/heatmap/HeatmapPage.tsx
features/analytics/api/analyticsApi.ts
features/live/types.ts
features/analytics/types.ts
```

---

## 3. Hard constraints

- Keep React + TypeScript.
- Keep Tailwind CSS.
- Keep Recharts.
- Keep current backend API calls working.
- Do not introduce a large state management library.
- Do not change API endpoint URLs unless strictly needed.
- Do not remove existing features unless replaced by a better user-facing equivalent.
- Do not expose technical table names as primary business UI labels.
- Run build after changes.

---

## 4. Step-by-step implementation plan

### Step 1 - Create shared UI foundation

Create:

```text
shared/components/ui/PageHeader.tsx
shared/components/ui/MetricCard.tsx
shared/components/ui/SectionCard.tsx
shared/components/ui/StatusBadge.tsx
shared/components/ui/EmptyState.tsx
shared/components/ui/Tabs.tsx
shared/utils/format.ts
```

Keep components simple and typed.

Acceptance:

- Existing pages still compile.
- No behavior changed yet.

---

### Step 2 - Update AppShell carefully

File:

```text
shared/components/AppShell.tsx
```

Recommended visible labels:

```text
Live Monitor
Analyst
Heatmap
System
```

Keep internal page ids stable:

```ts
type AppPage = 'live' | 'analytics' | 'heatmap' | 'system'
```

Do not break `App.tsx` page switching.

Acceptance:

- Sidebar still works.
- Active state still works.

---

### Step 3 - Refactor Live Monitor

Files to add/refactor:

```text
features/live/LivePage.tsx
features/live/components/LiveOperationsPanel.tsx
features/live/components/QueueStatusTable.tsx
features/live/components/ZoneOccupancyPanel.tsx
features/live/components/LiveKpiRow.tsx
```

Data source:

```text
useLiveData()
```

Use existing data fields:

```text
data.stats
data.frame.zone_counts
data.alerts
data.cameras
data.traffic
data.traffic_summary
data.zone_heatmap
```

Layout:

```text
PageHeader
LiveKpiRow
Main grid: VideoPanel + LiveOperationsPanel
Secondary grid: QueueStatusTable + TrafficChart + ZoneOccupancyPanel
Optional Live Density Snapshot
AlertDetail modal
```

Important:

- Keep `AlertDetail` modal working.
- Keep camera switching working.
- Keep high alert toast if useful.

Acceptance:

- Queue issue and active alerts visible above the fold.
- Camera still visible.
- No empty panels.

---

### Step 4 - Refactor Analyst Dashboard

Files to add/refactor:

```text
features/analytics/AnalyticsPage.tsx
features/analytics/components/AnalyticsFilterBar.tsx
features/analytics/components/AnalyticsTabs.tsx
features/analytics/components/OverviewTab.tsx
features/analytics/components/TrafficTab.tsx
features/analytics/components/QueueTab.tsx
features/analytics/components/ZonesTab.tsx
features/analytics/components/AlertsTab.tsx
features/analytics/adapters/analyticsViewModels.ts
```

Keep current hooks initially:

```text
useAnalyticsData(days)
useQueueData(days)
useAlertHistoryData(days)
```

Filter state:

```ts
type AnalyticsDateRange = 'today' | 'yesterday' | 'last_7_days' | 'last_14_days' | 'last_30_days'

type AnalyticsFilters = {
  storeId: string
  cameraId: string
  zoneId: string
  dateRange: AnalyticsDateRange
}
```

Map date range to current days parameter.

Do not implement fake store/camera/zone filtering if backend does not support it. Hide or disable unsupported filters with clear UI.

Tabs:

```text
Overview | Traffic | Queue | Zones | Alerts
```

Acceptance:

- One filter bar only.
- No duplicate `Last 7 days` label next to `7d` buttons.
- Business KPIs at top.
- Queue and Alerts are accessible via tabs.
- Technical metrics are moved to data quality or System.

---

### Step 5 - Refactor Heatmap

Files to add/refactor:

```text
features/heatmap/HeatmapPage.tsx
features/heatmap/components/HeatmapViewer.tsx
features/heatmap/components/HeatmapSettingsPanel.tsx
features/heatmap/components/HeatmapInsightsPanel.tsx
features/heatmap/components/TopHotspotsList.tsx
features/heatmap/adapters/heatmapViewModels.ts
features/heatmap/components/HeatmapCanvas.tsx
```

Data source:

```text
useHeatmapData(cameraId, days)
```

Add opacity support:

```ts
<HeatmapCanvas opacity={settings.opacity} ... />
```

Add derived insights from cells:

```text
Hotspot count
Max intensity
Concentration score
Top hotspot locations
```

Acceptance:

- Heatmap view remains intact.
- Side panel explains the heatmap.
- Date/camera filters match UI style.
- Technical labels are not prominent.

---

### Step 6 - Polish and build

Run:

```bash
npm run build
```

If project uses other commands, inspect `package.json` and run the appropriate typecheck/build command.

Fix TypeScript errors.

Check manually:

- Live page loads.
- Analyst page tabs work.
- Heatmap page loads.
- Empty and error states do not crash.
- Camera switch still works.
- Alert detail modal still opens.

---

## 5. Coding style guidance

Prefer clear code over clever code.

Good:

```tsx
const activeAlerts = alerts.filter((alert) => alert.status === 'new')
```

Avoid:

```tsx
const a = x?.filter((y) => y.s === 'new') ?? []
```

Use adapters for business view models. Do not put complicated business calculations directly inside JSX.

---

## 6. Business language replacements

Use these label changes:

```text
Traffic Analytics -> Analyst Dashboard
Total detections -> Total Visitors or Visitor Observations
Hourly detections -> Visitors by Hour
Camera share -> Camera Coverage or remove from Overview
Avg confidence -> Data Quality: Avg Confidence
Daily summary -> Daily Business Summary
Retail zones -> Zone Occupancy
New alerts -> Active Alerts
Density heatmap -> Live Density Snapshot or Traffic Density Map
Presence Heatmap -> Heatmap
```

---

## 7. Do not implement yet

Do not implement:

- LLM copilot.
- Text-to-SQL.
- STL decomposition.
- Forecasting.
- New AWS/cloud deploy UI.
- Authentication changes.
- Backend filtering unless explicitly requested.

---

## 8. Final response expected from Codex

After implementation, report:

```text
Changed files:
- ...

What changed:
- ...

How to verify:
- npm run build
- open Live Monitor
- open Analyst Dashboard
- open Heatmap

Known limitations:
- store/camera/zone historical filters may be disabled until backend supports them
- zone historical metrics may need Gold aggregates
```
