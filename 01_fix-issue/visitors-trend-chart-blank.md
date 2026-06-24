# Issue: Visitors Trend chart (Live tab) không hiển thị

**Ngày phát hiện:** 2026-06-24  
**Mức độ:** Medium — chart render nhưng line flat tại y=0, trông như trống  
**Status:** Root cause xác định, chưa fix

---

## 1. Triệu chứng

Tab **Live Monitor** → block **Visitors Trend / Last 60 minutes / Today**:
- Chart render đầy đủ (title, axes, grid)
- Line hoàn toàn bằng phẳng ở y=0
- Tooltip hover hiện `Visitors: 0` cho mọi phút
- Summary footer (`Total in`, `Total out`, `Peak`) hiện 0

---

## 2. Luồng dữ liệu

```
RealtimeMetricsJob (Flink)
  → HINCRBY line:hist:{cam}:{YYYYMMDDHHMM} in_count  1
  → HINCRBY line:hist:{cam}:{YYYYMMDDHHMM} out_count 1
  → TTL = 2h

GET /api/v1/live/{cam}/dashboard  (FastAPI)
  → _traffic_from_redis()
  → đọc 60 bucket line:hist keys qua Redis pipeline
  → trả về traffic: TrafficPoint[]

TrafficChart.tsx (React)
  → <Line dataKey="current_count" />
```

---

## 3. Root Cause

### Flink viết đúng

`RealtimeMetricsJob.java:504` — mỗi line crossing event ghi vào Redis:

```java
String histKey = "line:hist:" + evt.cameraId + ":" + minuteBucket;
jedis.hincrBy(histKey, direction + "_count", 1L);
jedis.expire(histKey, LINE_HIST_EXPIRE_SEC);
```

`people_in` và `people_out` **có data thật** trong Redis.

### Backend hardcode `current_count = 0`

`services/api/src/rva_api/api/v1/live.py:754` — hàm `_traffic_from_redis()`:

```python
points.append({
    "time": bucket_dt.strftime("%H:%M"),
    "people_in": people_in,    # ← đọc từ Redis, có giá trị thật
    "people_out": people_out,  # ← đọc từ Redis, có giá trị thật
    "current_count": 0,        # ← BUG: hardcoded, không bao giờ được tính
})
```

`current_count` được để `0` và chưa bao giờ được implement.

### Frontend dùng đúng `current_count`

`frontend/src/features/live/components/TrafficChart.tsx:67`:

```tsx
<Line
  dataKey="current_count"   // ← đúng field, nhưng field này luôn = 0
  stroke="#4f46e5"
  strokeWidth={2.5}
  ...
/>
```

### Kết quả

```
current_count = 0 cho mọi 60 điểm
→ Recharts vẽ line flat tại y=0
→ YAxis range [0, 0] → chart trông như trống
```

---

## 4. Các file liên quan

| File | Vị trí | Vấn đề |
|---|---|---|
| `services/api/src/rva_api/api/v1/live.py` | line 750–754 (hàm `_traffic_from_redis`) | `current_count` hardcoded = 0 |
| `frontend/src/features/live/components/TrafficChart.tsx` | line 67 (`dataKey`) | Dùng `current_count` — đúng, không cần sửa |
| `services/flink-jobs/java/src/main/java/org/rva/realtime/RealtimeMetricsJob.java` | line 502–506 | Viết `line:hist` đúng — không cần sửa |

---

## 5. Hướng xử lí

### Option A — Tính cumulative occupancy (Đúng nhất)

Sửa `_traffic_from_redis()` trong `live.py`: tính `current_count` là running total `people_in - people_out` tích lũy qua 60 phút.

```python
running_count = 0
for bucket_dt, raw in zip(bucket_times, raw_results):
    raw = raw or {}
    people_in  = _safe_int(...) or 0
    people_out = _safe_int(...) or 0
    running_count = max(0, running_count + people_in - people_out)

    points.append({
        "time": bucket_dt.strftime("%H:%M"),
        "people_in": people_in,
        "people_out": people_out,
        "current_count": running_count,   # ← tính đúng
    })
```

**Ý nghĩa hiển thị:** số người ước tính trong cửa hàng tại mỗi phút (relative occupancy từ đầu window 60 phút).  
**Cons:** không biết giá trị khởi đầu thật — nếu restart, running_count bắt đầu từ 0 dù thực tế đang có người trong store.

---

### Option B — Đổi `dataKey` sang `people_in` (Nhanh nhất)

Sửa `TrafficChart.tsx`: đổi `dataKey="current_count"` → `dataKey="people_in"`.

```tsx
<Line dataKey="people_in" ... />
```

**Ý nghĩa hiển thị:** số người vào cửa hàng mỗi phút — có data thật, chart sẽ hiện ngay.  
**Cons:** không phải "occupancy", chỉ là lượt vào, không trừ lượt ra.  
**Đổi label:** `"Visitors"` → `"People In"` trong Tooltip formatter.

---

### Khuyến nghị

| Tiêu chí | Option A | Option B |
|---|---|---|
| Đúng về semantic | ✅ Occupancy | ⚠️ Chỉ in-flow |
| Effort | Backend thay đổi 1 hàm | Frontend thay đổi 1 dòng |
| Phù hợp thesis demo | ✅ | ✅ |

**Chọn Option A** nếu muốn chart đúng nghĩa "số người trong store".  
**Chọn Option B** nếu muốn fix nhanh trước khi demo.
