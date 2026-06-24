# Audit: Analytics Tab — Full Issue Report

**Ngày kiểm tra:** 2026-06-24  
**Phạm vi:** Toàn bộ Analytics tab — Overview, Traffic, Queue, Zones, Alerts, Dwell Time + Filter  
**Phương pháp:** Code review + SSH trực tiếp query Trino/Iceberg trên server  
**Tổng issues:** 12 (2 Critical · 6 High · 3 Medium · 1 Low)

---

## Dữ liệu thực tế trên server (query kết quả)

```
Table                    Rows   Date range              Ghi chú
────────────────────────────────────────────────────────────────
traffic_daily              4    Jun 21, Jun 24          ← Jun 22-23 MISSING
traffic_hourly             8    Jun 21, Jun 24          ← chỉ 3 giờ/ngày
dwell_daily                4    Jun 21, Jun 24          ← p50/p90 = NULL
zone_daily                 9    Jun 21, Jun 24          ← zone cũ lẫn mới
queue_daily                6    Jun 21, Jun 24          ← chỉ cam_01
queue_hourly              15    Jun 21, Jun 24          ← chỉ cam_01
alert_daily                0    —                       ← TRỐNG
gold_alerts (Iceberg)      0    —                       ← TRỐNG
heatmap_tile_5min       9435    Jun 21 14:50–16:15      ← chỉ 90 phút 1 ngày
heatmap_tile_hour        1847   Jun 21                  ← chỉ 1 ngày
executive_daily            2    Jun 21, Jun 24          ← peak_hour = "" (TRỐNG)
```

---

## 1. Tab Overview

### Issue 1 — Visitors Over Time chỉ hiển thị 2 điểm dữ liệu (CRITICAL)

**Triệu chứng:** Chọn "Last 7 days" → chart "Visitors Over Time" chỉ có 2 điểm (Jun 21, Jun 24). Jun 22 và Jun 23 không có dữ liệu.

**Root cause:** Dữ liệu Silver bị gián đoạn giữa Jun 21 và Jun 24:
- Jun 21: hệ thống chạy lần đầu, data OK
- Jun 22–23: SilverRealtimeJob bị thay đổi cấu trúc (tách ra từ `SilverJob`) + hệ thống restart → `SilverBackfillJob` chưa được chạy để fill gap
- Jun 24: hệ thống khởi động lại, data OK từ ngày này

**Ảnh hưởng:**
- Tất cả charts có trục ngày sẽ bị "nhảy cóc" từ Jun 21 → Jun 24
- Weekday Pattern chỉ có 2 ngày (Sat + Wed), không đủ đại diện
- Peak Hours Heatmap chỉ có 2 ngày × 3 giờ = 6 ô màu

**Fix:** Chạy `SilverBackfillJob` với `SILVER_BACKFILL_START_DATE=2026-06-22` `SILVER_BACKFILL_END_DATE=2026-06-23`, sau đó re-trigger Airflow DAGs cho 2 ngày đó.

---

### Issue 2 — Visitors by Day of Week (weekday_sql) dùng `detection_count` — sai đơn vị (HIGH)

**File:** `services/api/src/rva_api/api/v1/analytics_queries.py:291`

```sql
SELECT metric_date, SUM(detection_count) AS visitors   -- ← detection events, không phải người
FROM gold_serving_traffic_daily
```

**Kết quả:**
- Jun 21 (Sat): 450,831 "visitors" (thực ra detection events)
- Jun 24 (Wed): 132,643 "visitors"

Chart "Visitors by Day of Week" (Overview tab) và `weekday_pattern` KPI sẽ hiển thị số vô lý.

---

### Issue 3 — Peak Hours Heatmap (Overview) dùng `detection_count` — sai đơn vị (HIGH)

**File:** `services/api/src/rva_api/api/v1/analytics_queries.py:329`

```sql
SELECT ..., SUM(detection_count) AS visitors
FROM gold_serving_traffic_hourly
```

Heatmap sẽ highlight giờ 15:00 Jun 21 với 271,213+60,918 = 332,131 "visitors" — sai × 50 lần.

---

### Issue 4 — Top Zones hiển thị zone_id cũ lẫn mới — nghĩa lịch sử bị lẫn (MEDIUM)

**Server data:**
```
Jun 21: cam_02 → aisle_01 (43,259 detections), promo_area_02 (37,952)
Jun 24: cam_02 → main_aisle (19,730 detections)  ← zone đã đổi tên
```

Khi xem "Last 7 days", Top Zones hiển thị cả `aisle_01`, `promo_area_02` (cũ) lẫn `main_aisle` (mới) — chúng đề cập đến cùng vùng vật lý nhưng khác tên. Tổng share bị phân tán sai.

**Fix:** Backfill dữ liệu Jun 22–23 với zone mới, hoặc document sự thay đổi zone trong UI.

---

## 2. Tab Traffic

### Issue 5 — "Traffic Trend" chart: days=1 (Today) dùng `detection_count`, days>1 dùng `track_count` — inconsistent (HIGH)

**File:** `services/api/src/rva_api/api/v1/analytics_queries.py:259–285`

```python
def visitors_series_sql(days, camera_id=None):
    if days <= 1:
        # ← Today: SUM(detection_count) từ traffic_hourly → SALARIED
        return "SELECT hour_label, SUM(detection_count) AS detections FROM gold_serving_traffic_hourly"
    # ← Last 7/14/30 days: SUM(track_count) từ dwell_daily → CORRECT
    return "SELECT date_label, COALESCE(SUM(track_count), 0) AS detections FROM gold_serving_dwell_daily"
```

**Kết quả:**
- Filter "Today": chart "Traffic Trend" hiện detection events (inflated ×50)
- Filter "Last 7 days": chart hiện unique tracks (đúng)

Cùng 1 chart, cùng label "Visitors", nhưng đơn vị khác nhau tùy filter — **inconsistency nghiêm trọng**.

---

### Issue 6 — Daily Summary table: cột "Peak Hour" luôn trống (HIGH)

**Root cause:** `gold_serving_traffic_daily.peak_hour` = `""` (empty string) cho tất cả rows.

Xác nhận trên server:
```
"2026-06-24","cam_01","","25433"
"2026-06-21","cam_01","","60918"
```

`peak_hour` column không được populate trong batch SQL của Airflow DAG.

**File cần kiểm tra:** `services/flink-jobs/java/src/main/resources/sql/gold-serving/traffic_daily.sql`  
(cột `peak_hour` có thể được tính bằng `MAX_BY` nhưng kết quả không được ghi đúng vào Iceberg)

**Ảnh hưởng:** Cột "Peak Hour" trong Daily Summary table luôn hiện `""` thay vì `"15:00"`.

---

### Issue 7 — "Peak Hour Distribution" bar chart dùng `detection_count` (HIGH)

**File:** `analytics_queries.py:128–145` (`hourly_sql`)
**Frontend:** `TrafficTab.tsx:58` — `dataKey="average"` (= `ROUND(detection_count / days)`)

```sql
SELECT hour_of_day, SUM(detection_count) AS detections,
       ROUND(SUM(detection_count) / NULLIF(COUNT(DISTINCT metric_date), 0)) AS average
FROM gold_serving_traffic_hourly
```

Cả `detections` và `average` đều là detection events, không phải unique visitors. Giờ 15:00 sẽ luôn spike 271,213 detections.

---

## 3. Tab Queue

### Issue 8 — Queue wait time Jun 21 bất thường — dữ liệu anomalous (HIGH)

**Dữ liệu thực tế từ server:**
```
Jun 21:
  checkout_queue_01: avg_wait = 629s (10m 29s), max_wait = 4188s (69m!)
  checkout_queue_02: avg_wait = 775s (12m 55s), max_wait = 4285s (71m!)
  checkout_queue_03: avg_wait = 904s (15m 04s), max_wait = 4270s (71m!)

Jun 24:
  checkout_queue_01: avg_wait = 8.9s, max_wait = 256s
  checkout_queue_02: avg_wait = 23.3s, max_wait = 103s
  checkout_queue_03: avg_wait = 44.3s, max_wait = 163s
```

Jun 24 hợp lý. Jun 21 hoàn toàn bất thường — checkout queue chờ 70 phút?

**Root cause:** Lần deploy đầu tiên (Jun 21), `GoldTrackSummaryJob` bắt đầu tracking từ giữa chừng — các track đã hiện diện trước khi job start được gán `first_seen` = thời điểm job start, trong khi `last_seen` = khi track biến mất. Kết quả: duration_sec = toàn bộ thời gian job chạy thay vì thời gian queue thật.

**Ảnh hưởng:**
- Queue tab: "Avg Queue Wait: 12m 55s", "Longest Wait: 71m" — hoàn toàn sai
- KPI "SLA Violations" hiện `3` (vì avg_wait > 120s threshold) trong khi thực tế không có vi phạm

---

### Issue 9 — Queue tab trống khi filter cam_02 (MEDIUM)

Queue data chỉ tồn tại cho `cam_01` (checkout queues). cam_02 không có queue zone → khi filter "Camera: cam_02", Queue tab hiện empty state.

**UI issue:** Không có thông báo rõ ràng tại sao cam_02 không có queue data — user có thể nghĩ là lỗi.

---

## 4. Tab Zones

### Issue 10 — Zone Utilization % hiển thị avg_occupancy của zone — không phải real capacity % (MEDIUM)

**File:** `ZonesTab.tsx:88`

```tsx
<p className="text-sm font-semibold text-slate-700">{zone.avg_occupancy.toFixed(0)}%</p>
```

`avg_occupancy` từ server = avg số người visible per frame trong zone. Ví dụ `aisle_01` = 2.47 → hiện `2%`. Đây là "số người trung bình" bị cast thành `%` — không có nghĩa là occupancy capacity.

Thanh tiến trình `width: zone.avg_occupancy%` → thanh rất ngắn (2–3%) dù zone đông.

**Fix:** Normalize avg_occupancy theo max zone value để hiện tương đối, hoặc đổi label thành "Avg persons/frame".

---

### Issue 11 — Presence Heatmap endpoint tồn tại nhưng không được dùng (LOW)

`analyticsApi.ts:34` export `getPresenceHeatmapData()` — endpoint đầy đủ, có 9,435 rows dữ liệu thực tế.

**Nhưng** không component nào trong ZonesTab, OverviewTab hay bất kỳ tab nào gọi hàm này.

`data.heatmap = []` luôn trong dashboard response (`analytics.py:597`).

**Kết quả:** 9,435 rows heatmap data trên server nhưng không bao giờ được hiển thị.

---

## 5. Tab Alerts

### Issue 12 — Alerts tab hoàn toàn trống — pipeline không sinh alert (CRITICAL)

**Dữ liệu server:**
```
gold_alerts (Iceberg):  0 rows
alert_daily:            0 rows
```

**Ảnh hưởng:** Toàn bộ Alerts tab:
- 4 metric cards: "Total Alerts: 0", "High Severity: 0", "Most Common Type: —", "Most Affected Zone: —"
- Alert Trend chart: empty state
- Alert History table: empty state

**Root cause (cần điều tra thêm):**
- `GoldAlertsJob` có đang chạy? (`submit-jobs.sh` submit job này với warn-and-continue → có thể fail mà không ai biết)
- Alert thresholds có được configure đúng không?
- `gold_alerts` Iceberg table có được create đúng schema không?

**Cách kiểm tra:**
```bash
# Kiểm tra GoldAlertsJob trên Flink UI
ssh lakehouse-server "curl -s http://localhost:8081/jobs/overview | python3 -m json.tool | grep -A3 'GoldAlertsJob'"
```

---

## 6. Tab Dwell Time

### Issue đã document (đã có file riêng)

- P50 và P90 dwell = NULL trong `gold_serving_dwell_daily` (confirmed server query)
- DwellTab.tsx hiện "—" cho P90 card
- Dwell Trend chart: P50 và P90 lines flat tại 0 (vì `_safe_float(None) = 0.0`)

---

## 7. Filter

### Issue — Zone filter disabled, không có custom date range (MEDIUM)

**AnalyticsFilterBar.tsx:50:**
```tsx
<StaticSelect label="Zone" value="All Zones" disabled />
```

Zone filter render ra UI nhưng không interactive. Các vấn đề:
1. **Zone filter không hoạt động** — user không thể lọc theo zone cụ thể
2. **Chỉ có 4 date preset cố định** (Today, 7d, 14d, 30d) — không có custom date range picker
   - Không thể isolate Jun 21 riêng để xem data chính xác
   - Không thể so sánh "Jun 21 vs Jun 24"
3. **Store filter** cũng là `StaticSelect` không interactive

---

## Tóm tắt: Trạng thái từng tab

| Tab | Trạng thái | Vấn đề chính |
|---|---|---|
| **Overview** | ⚠️ Có data nhưng sai | Số liệu detection_count thay vì visitors, chỉ 2 ngày |
| **Traffic** | ⚠️ Có data nhưng sai | Today dùng detection_count, daily summary thiếu Peak Hour |
| **Queue** | ❌ Data anomalous | Jun 21 avg wait 10–15 phút (bất thường), cam_02 trống |
| **Zones** | ⚠️ Data lẫn lộn | Zone cũ/mới cùng hiển thị, avg_occupancy% sai nghĩa |
| **Alerts** | ❌ Hoàn toàn trống | 0 alerts trong Iceberg |
| **Dwell Time** | ⚠️ Thiếu P50/P90 | NULL percentiles, avg và bands OK |

---

## Ưu tiên fix

| Ưu tiên | Việc cần làm | Effort |
|---|---|---|
| 🔴 1 | Chạy SilverBackfillJob cho Jun 22–23, re-trigger Airflow | Thấp (ops) |
| 🔴 2 | Investigate GoldAlertsJob có đang chạy không | Thấp (debug) |
| 🟠 3 | Fix `visitors_series_sql` days=1 → dùng track_count thay detection_count | Thấp |
| 🟠 4 | Fix `weekday_pattern_sql`, `peak_heatmap_sql`, `hourly_sql` → dùng unique_tracks | Trung bình |
| 🟠 5 | Fix `peak_hour` column trong traffic_daily batch SQL | Trung bình |
| 🟠 6 | Fix Queue anomalous data Jun 21 — xem xét exclude "first-run" tracks | Trung bình |
| 🟡 7 | Wire `getPresenceHeatmapData` vào ZonesTab hoặc OverviewTab | Thấp |
| 🟡 8 | Fix Zone avg_occupancy % label → đổi thành "Avg persons" | Rất thấp |
| 🟡 9 | Thêm custom date range picker vào FilterBar | Trung bình |
| ⚪ 10 | Implement Zone filter functional | Cao |
