# Analyst Dashboard Tab - Business Charts and Data Specification

Target page:

```text
features/analytics/AnalyticsPage.tsx
```

Related current components:

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

Main data sources:

```text
useAnalyticsData(days)
useQueueData(days)
useAlertHistoryData(days)
```

This document defines the charts and business metrics for the Analyst Dashboard. The current page should evolve from `showing lakehouse rows` into `explaining store performance`.

---

## 1. User and page purpose

Primary users:

```text
Store manager
Retail analyst
Operations lead
```

The Analyst Dashboard should answer:

1. How did store traffic perform during the selected period?
2. What are the peak days and peak hours?
3. Which queues are hurting customer experience?
4. Which zones attract the most visitors or dwell time?
5. What incidents happened, and where?
6. What changed compared with the previous period?

This page should be historical and business-oriented. It should be based on Gold layer metrics whenever possible.

---

## 2. Business principle

The main page should not lead with technical CV metrics.

Avoid making these primary KPIs:

```text
Total detections
Avg confidence
Camera share
Silver rows
```

Use them only as data quality indicators or in System/debug views.

Primary business metrics should be:

```text
Visitors
Peak hour
Dwell time
Queue wait
Queue sessions
Alerts
Zone utilization
```

---

## 3. Recommended Analyst structure

```text
PageHeader
  title: Analyst Dashboard
  subtitle: Business insights from Gold lakehouse metrics
  controls: Store, Camera, Zone, Date Range, Refresh

Tabs
  Overview | Traffic | Queue | Zones | Alerts
```

Do not create separate sidebar pages for every analysis type yet. Internal tabs keep the app simple.

---

## 4. Filter design

Current filter issue:

```text
1d 7d 14d 30d + Last 7 days duplicate information
```

Target filter bar:

```text
Store: Store A
Camera: All Cameras
Zone: All Zones
Date Range: Last 7 days
Refresh
```

Recommended type:

```ts
type AnalyticsTab = 'overview' | 'traffic' | 'queue' | 'zones' | 'alerts'

type DateRangePreset =
  | 'today'
  | 'yesterday'
  | 'last_7_days'
  | 'last_14_days'
  | 'last_30_days'

type AnalyticsFilters = {
  storeId: string
  cameraId: string
  zoneId: string
  dateRange: DateRangePreset
}
```

Mapping to current backend:

```ts
function dateRangeToDays(dateRange: DateRangePreset) {
  switch (dateRange) {
    case 'today': return 1
    case 'yesterday': return 1
    case 'last_7_days': return 7
    case 'last_14_days': return 14
    case 'last_30_days': return 30
  }
}
```

Important implementation rule:

If backend supports only `days`, then Store/Camera/Zone filters can be visible but disabled with a tooltip, or hidden until supported. Do not fake filtering on the client unless the dataset contains enough fields to filter correctly.

---

## 5. Overview tab

Purpose:

```text
A one-screen executive summary of store performance.
```

### 5.1 KPI row

#### Total Visitors

Business question:

```text
How much traffic did the store receive?
```

Preferred data source:

```text
gold traffic aggregate
```

Current fallback:

```ts
data.kpis item currently labeled Total detections
```

Implementation note:

If backend still returns detection count, rename carefully only if it represents visitor count. If it is raw detection rows, label it as `Observed Visits` or keep it out of primary KPI.

User value:

- Measures store demand.
- Supports staffing and campaign evaluation.

#### Peak Day

Business question:

```text
Which day had the highest traffic?
```

Data source:

```ts
data.daily_summary
```

Derivation:

```ts
peakDay = max daily_summary by detections or visitors
```

Display:

```text
Peak Day
Sat, 7 Jun
3,185 visitors
```

#### Peak Hour

Business question:

```text
When should the store prepare for peak demand?
```

Data source:

```ts
data.hourly_traffic
```

Derivation:

```ts
peakHour = max hourly_traffic by detections or visitors
```

Display:

```text
Peak Hour
13:00
3,124 visitors
```

#### Average Dwell Time

Business question:

```text
How long do customers stay or engage?
```

Data source:

```ts
data.daily_summary[].avg_dwell_sec
```

Current fallback:

```ts
existing KPI Avg dwell
```

Display:

```text
Avg Dwell Time
52s
+6s vs previous period
```

#### Alert Count

Business question:

```text
How many operational problems occurred?
```

Data source:

```ts
alertHistoryData.records
```

Derivation:

```ts
totalAlerts = records.length
highAlerts = records.filter(r => r.severity === 'high').length
```

Display:

```text
Alerts
24
8 high severity
```

---

### 5.2 Visitors Over Time

Recommended chart:

```text
Line chart
```

Business question:

```text
Is traffic rising, falling, or stable over the selected period?
```

Preferred data:

```text
gold traffic by day or hour
```

Current data source:

```ts
data.daily_summary for daily trend
or data.hourly_traffic for hourly distribution
```

Chart fields:

```text
x: date or hour
y: visitors
```

User action:

- Identify growth/decline.
- Identify campaign impact.
- Compare periods later when backend supports previous period.

Do not use bars if the goal is trend. Use a line chart for trend.

---

### 5.3 Visitors by Day of Week

Recommended chart:

```text
Bar chart
```

Business question:

```text
Which weekdays need more staffing?
```

Preferred data:

```text
gold traffic grouped by day_of_week
```

Current fallback:

Derive from `daily_summary.date` if there are multiple days.

Fields:

```text
x: day of week
y: visitors
```

User action:

- Staff scheduling.
- Promotion planning.

Empty state:

If only one day of data exists, show:

```text
Need at least 7 days to compare weekdays.
```

---

### 5.4 Peak Hours Heatmap

Recommended chart:

```text
Calendar-style heatmap or matrix heatmap
```

Business question:

```text
Which day-hour combinations are consistently busy?
```

Preferred data:

```text
gold traffic grouped by day_of_week and hour
```

Current fallback:

Use `hourly_traffic` only for a simple hour-of-day bar chart until backend provides day/hour matrix.

Fields:

```text
rows: day of week
columns: hour of day
value: visitors
```

User action:

- Decide staffing by day and hour.
- Identify recurring peak periods.

Implementation note:

Do not fake a full matrix from one-day data. Show a future-ready empty or simple bar alternative.

---

### 5.5 Top Zones

Recommended chart:

```text
Ranked list or horizontal bar chart
```

Business question:

```text
Which zones attract the most customers?
```

Preferred data:

```text
gold zone traffic aggregate
```

Current fallback:

If only camera comparison exists, do not call it Top Zones. Use `Camera Coverage` or hide this card.

Fields:

```text
zone_name
visitors
share_percent
```

User action:

- Understand product area interest.
- Improve store layout.
- Compare promotion zones.

---

### 5.6 Key Insights panel

Recommended component:

```text
BusinessInsightPanel
```

Purpose:

```text
Convert charts into plain-language findings.
```

Example insights:

```text
Peak traffic occurred at 13:00 with 3,124 visitors.
Checkout Queue 03 had the highest average wait time.
High severity alerts increased compared with the previous period.
```

Data source:

Use simple deterministic rules from existing data. Do not use an LLM yet.

Implementation rule:

Generate 3 to 5 insights max. Each insight must reference a visible metric.

---

## 6. Traffic tab

Purpose:

```text
Detailed visitor traffic analysis.
```

### 6.1 Visitor Trend

Chart type:

```text
Line chart
```

Data:

```ts
data.daily_summary or hourly_traffic
```

Business question:

```text
How did visitor volume change over time?
```

Preferred label:

```text
Visitors over time
```

Avoid:

```text
Hourly detections
```

unless it is explicitly a technical debug metric.

---

### 6.2 Hourly Distribution

Chart type:

```text
Bar chart
```

Data:

```ts
data.hourly_traffic
```

Business question:

```text
What hours are busiest on average?
```

Fields:

```text
x: hour
y: visitors or observed visits
line: per-day average if available
```

User action:

- Staff scheduling by hour.
- Plan checkout coverage.

---

### 6.3 Daily Performance Table

Table columns:

```text
Date | Visitors | Peak Hour | Avg Dwell | Avg Queue Wait | Alerts
```

Current available fields:

```ts
Date: data.daily_summary[].date
Visitors: data.daily_summary[].detections, if this is visitor-like
Peak Hour: data.daily_summary[].peak
Avg Dwell: data.daily_summary[].avg_dwell_sec
Avg Conf: current field, but should not be business primary
```

Recommendation:

Remove `Avg conf` from the business table. Move it to a small data quality tooltip or System page.

---

## 7. Queue tab

Purpose:

```text
Customer waiting experience analysis.
```

Data source:

```ts
queueData.kpis
queueData.zone_stats
queueData.wait_trend
```

### 7.1 Queue KPI row

Cards:

```text
Avg Queue Wait
Longest Wait Session
Total Queue Sessions
SLA Violations
```

SLA Violations can be derived if threshold is available:

```ts
slaThresholdSec = 120
violatingZones = zone_stats where max_wait_sec > slaThresholdSec
```

If no session-level data exists, label it carefully:

```text
Queues Above SLA
```

not:

```text
SLA Violations
```

---

### 7.2 Avg Wait by Hour

Chart type:

```text
Bar chart or line chart
```

Current data:

```ts
queueData.wait_trend
```

Fields:

```text
x: hour
y: avg_wait_sec / 60
secondary: sessions
```

Business question:

```text
When do customers wait the longest?
```

User action:

- Add staff at the worst hours.
- Find checkout bottlenecks.

---

### 7.3 Queue Zone Breakdown

Chart/table:

```text
Ranked table
```

Current data:

```ts
queueData.zone_stats
```

Columns:

```text
Queue Zone | Sessions | Avg Wait | Max Wait | Status
```

Status threshold:

```text
Low: avg <= 60s
Medium: avg 61-120s
High: avg > 120s or max > 180s
```

Sort:

```text
High status first, max wait desc, avg wait desc
```

Business question:

```text
Which queue is hurting customer experience most?
```

---

### 7.4 Wait Time Distribution

Chart type:

```text
Histogram
```

Preferred future data:

```text
gold queue sessions with wait_sec
```

Business question:

```text
Are most waits acceptable, or are there many long waits?
```

Implementation note:

Do not implement this chart if only aggregated data exists. Put it in the future backend requirements section.

---

## 8. Zones tab

Purpose:

```text
Understand how customers use physical store areas.
```

Preferred data sources:

```text
gold zone traffic
gold zone dwell
gold zone utilization
```

Current fallback:

Use live zone data only in Live page. For Analyst, do not fake historical zone charts unless historical zone data exists.

### 8.1 Zone Ranking

Chart type:

```text
Horizontal bar chart
```

Fields:

```text
zone_name
visitors
share_percent
```

Business question:

```text
Which zones attract the most traffic?
```

### 8.2 Dwell Time by Zone

Chart type:

```text
Horizontal bar chart
```

Fields:

```text
zone_name
avg_dwell_sec
```

Business question:

```text
Where do customers spend the most time?
```

### 8.3 Zone Utilization Matrix

Chart type:

```text
Heatmap matrix or ranked cards
```

Fields:

```text
zone_name
traffic
avg_dwell
utilization_score
```

User action:

- Improve layout.
- Measure promotion area engagement.
- Identify underused space.

---

## 9. Alerts tab

Purpose:

```text
Historical incident analysis.
```

Data source:

```ts
alertHistoryData.records
```

### 9.1 Alert Summary KPI row

Cards:

```text
Total Alerts
High Severity Alerts
Most Frequent Alert Type
Most Affected Zone
```

Derivations:

```ts
totalAlerts = records.length
highAlerts = count severity high
mostFrequentAlertType = group by alert_type max count
mostAffectedZone = group by zone max count
```

Business question:

```text
What operational issues happened most often?
```

---

### 9.2 Alerts by Severity

Chart type:

```text
Donut chart or stacked bar
```

Fields:

```text
severity
count
```

Business question:

```text
Are incidents mostly low risk or high risk?
```

---

### 9.3 Alert Trend

Chart type:

```text
Line or bar chart
```

Fields:

```text
date or hour
alert_count
high_alert_count
```

Business question:

```text
Are incidents increasing or concentrated at specific times?
```

---

### 9.4 Alert History Table

Current component:

```text
AlertHistoryPanel.tsx
```

Recommended columns:

```text
Time | Alert | Zone | Camera | Severity | Evidence
```

If `clip_s3_key` exists, show an Evidence badge.

Sort:

```text
High severity first if in summary view, newest first in full history view
```

---

## 10. Data quality and naming rules

Use business labels:

```text
Visitors
Observed Visits
Queue Wait
Dwell Time
Alerts
Zones
```

Avoid primary labels:

```text
Detections
Confidence
Silver rows
Gold rows
Trino query
```

Where technical labels are necessary, use small badges or tooltips:

```text
Source: Gold lakehouse
Updated: 10:32:00
```

---

## 11. Backend-friendly phased implementation

### Phase 1 - Frontend only, current APIs

Use current data types:

```text
AnalyticsDashboardData
QueueAnalyticsData
AlertHistoryData
```

Implement:

- New filter bar with date range mapping to `days`.
- Tabs.
- Overview metrics from existing data.
- Queue tab from queueData.
- Alerts tab from alertHistoryData.
- Hide or relabel technical metrics.

### Phase 2 - Backend enrichment

Add endpoints or fields for:

```text
previous_period_delta
traffic_by_day_of_week
traffic_by_day_hour_matrix
zone_traffic_summary
zone_dwell_summary
alert_trend
queue_wait_distribution
```

### Phase 3 - Advanced insights

Add deterministic insight generation:

```text
Peak traffic insight
Worst queue insight
Alert hotspot insight
Dwell improvement/decline insight
```

No LLM required for this phase.

---

## 12. Acceptance criteria

1. Analyst page no longer looks like a raw lakehouse/debug page.
2. User can answer business questions from the first screen.
3. Filters are clear and not duplicated.
4. Charts have business titles and user-facing labels.
5. Technical metrics are moved to System or secondary tooltips.
6. Each chart has a clear decision purpose.
7. Page works with current backend APIs, with clear empty states for future charts.
