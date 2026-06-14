# Analyst Dashboard Tab - Business Chart and Data Specification

This file defines the chart inventory for the **Analyst Dashboard** tab. The page should turn Gold lakehouse metrics into business insight, not simply expose raw detection rows.

The page should answer:

```text
How did the store perform?
When were customers most active?
Where did customers spend time?
How did queues affect customer experience?
What incidents happened and where?
What changed compared with the previous period?
```

---

## 1. Target user

Primary user:

```text
Retail manager / operations analyst / business stakeholder
```

They care about historical business performance:

- visitor volume;
- peak periods;
- queue performance;
- zone utilization;
- dwell time;
- alerts/incidents;
- comparison across time, cameras, and zones.

They should not need to understand:

- Bronze/Silver/Gold implementation details;
- raw detection confidence;
- raw table names;
- data engineering internals.

---

## 2. Main design rule

Use this mental model:

```text
Gold layer metrics -> business questions -> chart -> action
```

Do not use this mental model:

```text
API response exists -> render a card/chart
```

The current Analytics page exposes some technical metrics such as detections, camera share, confidence, and lakehouse layer labels. These can exist as secondary/debug labels, but they should not be the main story.

---

## 3. Required filters

Top filter bar:

```text
Store       [Store A]
Camera      [All Cameras]
Zone        [All Zones]
Date Range  [Last 7 days]
Refresh
```

Current backend mainly supports `days`. Therefore:

- `Date Range` must control current `days` API parameter.
- `Store`, `Camera`, and `Zone` should be rendered only if supported, or shown disabled with a clear tooltip.
- Do not visually imply a filter is active if it does not change the query.

Recommended date options:

```ts
today
yesterday
last_7_days
last_14_days
last_30_days
custom // future
```

---

## 4. Recommended internal tabs

Use internal tabs inside the Analyst page:

```text
Overview | Traffic | Queue | Zones | Alerts
```

Do not put everything into one long scroll. Each tab should answer a distinct business question.

---

# 5. Overview tab

Purpose:

```text
Executive summary of store performance for the selected period.
```

## 5.1 KPI row

| KPI | Business question | Current/future data | Chart type | Action |
|---|---|---|---|---|
| Total Visitors | How much traffic did the store receive? | Prefer Gold visitor count. Current fallback: `daily_summary.detections` or existing KPI | Metric card | Compare demand across periods |
| Peak Day | Which day was busiest? | `daily_summary` | Metric card | Prepare staffing for similar days |
| Peak Hour | What hour was busiest? | `hourly_traffic` or daily peak | Metric card | Adjust staff schedule |
| Avg Dwell Time | Are customers engaging? | `avg_dwell_sec` | Metric card | Evaluate layout/promotion engagement |
| Avg Queue Wait | How was checkout experience? | `queueData.kpis` / `zone_stats` | Metric card | Identify service bottleneck |
| Alert Count | How many incidents happened? | `alertHistoryData.records` | Metric card | Review operational risk |

Important label rule:

```text
If the backend value is raw detection events, label it as "Observed visitor events".
If you can deduplicate into real visitors/tracks, label it as "Visitors".
```

Do not mislead the user by calling raw detections unique customers.

---

## 5.2 Visitors Over Time

Chart type:

```text
Line chart or area chart
```

Business question:

```text
Is store traffic increasing, decreasing, or stable over the selected period?
```

Data:

| Current source | Future ideal source |
|---|---|
| `data.hourly_traffic` for hourly view | `gold_traffic_hourly` or `gold_traffic_daily` |
| `data.daily_summary` for daily view | `gold_store_kpi_daily` |

Recommended series:

```text
visitors / observed visitor events
previous period comparison, optional
moving average, optional
```

Design notes:

- For `today` or `1d`, use hourly x-axis.
- For `7d+`, use daily x-axis if available.
- Tooltip should show exact value and time bucket.
- Use previous-period comparison only if available or computed safely.

Business action:

- staffing and inventory planning;
- evaluate whether promotion caused traffic increase;
- detect sudden drop in traffic.

---

## 5.3 Visitors by Day of Week

Chart type:

```text
Bar chart
```

Business question:

```text
Which weekday brings the most traffic?
```

Data:

```text
Aggregate daily traffic by weekday over selected range.
```

Current fallback:

- If only one day exists, show an empty state: `Need at least 7 days to compare weekdays`.
- Do not render a fake weekly chart from one data point.

Business action:

- schedule more staff on high-traffic weekdays;
- choose promotion days.

---

## 5.4 Peak Hours Heatmap

Chart type:

```text
Calendar-style heatmap / hour-of-day heatmap
```

Recommended axes:

```text
Y-axis: day of week
X-axis: hour of day
Cell value: visitors or observed events
```

Business question:

```text
Which hour/day combinations are busiest?
```

Data needed:

```text
gold_traffic_hourly(date, day_of_week, hour, visitor_count)
```

Current fallback:

- If only `hourly_traffic` exists without day-of-week dimension, render a simple `Hourly traffic` bar/line chart instead.
- Mark full day-hour heatmap as future backend support if not available.

Business action:

- staffing by hour;
- checkout lane planning;
- cleaning/restocking schedule.

---

## 5.5 Top Zones by Visitors

Chart type:

```text
Ranked horizontal bar chart or ranked list
```

Business question:

```text
Which store areas attract the most customers?
```

Data needed:

```text
gold_zone_traffic_daily / gold_zone_traffic_hourly
zone_id
zone_name
visitor_count
traffic_share
```

Current fallback:

- Use queue zone stats only for queue zones, but label clearly as `Top Queue Zones`, not `Top Store Zones`.
- Do not use camera share as a replacement for zone performance.

Business action:

- optimize product placement;
- understand promotion visibility;
- identify underused areas.

---

# 6. Traffic tab

Purpose:

```text
Deep dive into customer traffic patterns.
```

Recommended charts:

| Chart | Type | Business data | User question |
|---|---|---|---|
| Traffic Trend | Line/area | visitors by hour/day | Is traffic growing or declining? |
| Peak Hour Distribution | Bar | visitors by hour-of-day | What hours need more staff? |
| Daily Summary Table | Table | date, visitors, peak hour, avg dwell, alerts | What happened each day? |
| Camera Coverage, secondary | Small ranked list | camera contribution | Which camera/source produced most observations? |

Important:

- `Camera Coverage` is secondary technical context.
- Do not make `Busiest camera` a top KPI because it rarely maps to a business decision.

Daily summary recommended columns:

```text
Date
Visitors / Observed Events
Peak Hour
Avg Dwell
Avg Queue Wait
Alerts
```

Remove or demote:

```text
Avg confidence
```

unless this is a data quality/debug section.

---

# 7. Queue tab

Purpose:

```text
Understand checkout service quality and waiting-time problems.
```

## 7.1 Queue KPI row

| KPI | Source | Business meaning |
|---|---|---|
| Avg Queue Wait | `queueData.kpis` or avg `zone_stats.avg_wait_sec` | Normal customer wait experience |
| Longest Wait | max `zone_stats.max_wait_sec` | Worst customer experience |
| Queue Sessions | sum `zone_stats.total_sessions` | Volume of queue interactions |
| SLA Violations | future `wait_sec > threshold` | Service quality failures |

Recommended threshold:

```text
Queue SLA target: wait <= 120 seconds
```

## 7.2 Avg Wait by Hour

Chart type:

```text
Bar chart
```

Current data:

```ts
queueData.wait_trend.hour
queueData.wait_trend.avg_wait_sec
queueData.wait_trend.sessions
```

Business question:

```text
At what times do customers wait the longest?
```

Business action:

- schedule cashiers during high wait windows;
- investigate checkout process bottlenecks.

## 7.3 Queue Zone Breakdown

Chart/table type:

```text
Ranked table
```

Current data:

```ts
queueData.zone_stats
```

Recommended columns:

```text
Queue Zone
Sessions
Avg Wait
Max Wait
Status
```

Sort by:

```text
Max Wait desc, then Avg Wait desc
```

Business action:

- identify worst-performing checkout queue.

## 7.4 Queue SLA Violations

Chart type:

```text
Stacked bar or count card
```

Future data needed:

```text
queue_session_id
zone_id
start_ts
end_ts
wait_sec
sla_target_sec
sla_violated boolean
```

Current fallback:

- If backend does not provide session-level violation count, do not fake it.
- Show a disabled/empty section: `Requires queue session SLA metric`.

---

# 8. Zones tab

Purpose:

```text
Understand how customers use physical store areas.
```

Recommended charts:

| Chart | Type | Business data | User question |
|---|---|---|---|
| Zone Visitor Ranking | Horizontal bar | visitor count by zone | Which zones are most visited? |
| Dwell Time by Zone | Bar/table | avg dwell seconds by zone | Where do customers spend time? |
| Zone Utilization | Progress bars | occupancy / capacity or relative share | Which zones are under/overused? |
| Zone Trend | Line small multiples | visitor count by time per zone | Is a zone improving or declining? |

Future ideal data contract:

```ts
type ZoneAnalyticsRow = {
  zone_id: string
  zone_name: string
  zone_type: 'queue' | 'entrance' | 'aisle' | 'shelf' | string
  visitor_count: number
  traffic_share: number
  avg_dwell_sec: number
  peak_hour: string
  alerts_count: number
}
```

Current fallback:

- Use `queueData.zone_stats` for queue zones only.
- Do not present queue-only data as whole-store zone analytics.

Business action:

- adjust product placement;
- evaluate promotion zone effectiveness;
- detect dead zones in the store layout.

---

# 9. Alerts tab

Purpose:

```text
Review incident history and operational risk.
```

Current data:

```ts
alertHistoryData.records
```

Recommended charts:

| Chart | Type | Business data | User question |
|---|---|---|---|
| Alert Count by Severity | Stacked bar / donut | high/medium/low counts | How serious were incidents? |
| Alert Trend | Line/bar over time | count by day/hour | Are incidents increasing? |
| Alert Type Breakdown | Bar | count by alert_type | What kind of problems happen most? |
| Alert History Table | Table | records | Which incidents need follow-up? |

Alert history recommended columns:

```text
Time
Alert
Severity
Camera
Zone
Clip/Snapshot
Status
```

Business action:

- identify repeated operational problems;
- review evidence;
- tune staffing/layout.

---

## 10. Chart priority for implementation

P0, implement first with current data:

```text
1. Filter bar with meaningful labels
2. Overview KPI row
3. Visitors Over Time
4. Queue tab: Queue KPI + Avg Wait by Hour + Queue Zone Breakdown
5. Alerts tab: Alert History + Alert Severity Summary if records exist
```

P1, implement when backend provides better Gold metrics:

```text
1. Peak Hours day-hour heatmap
2. Top Zones by Visitors
3. Dwell Time by Zone
4. Zone Utilization
5. Alert Type Breakdown
```

P2, advanced analytics:

```text
1. Previous period comparison
2. Forecasted traffic
3. Anomaly indicators
4. STL trend/seasonality/residual insights
```

---

## 11. Labels to prefer

Use business labels:

```text
Visitors
Observed visitor events
Peak hour
Avg dwell time
Avg queue wait
Queue sessions
Alerts
Zone utilization
```

Avoid primary labels:

```text
Detections
Silver rows
Gold lakehouse
Avg confidence
Busiest camera
```

Technical labels can appear in small data-source badges or System page, not as the main story.

---

## 12. Acceptance checklist

Analyst Dashboard is acceptable when:

- user can answer store performance questions from the first screen;
- filters are understandable and not duplicated;
- charts are grouped by business topic;
- queue and alert insights are not buried at the bottom of a long page;
- raw detection/confidence metrics are not main KPIs;
- the page can gracefully handle incomplete backend data without showing misleading charts.
