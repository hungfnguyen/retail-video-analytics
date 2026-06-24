# Audit: Live Monitor Tab — Full Issue Report

**Ngày kiểm tra:** 2026-06-24  
**Phạm vi:** Tab Live Monitor — toàn bộ frontend + backend API + Flink pipeline  
**Tổng issues:** 9 (1 Critical · 4 High · 3 Medium · 1 Low)

---

## Tổng quan

| # | Issue | Mức độ | Lớp |
|---|---|---|---|
| 1 | Visitors Trend chart flat tại y=0 | High | Redis → API |
| 2 | `count_change_percent` luôn = 0, trend không bao giờ hiện | Medium | API |
| 3 | `_active_track_count` dùng `scan_iter` — O(N) mỗi 2 giây | High | API / Redis |
| 4 | Peak Hour (Live Insights) dùng `detection_count` — sai nghĩa | High | Gold Serving → API |
| 5 | Zone Occupancy bar hiện `%` sai — không phải real occupancy | Medium | Frontend |
| 6 | Pipeline Health fetch nhưng không render | Low | API → Frontend |
| 7 | 3 component không được dùng trong LivePage | Medium | Frontend |
| 8 | Live Insights trống 30 phút đầu sau restart | High | Gold Serving |
| 9 | Trino query chặn request path mỗi 60 giây | Medium | API |

---

## 1. Kết quả triển khai Vision Service

### Issue: Video panel hoạt động đúng — không có bug cứng, nhưng fragile

**Phân tích chain:**

```
Vision (local) → ghi JPEG annotated → runtime/live_frames/{cam_id}.jpg
                → ghi metadata    → runtime/live_frames/{cam_id}.json (hoặc Redis)

Frontend (VITE_LIVE_VIDEO_TRANSPORT ?? 'webrtc')
  → WebRTC: POST /media/live/{cam}/webrtc/offer
           → LatestJpegVideoTrack đọc file .jpg từ disk
           → Nếu fail → fallbackRequired = true
  → MJPEG fallback: <img src="/media/live/{cam}/stream">
           → live_video.py đọc .jpg từ disk
  → Nếu streamUrl = "" → render heatmap blob + bbox overlay từ Redis frame data
```

**Trạng thái:** Hoạt động đúng khi Vision service chạy. Rủi ro:
- `aiortc` là optional import — nếu không install trong API container → WebRTC trả `503`, fallback về MJPEG
- Nếu Vision service chưa chạy (thủ công start sau stack) → `media_status = "missing"` → `image_url = ""` → hiện heatmap overlay không có video thật

**Đánh giá cho thesis:** ✅ Đủ để demo, fallback chain rõ ràng.

---

## 2. Kết quả xử lý dữ liệu thời gian thực (Pulsar → Flink → Redis)

### Issue 1 — Visitors Trend chart luôn flat (HIGH) ← đã có doc riêng

**File:** `services/api/src/rva_api/api/v1/live.py:754`  
**Root cause:** `current_count` hardcode = 0, `TrafficChart` dùng `dataKey="current_count"` → line y=0.

`people_in` và `people_out` (từ `line:hist:{cam}:{YYYYMMDDHHMM}`) đúng, Flink viết đầy đủ. Lỗi thuần ở API.

---

### Issue 2 — `count_change_percent` và `tracks_change_percent` luôn = 0 (MEDIUM)

**File:** `services/api/src/rva_api/api/v1/live.py:1109–1110`

```python
"count_change_percent": 0,   # ← hardcoded
"tracks_change_percent": 0,  # ← hardcoded
```

**Ảnh hưởng frontend** (`LivePage.tsx:193-198`):

```tsx
trend={
  data.stats.count_change_percent !== 0  // ← luôn false
    ? { value: `↑/↓ X% vs previous`, ... }
    : undefined   // ← luôn undefined → trend badge không hiện
}
```

**Kết quả:** Card "Visitors in Store" không bao giờ hiện trend arrow, dù người dùng kỳ vọng thấy tăng/giảm so với trước đó.

**Root cause:** Không có snapshot Redis nào lưu count trước đó để so sánh. Cần thêm `stats:count:prev:{cam}` (e.g., giá trị cách 5 phút).

---

### Issue 3 — `_active_track_count` dùng `scan_iter` — performance regression (HIGH)

**File:** `services/api/src/rva_api/api/v1/live.py:395`

```python
def _active_track_count(client: Any, camera_id: str) -> int:
    return sum(1 for _ in client.scan_iter(match=f"track:active:{camera_id}:*"))
```

**Vấn đề:**
- Frontend poll `/live/{cam}/dashboard` mỗi **2 giây**
- Mỗi call gọi `scan_iter` — đây là lệnh **O(N)** scan toàn bộ Redis keyspace
- Với nhiều track đang active hoặc Redis key nhiều → latency tăng đáng kể
- `scan_iter` không atomic — kết quả có thể inconsistent khi đang có keys bị xóa đồng thời

**Fix:** Dùng Redis INCR/DECR trên `stats:active_count:{cam}` thay vì scan keys.

---

## 3. Kết quả xây dựng Data Lakehouse (Bronze → Silver → Gold → Gold Serving)

### Issue 4 — Peak Hour (Live Insights) dùng `detection_count` — số liệu sai (HIGH)

**File:** `services/api/src/rva_api/api/v1/live.py:769`

```sql
SELECT hour_of_day, SUM(detection_count) AS visitors   -- ← WRONG: frame events
FROM lakehouse.rva_gold_serving.gold_serving_traffic_hourly
```

**Kết quả:** `peak_hour_visitors` hiển thị 332,131 thay vì ~200–500 unique visitors. Đây là cùng root cause với Analytics tab (đã document trong `visitor-count-detection-vs-track.md`).

**Ảnh hưởng:** Card "Peak Hour" trên Live Monitor hiện `332,131 visitors` — con số vô lý với 1 cửa hàng nhỏ.

---

### Issue 5 — Live Insights trống 30 phút đầu sau restart (HIGH) ← liên quan restart-daily-issues

**File:** `services/api/src/rva_api/api/v1/live.py:827–861`

```python
def _live_insights(camera_id: str) -> dict:
    rows = trino_query(_live_insights_sql(camera_id), 5.0)
    # ↑ query gold_serving_dwell_daily, gold_serving_traffic_hourly...
```

`gold_serving_today_refresh` DAG chạy `*/30 * * * *` với `catchup=False`. Sau restart:
- Các `gold_serving_*` tables không có data hôm nay
- `_live_insights` trả về tất cả `0` hoặc `None`
- Card "Peak Hour" hiện `--`, "Dwell Time (Avg)" hiện `—`, "Avg Queue Wait" hiện `—`

**Timeline:** Tối đa 30 phút sau restart → tất cả insights trên Live Monitor trống.

---

## 4. Kết quả xây dựng Dashboard

### Issue 6 — Zone Occupancy bar label `%` sai nghĩa (MEDIUM)

**File:** `frontend/src/features/live/components/ZoneOccupancyPanel.tsx:38`

```tsx
const pct = total > 0 ? Math.round((zone.count / maxCount) * 78) : 0
//                                              ↑ maxCount (zone có nhiều người nhất)
//                                              không phải zone capacity
```

**Vấn đề:**
- `pct` không phải real occupancy capacity (%), nó là "so sánh tương đối với zone đông nhất", scale về 78%
- Zone đông nhất luôn hiện `78%` dù chỉ có 1 người → misleading label
- Màu sắc `red` khi `pct >= 70%` không có nghĩa thực — 1 người trong store → zone đó đỏ ngay

**Ví dụ:** 2 zones, zone A: 3 người, zone B: 2 người → A hiện `78%` (đỏ), B hiện `52%` (cam) — thực tế không có gì là "cao"

**Fix:** Tính `pct = (zone.count / total) * 100` hoặc so với max capacity nếu có config.

---

### Issue 7 — Pipeline Health fetch nhưng không bao giờ render (LOW)

**Backend:** `live.py:1118–1119` gọi `_pipeline_health()` — chạy 4 TCP socket checks (Pulsar:6650, Flink:8081, S3, Trino:8083) mỗi 10 giây.

**Frontend:** `data.pipeline_health` có trong response, nhưng `PipelineHealth` component **không được render** trong `LivePage.tsx`.

```tsx
// LivePage.tsx — không có dòng này:
// <PipelineHealth services={data.pipeline_health} />
```

**Kết quả:**
- API mất ~10–50ms mỗi 10s cho TCP health checks mà không ai dùng kết quả
- Component `PipelineHealth.tsx` tồn tại nhưng orphaned

---

### Issue 8 — 3 component tồn tại nhưng không được render (MEDIUM)

Các component sau được build nhưng không import vào `LivePage.tsx`:

| Component | File | Chức năng |
|---|---|---|
| `PipelineHealth` | `components/PipelineHealth.tsx` | Hiển thị status Pulsar/Flink/Redis/S3/Trino |
| `ZoneRuntimePanel` | `components/ZoneRuntimePanel.tsx` | Zone occupancy + line crossings (view khác) |
| `LiveMetricCards` | `components/LiveMetricCards.tsx` | 4 metric cards (phiên bản cũ hơn) |

`ZoneRuntimePanel` và `LiveMetricCards` có UI đầy đủ và nhận đúng props — chúng đã bị thay thế bởi layout mới trong `LivePage.tsx` nhưng file vẫn còn. Cần xóa hoặc wiring lại.

---

## 5. Đánh giá hiệu năng hệ thống

### Issue 9 — Trino query chặn live dashboard request mỗi 60 giây (MEDIUM)

**File:** `services/api/src/rva_api/api/v1/live.py:834`

```python
INSIGHTS_CACHE_TTL = 60.0  # 60-second cache

def _live_insights(camera_id: str) -> dict:
    rows = trino_query(_live_insights_sql(camera_id), 5.0)  # ← timeout 5s
```

**Timeline:**
```
T+0s:   First poll → Trino query → 2–5s response → API latency spike 2–5s
T+60s:  Cache expires → next poll triggers Trino lại → spike 2–5s
T+120s: Repeat...
```

**Vấn đề:** Frontend poll 2s, nhưng mỗi 60s API response sẽ chậm tới 5s (Trino cold start).  
**Ảnh hưởng thực tế:** Người dùng thấy UI "freeze" nhẹ, latency spike mỗi phút.

**Fix options:**
- Tăng `INSIGHTS_CACHE_TTL` lên 300s (khớp với Redis `analytics:cache` TTL)
- Hoặc chạy insights query trong background task độc lập, không block request

---

## Tóm tắt: Danh sách fix theo ưu tiên

| Ưu tiên | Issue | Effort | Impact |
|---|---|---|---|
| 🔴 1 | Fix `current_count` trong `_traffic_from_redis` (live chart) | Thấp — 1 hàm | Visitors Trend hiện lên ngay |
| 🔴 2 | Fix Peak Hour SQL dùng `unique_tracks` thay `detection_count` | Thấp — 1 SQL | Số liệu insights đúng nghĩa |
| 🟠 3 | Fix `_active_track_count`: dùng counter key thay `scan_iter` | Thấp — API + Flink | API latency ổn định |
| 🟠 4 | Tăng `INSIGHTS_CACHE_TTL` lên 300s | Rất thấp — 1 dòng | Xóa latency spike 60s |
| 🟠 5 | Fix `ZoneOccupancyPanel` pct calculation | Thấp — 1 dòng | Số % có nghĩa thật |
| 🟡 6 | Thêm `PipelineHealth` vào LivePage hoặc xóa TCP check | Thấp | Tránh lãng phí CPU |
| 🟡 7 | Xóa 3 orphaned components hoặc wire lại | Thấp | Code cleanliness |
| 🟡 8 | Trigger `gold_serving_today_refresh` khi startup | Trung bình | Insights sẵn sàng ngay sau restart |
| ⚪ 9 | Implement `count_change_percent` từ Redis snapshot | Trung bình | Trend indicator trên metric card |
