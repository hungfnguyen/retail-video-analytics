# Analyst Dashboard Tab - Business Data and Chart Specification

This document defines the charts, business metrics, and data contracts for the **Analyst Dashboard** tab.

The Analyst tab should not be a raw lakehouse data viewer. It should be a business intelligence dashboard that answers:

```text
How did the store perform?
What changed?
When was it busy?
Where did customers spend time?
How bad were queues?
Which incidents matter?
```

---

## 1. Target user

Primary users:

```text
Store manager
Retail analyst
Operations lead
```

They care about business outcomes:

- foot traffic;
- peak periods;
- queue performance;
- dwell time;
- zone performance;
- alert frequency;
- comparison with previous period.

They should not need to understand:

- Silver table row counts;
- detection confidence;
- raw camera ids;
- model internals.

Those can exist in System or debug views, but not as headline business KPIs.

---

## 2. Recommended Analyst tab structure

Use internal tabs inside the Analyst page:

```text
Overview | Traffic | Queue | Zones | Alerts
```

Recommended top-level layout:

```text
PageHeader: Analyst Dashboard
FilterBar: Store | Camera | Zone | Date Range | Compare | Refresh
Tabs
Selected tab content
```

Do not create more sidebar pages for each analytics area. Keep the sidebar simple.

---

## 3. Filter specification

### 3.1 Required filters

| Filter | Business meaning | Current implementation guidance |
|---|---|---|
| Store | Which retail location? | show `Store A`; disabled if only one store exists |
| Camera / Area | All cameras or selected camera area | enabled only if backend supports it; otherwise disabled |
| Zone | All zones or a selected zone | enabled only if backend supports it; otherwise disabled |
| Date Range | Time window for analytics | maps to existing `days` API parameter |
| Compare | Compare with previous equivalent period | frontend can show placeholder until backend supports comparison |
| Refresh | Reload Trino-backed data | call existing refresh functions |

### 3.2 Date range options

Recommended visible options:

```text
Today
Yesterday
Last 7 days
Last 14 days
Last 30 days
Custom
```

For the current backend, map supported values to days:

```ts
today -> 1
yesterday -> 1
last_7_days -> 7
last_14_days -> 14
last_30_days -> 30
```

Do not show both `7d` and `Last 7 days` at the same time. That duplicates meaning.

### 3.3 Unsupported filters

If Camera or Zone filtering is not supported by the backend yet:

```text
Render the control disabled with helper text:
"Available after backend filter support"
```

Never fake filtering in the frontend if the returned dataset is global.

---

## 4. Overview tab

The Overview tab is the executive summary. It should answer:

```text
Did the store perform well during the selected period?
What are the biggest changes or problems?
```

### 4.1 KPI cards

| KPI | Business question | Data source | Display guidance |
|---|---|---|---|
| Total visitors | How much traffic did we get? | Gold traffic aggregate or current `total detections` fallback | Use `Visitors`, not `Detections` if deduped data exists |
| Peak hour | When was the busiest time? | `daily_summary.peak` or hourly traffic | Show hour + visitor count |
| Average dwell time | Did customers stay long enough? | `daily_summary.avg_dwell_sec` / Gold dwell table | Format as seconds/minutes |
| Average queue wait | How painful was checkout? | `QueueAnalyticsData.kpis` or `zone_stats` | Format duration |
| Alert count | How many incidents occurred? | `AlertHistoryData.records` | Split high/medium if possible |

Optional comparison:

```text
+14% vs previous 7 days
-8s avg queue wait vs previous 7 days
```

Only show comparison if data is actually available. Otherwise hide it.

---

### 4.2 Visitors over time

Business question:

```text
Is traffic increasing, decreasing, or peaking at certain times?
```

Visualization:

```text
Line chart for daily or hourly visitors
```

Data:

Current fallback:

```text
AnalyticsDashboardData.hourly_traffic[]
hour
detections
average
```

Better future Gold data:

```text
gold.store_traffic_hourly
- store_id
- hour_bucket
- visitor_count
- unique_track_count
- camera_count
```

Label guidance:

- If using raw detections, label as `Detection events` or `Estimated visitors` with tooltip.
- If using deduped tracks, label as `Visitors`.

Do not silently rename raw detections to visitors if deduplication is not reliable.

---

### 4.3 Visitors by day of week

Business question:

```text
Which weekdays are busiest?
```

Visualization:

```text
Bar chart: Mon -> Sun
```

Data requirement:

```text
business_date
weekday
visitor_count
```

Business value:

- staff scheduling;
- promotion planning;
- identifying weekend patterns.

Implementation note:

If backend does not provide weekday aggregation yet, this chart can be added after Gold daily aggregates are ready.

---

### 4.4 Peak hour heatmap

Business question:

```text
Which hour-of-day and day-of-week combinations are busiest?
```

Visualization:

```text
Matrix heatmap
Rows: day of week
Columns: hour of day
Color: visitor count or relative intensity
```

Data requirement:

```text
weekday
hour
visitor_count
```

Business value:

This is one of the most useful BI charts for retail because it directly supports staffing decisions.

Do not confuse this with camera spatial heatmap. This is a **time heatmap**, not a floor heatmap.

---

### 4.5 Top zones

Business question:

```text
Which areas attract the most customer presence?
```

Visualization:

```text
Ranked horizontal bars
```

Data requirement:

```text
zone_id
zone_name
visitor_count
share_of_total
avg_dwell_sec
```

Business value:

- merchandising;
- layout optimization;
- identifying underused areas.

Current fallback:

If only camera comparison exists, do not label it as zone performance. Use:

```text
Camera / Area Share
```

not:

```text
Top Zones
```

---

### 4.6 Key insights panel

Business question:

```text
What should the manager notice first?
```

Visualization:

```text
Short insight cards
```

Examples:

```text
Peak traffic occurred at 13:00 with 3,124 visitor events.
Checkout Queue 03 had the longest average wait at 43s.
High severity alerts increased during the afternoon period.
```

Implementation can be deterministic. No LLM needed.

---

## 5. Traffic tab

The Traffic tab focuses only on customer flow.

### 5.1 Recommended charts

| Chart | Business question | Visualization | Data |
|---|---|---|---|
| Visitor trend | How did traffic evolve over time? | Line chart | hourly/daily visitor count |
| Peak hours | When is the store busiest? | Bar chart or time heatmap | hour-of-day aggregation |
| Daily summary | What happened each day? | Table | daily visitor, peak hour, dwell, alerts |
| Camera / area share | Which camera-covered area sees more activity? | Horizontal bars | `camera_comparison` fallback |

### 5.2 Daily summary table

Current table columns should change from technical to business:

Current:

```text
Date | Detections | Peak | Avg dwell | Avg conf
```

Recommended:

```text
Date | Visitors / Events | Peak Hour | Avg Dwell | Avg Queue Wait | Alerts
```

If `Avg Queue Wait` or `Alerts` are not available in the same response, either join from loaded hook data in the view model or hide those columns.

### 5.3 Confidence metric

`Avg confidence` should not be a main business metric.

Move it to:

```text
System / Model Quality / Debug
```

If it remains visible in Analyst temporarily, place it under a small technical disclosure section, not in KPI cards.

---

## 6. Queue tab

The Queue tab should answer:

```text
How long did customers wait and which checkout zone caused the most pain?
```

### 6.1 KPI cards

| KPI | Meaning | Data |
|---|---|---|
| Avg queue wait | Average waiting time across queue sessions | `QueueAnalyticsData.kpis` or computed from `zone_stats` |
| Max wait session | Worst wait during selected period | `QueueAnalyticsData.kpis` |
| Total queue sessions | Number of queue sessions | `QueueAnalyticsData.kpis` |
| SLA violations | Number of waits above threshold | future field or derived if session-level data exists |

SLA threshold example:

```text
Wait > 120 seconds = SLA violation
```

### 6.2 Avg wait by hour

Business question:

```text
What time of day produces the worst queue wait?
```

Visualization:

```text
Bar chart
X: hour
Y: avg wait minutes
```

Current data:

```text
QueueAnalyticsData.wait_trend[]
hour
avg_wait_sec
sessions
```

Improve tooltip:

```text
09:00
Avg wait: 0.5 min
Sessions: 12
```

### 6.3 Queue zone breakdown

Business question:

```text
Which checkout queue should be improved?
```

Visualization:

```text
Table or ranked bars
```

Current data:

```text
QueueAnalyticsData.zone_stats[]
zone_id
total_sessions
avg_wait_sec
max_wait_sec
```

Recommended columns:

```text
Queue Zone | Sessions | Avg Wait | Max Wait | Status
```

Status is derived from wait threshold:

```text
Normal / Warning / Critical
```

---

## 7. Zones tab

The Zones tab should answer:

```text
Which store areas attract attention, and which areas are underperforming?
```

Recommended charts:

| Chart | Business question | Visualization | Data needed |
|---|---|---|---|
| Zone ranking | Which zones have the most visitors? | Horizontal bars | zone visitor counts |
| Avg dwell by zone | Where do customers stay longest? | Bar chart | avg dwell sec by zone |
| Zone utilization | Which zones are crowded relative to others? | Bar / table | occupancy or presence share |
| Underused zones | Which zones have low engagement? | Insight list | zone rank + dwell |

Current backend may not fully support this tab yet. If not available, show a clear empty state:

```text
Zone-level Gold metrics are not available yet.
Run or implement Gold zone aggregation to enable this view.
```

Do not fill this tab with unrelated camera share just to avoid emptiness.

---

## 8. Alerts tab

The Alerts tab should answer:

```text
What incidents happened, how severe were they, and where did they occur?
```

### 8.1 KPI cards

| KPI | Meaning | Data |
|---|---|---|
| Total alerts | All alerts in selected period | `AlertHistoryData.records.length` |
| High severity alerts | Serious incidents | records where `severity === 'high'` |
| Most common alert type | Recurring issue | group by `alert_type` |
| Most affected zone | Problem area | group by `zone` |

### 8.2 Alert trend

Business question:

```text
Are incidents increasing over time?
```

Visualization:

```text
Stacked bar chart by day and severity
```

Data:

```text
event_ts
severity
```

### 8.3 Alert history table

Recommended columns:

```text
Time | Alert | Severity | Zone | Camera | Clip/Snapshot | Status
```

Current available data:

```text
alert_id
camera_id
alert_type
severity
title
description
zone
event_ts
clip_s3_key
```

Business UI labels should use human-readable zone names where possible.

---

## 9. Current API to business view model mapping

Use an adapter layer instead of directly rendering API objects.

Recommended file:

```text
features/analytics/adapters/analyticsViewModels.ts
```

Example view models:

```ts
type AnalystOverviewVm = {
  kpis: BusinessKpi[]
  visitorTrend: Array<{ label: string; visitors: number; average?: number }>
  peakHourHeatmap: Array<{ weekday: string; hour: string; value: number }>
  topZones: Array<{ zoneName: string; visitors: number; share: number }>
  insights: Array<{ tone: 'info' | 'warning' | 'critical'; title: string; detail: string }>
}
```

Mapping principle:

```text
API field names can be technical.
View model field names must be business-oriented.
```

---

## 10. Gold layer data wishlist

To make the Analyst tab truly business-grade, the lakehouse should eventually expose these Gold aggregates.

### gold.store_traffic_hourly

```text
store_id
camera_id
hour_bucket
visitor_count
unique_track_count
people_in
people_out
peak_occupancy
```

### gold.store_traffic_daily

```text
store_id
business_date
visitor_count
peak_hour
peak_hour_visitor_count
avg_dwell_sec
alert_count
```

### gold.queue_metrics_hourly

```text
store_id
zone_id
hour_bucket
queue_sessions
avg_wait_sec
max_wait_sec
sla_violation_count
```

### gold.zone_metrics_daily

```text
store_id
zone_id
zone_name
business_date
visitor_count
avg_dwell_sec
presence_share
```

### gold.alert_summary_daily

```text
store_id
business_date
severity
alert_type
zone_id
alert_count
```

These tables are not required for the first UI refactor, but the UI should be designed to grow toward them.

---

## 11. What not to show as main business charts

Avoid using these as headline charts in Analyst:

- raw detection confidence;
- Silver row count;
- technical camera id as a business category unless camera represents a store area;
- model latency;
- container status;
- Pulsar backlog;
- Flink job health.

These are valid system metrics, but not Analyst business metrics.

---

## 12. Acceptance criteria for Codex

The Analyst tab refactor is successful when:

- the page title and labels speak business language;
- filters are clear and not duplicated;
- technical metrics are not used as headline KPIs;
- charts answer explicit business questions;
- Queue and Alert analytics are accessible without long scrolling;
- unsupported filters are disabled honestly;
- current APIs still work through adapter/view-model mapping;
- empty states explain which Gold data is missing.
