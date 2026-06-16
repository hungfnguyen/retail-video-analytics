# RVA UI Refactor Plan for Codex Agent

Project: Retail Video Analytics (RVA)
Scope: Frontend UI refactor for 3 main user-facing pages:

1. Live Monitor
2. Analyst Dashboard (current Analytics page)
3. Heatmap

System page can stay mostly as technical/dev monitoring. Do not mix System/engineering metrics into the business-facing pages unless explicitly marked as Data Quality or Diagnostics.

---

## 1. Product goal

Current UI already displays live camera, analytics, and heatmap data. The refactor goal is not to show more data. The goal is to make the UI answer user decisions:

- What is happening in the store right now?
- Do I need to act now?
- Which queue/zone is problematic?
- What changed compared with the previous period?
- Which area attracts the most traffic?
- Where should staff be allocated?

The target user is a store manager or retail operations analyst, not a computer vision engineer.

---

## 2. Current code context

Relevant current files:

```text
app/App.tsx
shared/components/AppShell.tsx
features/live/LivePage.tsx
features/live/components/LiveMetricCards.tsx
features/live/components/VideoPanel.tsx
features/live/components/ZoneRuntimePanel.tsx
features/live/components/AlertList.tsx
features/live/components/ZoneHeatmap.tsx
features/analytics/AnalyticsPage.tsx
features/analytics/components/AnalyticsPanels.tsx
features/analytics/components/QueueAnalyticsPanels.tsx
features/analytics/components/AlertHistoryPanel.tsx
features/analytics/api/analyticsApi.ts
features/analytics/types.ts
features/heatmap/HeatmapPage.tsx
features/heatmap/components/TrafficHeatmap.tsx
features/heatmap/components/HeatmapCanvas.tsx
features/heatmap/hooks/useHeatmapData.ts
```

Important constraints:

- Keep React + TypeScript + Tailwind CSS.
- Keep Recharts for charts.
- Do not rewrite backend APIs in this UI refactor.
- Keep existing hooks initially, then add adapters/selectors if needed.
- UI should degrade gracefully when backend fields are missing.
- Avoid large risky rewrites in one patch.

---

## 3. Target information architecture

Navigation remains simple:

```text
RVA
- Live Monitor
- Analyst Dashboard
- Heatmap
- System
```

Recommended labels:

- Live Monitor: real-time operations.
- Analyst Dashboard: historical and gold-layer business insights.
- Heatmap: spatial traffic analysis.
- System: technical health, docker, pipeline, CV runtime.

If renaming `Analytics` to `Analyst Dashboard` is too large, keep the route/page id as `analytics` and only change the visible label/title.

---

## 4. Refactor principle

Each main page should follow this structure:

```text
PageHeader
FilterBar
Primary KPI row
Primary content grid
Secondary insights / tables
Empty/loading/error states
```

Each card should answer one question. Avoid cards that only expose raw technical data.

Bad examples for business page:

```text
Total detections
Average confidence
Silver rows
Camera share
```

Good examples:

```text
Total visitors
Peak hour
Average queue wait
Worst queue zone
Alert count
Top zone by traffic
Average dwell time
SLA violation count
```

Technical metrics can stay in System:

```text
Detection count
Model confidence
Flink lag
Trino query status
Pulsar backlog
Redis keys
FPS
Inference latency
```

---

## 5. Proposed shared UI components

Create or refactor these shared components first:

```text
shared/components/ui/PageHeader.tsx
shared/components/ui/FilterBar.tsx
shared/components/ui/MetricCard.tsx
shared/components/ui/SectionCard.tsx
shared/components/ui/StatusBadge.tsx
shared/components/ui/EmptyState.tsx
shared/components/ui/Tabs.tsx
shared/components/ui/ChartContainer.tsx
shared/components/ui/InsightList.tsx
shared/utils/format.ts
shared/utils/chart.ts
```

Do not over-engineer. These components should be small and boring.

---

## 6. Suggested implementation phases

### Phase 1 - UI foundation

- Create shared UI components.
- Normalize spacing, card radius, shadows, page title, filter controls.
- Make all pages visually consistent.
- No backend changes.

### Phase 2 - Live Monitor redesign

- Keep existing live API.
- Rebalance camera and operational panels.
- Add action-oriented queue/alert/zone cards.
- Make camera view important but not the only value.

### Phase 3 - Analyst Dashboard redesign

- Replace weak `1d/7d/14d/30d + Last 7 days` filter with a proper filter bar.
- Add internal tabs: Overview, Traffic, Queue, Zones, Alerts.
- Prioritize Gold/business metrics.
- Move detection/confidence details away from top-level business UI.

### Phase 4 - Heatmap redesign

- Keep camera overlay.
- Add insight panel: hottest zone, busiest time, top zones, dwell hotspot.
- Add controls for camera, date range, layer, opacity.
- Turn the heatmap from a visual-only page into a decision page.

### Phase 5 - polish and QA

- Loading/empty/error states.
- Visual consistency.
- TypeScript compile.
- Responsive behavior for 1180px minimum width and large screens.

---

## 7. Acceptance criteria

A reviewer should be able to open the app and understand:

- Live page: current risk and operational actions within 10 seconds.
- Analyst page: traffic/queue/zone business insights without reading technical table names.
- Heatmap page: where traffic concentrates and what action it suggests.

Codex should not consider the refactor done unless:

- `npm run build` passes.
- No API endpoint is broken.
- No page crashes when data is empty/null.
- Filters have a single source of truth per page.
- Page titles and labels use business language.
- Charts have clear titles, units, and tooltips.

---

## 8. Files in this plan

```text
00_README_UI_REFACTOR_PLAN.md
01_UI_FOUNDATION_AND_COMPONENTS.md
02_LIVE_MONITOR_REDESIGN.md
03_ANALYST_DASHBOARD_REDESIGN.md
04_HEATMAP_REDESIGN.md
05_CODEX_IMPLEMENTATION_PROMPT.md
```
