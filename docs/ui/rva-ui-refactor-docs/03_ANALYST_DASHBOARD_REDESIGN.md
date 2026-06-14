# Analyst Dashboard Redesign Plan

Target file:

```text
features/analytics/AnalyticsPage.tsx
```

Current related files:

```text
features/analytics/components/AnalyticsPanels.tsx
features/analytics/components/QueueAnalyticsPanels.tsx
features/analytics/components/AlertHistoryPanel.tsx
features/analytics/api/analyticsApi.ts
features/analytics/hooks/useAnalyticsData.ts
features/analytics/hooks/useQueueData.ts
features/analytics/hooks/useAlertHistoryData.ts
features/analytics/types.ts
```

---

## 1. Page purpose

This page should be the main historical business intelligence page.

Rename visible title from:

```text
Traffic Analytics
```

to:

```text
Analyst Dashboard
```

Subtitle:

```text
Business insights from Gold lakehouse metrics
```

The page should answer:

- How many visitors did the store receive?
- When was the peak hour/day?
- How long did customers wait?
- Which zones performed best/worst?
- How many alerts happened?
- What changed compared with the previous period?

---

## 2. Current problems

Current Analyst/Analytics page mixes several concerns in one long scroll:

```text
Traffic KPIs
Hourly detections
Camera share
Daily summary
Queue analytics
Alert history
```

Issues:

1. Filters are too weak.
2. `1d/7d/14d/30d` and `Last 7 days` duplicate the same meaning.
3. Business page exposes technical metrics such as detections, confidence, Silver rows.
4. Queue and Alert sections are appended below traffic, so users must scroll.
5. The page looks like lakehouse data display, not business insight.

---

## 3. Target page structure

```text
PageHeader: Analyst Dashboard        [Store] [Camera] [Zone] [Date Range] [Refresh]
Tabs: Overview | Traffic | Queue | Zones | Alerts

Overview tab:
- KPI row
- Visitors over time
- Visitors by day of week
- Peak hour heatmap
- Top zones
- Key insights

Traffic tab:
- Visitor trend
- Peak hours
- Daily summary

Queue tab:
- Queue KPI row
- Avg wait trend
- Queue zone breakdown
- SLA violations

Zones tab:
- Zone ranking
- Dwell time by zone
- Zone utilization

Alerts tab:
- Alert summary
- Alert trend
- Alert history table
```

Use internal tabs, not more sidebar pages. This keeps the main navigation simple.

---

## 4. New filter design

Replace current filter cluster:

```text
1d 7d 14d 30d | Last 7 days | refresh
```

with:

```text
Store: Store A
Camera: All Cameras
Zone: All Zones
Date Range: Last 7 days
Refresh
```

Recommended state:

```ts
type AnalyticsTab = 'overview' | 'traffic' | 'queue' | 'zones' | 'alerts'

type AnalyticsFilters = {
  storeId: string
  cameraId: string
  zoneId: string
  dateRange: 'today' | 'yesterday' | 'last_7_days' | 'last_14_days' | 'last_30_days'
}
```

Mapping to current API:

```ts
function dateRangeToDays(dateRange: AnalyticsFilters['dateRange']) {
  switch (dateRange) {
    case 'today': return 1
    case 'yesterday': return 1
    case 'last_7_days': return 7
    case 'last_14_days': return 14
    case 'last_30_days': return 30
  }
}
```

Important:

Current backend endpoints mostly accept `days`. Therefore:

- Date Range should actively control API `days`.
- Camera/Zone filters should be shown only if data/API supports them, or rendered as disabled controls with tooltip `Coming after backend filter support`.
- Do not pretend to filter if the backend result is global.

---

## 5. KPI redesign

Current KPI examples include:

```text
Total detections
Busiest camera
Avg confidence
```

Replace with business KPIs:

```text
Total Visitors
Peak Day
Peak Hour
Average Dwell Time
Alert Count
```

For queue tab:

```text
Average Queue Wait
Longest Wait Session
Total Queue Sessions
SLA Violations
```

For zones tab:

```text
Top Zone
Average Zone Dwell
Zone Utilization
Low Engagement Zone
```

For alerts tab:

```text
Total Alerts
High Severity Alerts
Most Frequent Alert Type
Most Affected Zone
```

If backend does not have exact visitor count and only detections exist, UI can label as:

```text
Visitor Observations
```

or keep `Detections` only in a small data quality badge, not as the page's main business KPI.

---

## 6. Overview tab layout

Target:

```text
KPI row: Total Visitors | Peak Day | Peak Hour | Avg Dwell Time | Alerts

Grid 1:
+------------------------------------+------------------------------------+
| Visitors Over Time                 | Visitors by Day of Week            |
+------------------------------------+------------------------------------+

Grid 2:
+------------------------------------+------------------------------------+
| Peak Hours Heatmap                 | Top Zones                          |
+------------------------------------+------------------------------------+

Insights:
+--------------------------------------------------------------------------+
| Key Insights: plain language bullets                                     |
+--------------------------------------------------------------------------+
```

Charts:

### Visitors Over Time

Use line chart.

Source candidates:

```text
data.daily_summary
or transformed data.hourly_traffic
```

If only one day exists, show hourly trend instead of daily trend.

### Visitors by Day of Week

Use bar chart.

If daily_summary has multiple dates, aggregate client side by weekday.

### Peak Hours Heatmap

Use small grid:

```text
Rows: days of week
Columns: hours 06-22
Cell: visitor count or detections
```

If data is not sufficient, hide this chart and show empty state.

### Top Zones

Use horizontal bar chart or ranked list.

Current API may not have zone traffic in `AnalyticsDashboardData`. If not available, use Queue zone stats for queue-only zones or add TODO for backend.

---

## 7. Traffic tab

Purpose:

- Understand customer traffic patterns.

Cards/charts:

```text
Visitor Trend
Peak Hour Distribution
Daily Summary Table
Data Quality mini card
```

Daily summary table columns should be business-focused:

```text
Date | Visitors | Peak Hour | Avg Dwell | Alerts | Notes
```

Avoid:

```text
Avg conf
```

Move `Avg confidence` to a small `Data Quality` block:

```text
Data quality
- Avg model confidence: 83.3%
- Source: Silver detections
```

This preserves useful technical info without making it a business KPI.

---

## 8. Queue tab

Purpose:

- Understand checkout bottlenecks.

Use existing `QueueAnalyticsData`:

```text
kpis
zone_stats
wait_trend
```

Layout:

```text
KPI row: Avg Queue Wait | Max Wait Session | Total Sessions | SLA Violations

Main:
+------------------------------------+------------------------------------+
| Avg Wait by Hour                   | Queue Zone Breakdown               |
+------------------------------------+------------------------------------+

Bottom:
+--------------------------------------------------------------------------+
| Recommendations / Operational Notes                                      |
+--------------------------------------------------------------------------+
```

Queue zone table columns:

```text
Zone | Sessions | Avg Wait | Max Wait | Status
```

Status logic:

```text
Low: avg wait < 60s
Medium: avg wait 60s to 120s
High: avg wait > 120s
```

If SLA threshold is not from backend, define constant in UI:

```ts
const QUEUE_SLA_SECONDS = 120
```

---

## 9. Zones tab

Purpose:

- Understand which store zones receive attention and which underperform.

Required panels:

```text
Top Zones by Visitors
Average Dwell by Zone
Zone Utilization
Low Engagement Zones
```

Current API may not yet expose full zone historical metrics. If not available:

- Create component skeletons with empty states.
- Use queue zone data only where appropriate.
- Add TODO comments for backend fields.

Example empty state:

```text
Zone traffic metrics are not available yet. Add Gold zone aggregates to enable this panel.
```

Do not fake zone traffic from camera share.

---

## 10. Alerts tab

Purpose:

- Understand incident patterns.

Use existing `AlertHistoryData`.

Layout:

```text
KPI row: Total Alerts | High Severity | Most Affected Zone | Most Frequent Type

Grid:
+------------------------------------+------------------------------------+
| Alerts Over Time                   | Alerts by Severity                 |
+------------------------------------+------------------------------------+

Table:
Alert History
```

Current `AlertHistoryPanel` can be reused but should become one section inside Alerts tab, not appended at the bottom of the entire page.

Alert history table columns:

```text
Time | Alert | Camera | Zone | Severity
```

Optional future column:

```text
Clip
```

---

## 11. Data adapter layer

Create selectors/adapters to avoid making components aware of raw API shape.

Recommended path:

```text
features/analytics/adapters/analyticsViewModels.ts
```

Example functions:

```ts
export function buildOverviewKpis(data, queueData, alertHistoryData): MetricCardProps[]
export function buildVisitorsTrend(data): Array<{ label: string; visitors: number }>
export function buildDayOfWeekTraffic(data): Array<{ day: string; visitors: number }>
export function buildQueueStatusRows(queueData): QueueStatusRow[]
export function buildAlertSummary(alertHistoryData): AlertSummaryViewModel
```

Reason:

- Current backend shape may evolve.
- UI components should be simple and reusable.
- Codex can implement page by page without breaking API contracts.

---

## 12. Proposed file structure

```text
features/analytics/AnalyticsPage.tsx
features/analytics/components/AnalyticsFilterBar.tsx
features/analytics/components/AnalyticsTabs.tsx
features/analytics/components/OverviewTab.tsx
features/analytics/components/TrafficTab.tsx
features/analytics/components/QueueTab.tsx
features/analytics/components/ZonesTab.tsx
features/analytics/components/AlertsTab.tsx
features/analytics/components/charts/VisitorsTrendChart.tsx
features/analytics/components/charts/VisitorsByDayChart.tsx
features/analytics/components/charts/PeakHourHeatmapChart.tsx
features/analytics/components/charts/TopZonesChart.tsx
features/analytics/components/charts/QueueWaitTrendChart.tsx
features/analytics/components/charts/AlertSeverityChart.tsx
features/analytics/adapters/analyticsViewModels.ts
```

You can keep old components temporarily and replace one by one.

---

## 13. Compatibility with current API

Current API functions:

```text
getAnalyticsDashboardData(days)
getQueueAnalyticsData(days)
getAlertHistoryData(days)
getPresenceHeatmapData(cameraId, days)
```

Refactor should initially call the same functions.

If adding filter object, map it to days:

```ts
const days = dateRangeToDays(filters.dateRange)
const { data } = useAnalyticsData(days)
const { data: queueData } = useQueueData(days)
const { data: alertHistoryData } = useAlertHistoryData(days)
```

Later backend can support:

```text
/api/v1/analytics/dashboard?store_id=...&camera_id=...&zone_id=...&start=...&end=...
```

But do not require this for the UI refactor.

---

## 14. Chart naming and labels

Replace labels:

```text
Hourly detections -> Visitors by Hour
Camera share -> Camera Coverage / Data Source Mix, or remove from Overview
Daily summary -> Daily Business Summary
Avg conf -> Data Quality: Avg Confidence
Silver rows -> Data source: Silver layer
Gold daily aggregates -> Source: Gold metrics
```

Better business language:

```text
Visitors
Peak Hour
Queue Wait
Dwell Time
Alerts
Zones
```

---

## 15. Implementation steps for Codex

1. Add shared UI components.
2. Add `AnalyticsFilterBar` with date range support.
3. Replace `days` button group in `AnalyticsPage`.
4. Add internal tab state.
5. Move current `AnalyticsPanels` content into `TrafficTab` or `OverviewTab` as a starting point.
6. Move current `QueueAnalyticsPanels` into `QueueTab`.
7. Move current `AlertHistoryPanel` into `AlertsTab`.
8. Create `OverviewTab` with new KPI row and charts using adapters.
9. Add empty states for unavailable zone metrics.
10. Run build.

---

## 16. Acceptance criteria

Analyst Dashboard is done when:

- There is one clear filter bar.
- No duplicate date filter label exists.
- Top KPIs are business KPIs.
- Queue and Alerts are accessible through tabs without scrolling far down.
- Technical fields are either hidden or shown as data quality.
- All charts have units and meaningful titles.
- Empty states explain what data/job is missing.
