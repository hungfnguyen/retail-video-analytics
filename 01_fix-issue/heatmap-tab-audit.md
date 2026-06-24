# Audit: Heatmap Tab — Full Issue Report

**Ngày kiểm tra:** 2026-06-24  
**Phạm vi:** Tab Heatmap — frontend + backend API + Iceberg data + filter theo camera & ngày  
**Phương pháp:** Code review + SSH query Trino/Iceberg + API call từ bên trong container  
**Tổng issues:** 7 (1 Critical · 3 High · 2 Medium · 1 Low)

---

## Dữ liệu thực tế trên server (query kết quả)

```
Table                        Rows    Date range              Ghi chú
─────────────────────────────────────────────────────────────────────
gold_serving_heatmap_tile_5min  9435   Jun 21 14:50–16:15    ← chỉ 90 phút, 1 ngày
gold_serving_heatmap_tile_hour  1847   Jun 21 14:00–16:00    ← chỉ 3 giờ, 1 ngày

Breakdown theo camera (tile_5min):
  cam_01: 3758 rows
  cam_02: 5677 rows

Grid size: tile_x ∈ [0, 31] (cols), tile_y ∈ [0, 23] (rows) → 32×24 = 768 cells max
```

**API response (test từ trong API container):**

```
cam_01, days=1  (Today Jun 24)   → status: "empty"     ← TODAY LUÔN TRỐNG
cam_01, days=7  (Last 7 days)    → status: "ready", 269 cells
cam_01, days=14 (Last 14 days)   → status: "ready", 269 cells  ← GIỐNG HỆT 7d
cam_02, days=7  (Last 7 days)    → status: "ready", 470 cells
snapshot.jpg endpoint            → HTTP 200 khi Vision đang chạy
```

---

## 1. Issue 1 — Filter "Today" luôn trả về trạng thái trống (CRITICAL)

**Triệu chứng:** Chọn filter bất kỳ camera + date preset "Today" → Heatmap page hiện empty state ("No heatmap data available for this period").

**Root cause:**

`heatmap_presence_sql()` trong `analytics_queries.py`:

```python
def heatmap_presence_sql(days: int, camera_id: str = None):
    if days <= 1:
        table = "gold_serving_heatmap_tile_5min"   # chỉ có data Jun 21
        where  = "metric_ts >= NOW() - INTERVAL '24' HOUR"
    else:
        table = "gold_serving_heatmap_tile_hour"
```

`gold_serving_heatmap_tile_5min` chỉ có data Jun 21, 14:50–16:15.

Hôm nay là Jun 24 → không có bản ghi nào thỏa `metric_ts >= NOW() - 24h` → API trả về `cells: []`, `status: "empty"`.

**Root cause sâu hơn:** `heatmap_tile_5min` được populate bởi Flink `HeatmapPresenceJob` (streaming job). Job này chạy ngày Jun 21 nhưng bị dừng và không tiếp tục viết data cho Jun 22–24. Tương tự như dữ liệu silver bị gap Jun 22–23 — pipeline không chạy liên tục.

**Ảnh hưởng:**
- Filter "Today" hoàn toàn vô dụng — không bao giờ hiện data trong điều kiện hiện tại
- Người dùng không có thông báo rõ ràng vì sao không có data

---

## 2. Issue 2 — Tất cả date preset 7d / 14d / 30d trả về cùng 1 dataset (HIGH)

**Triệu chứng:** Chọn "Last 7 days", "Last 14 days", hoặc "Last 30 days" đều hiện **cùng heatmap pattern** — cam_01 luôn 269 cells, cam_02 luôn 470 cells.

**Root cause:**

```
gold_serving_heatmap_tile_hour  → chỉ có data Jun 21, 14:00–16:00
                                  ← WHERE metric_date >= CURRENT_DATE - INTERVAL '7' DAY
                                  ← WHERE metric_date >= CURRENT_DATE - INTERVAL '14' DAY
                                  ← (đều match cùng 1847 rows)
```

Tất cả preset ≥ 2 ngày dùng `tile_hour`, nhưng bảng này chỉ có 1 ngày data (Jun 21). Kết quả sau aggregation: heatmap không thay đổi dù chọn 7d hay 30d.

**Ảnh hưởng:**
- Người dùng mất đi khả năng so sánh pattern theo thời gian
- 3 trong 4 date preset về thực chất trả về cùng kết quả → misleading UX

---

## 3. Issue 3 — Heatmap chỉ có 90 phút coverage — quá ít để đại diện (HIGH)

**Phân tích dữ liệu:**

```
Toàn bộ heatmap data:
  Jun 21, 14:50 → 16:15  (85 phút)
  → Không có data sáng (9:00–14:00)
  → Không có data tối (sau 16:15)
  → Không có Jun 22, 23, 24 hoàn toàn
```

`HeatmapPresenceJob` (Flink) chỉ chạy trong 90 phút ngày Jun 21, sau đó dừng hoặc không được submit lại khi restart.

**Ảnh hưởng thực tế:**
- 269/470 cells active cam_01/cam_02 chỉ đại diện cho 90 phút buổi chiều
- Hot zones trên heatmap không phản ánh pattern thực tế trong ngày
- Giá trị thesis demo bị giảm — heatmap cần ít nhất 1 ngày đầy đủ để có ý nghĩa

**Hướng xử lý:** Chạy lại `HeatmapPresenceJob` và đảm bảo job được submit trong startup script (`submit-jobs.sh`) — kiểm tra xem job này có trong danh sách submit không.

---

## 4. Issue 4 — Camera list hardcoded trong frontend (HIGH)

**File:** `frontend/src/features/heatmap/HeatmapPage.tsx`

```tsx
const CAMERA_IDS = ['cam_01', 'cam_02']   // ← hardcoded
```

Danh sách camera không được fetch từ API. Thêm camera mới (cam_03, cam_04) vào hệ thống yêu cầu sửa code frontend + rebuild.

**So sánh với Live tab:** `LivePage.tsx` cũng hardcode camera list — đây là pattern lặp lại.

**Fix:** Gọi `GET /api/v1/cameras` (endpoint đã tồn tại) để lấy danh sách camera động.

---

## 5. Issue 5 — Background snapshot.jpg không hiện nếu Vision chưa chạy (MEDIUM)

**File:** `frontend/src/features/heatmap/components/HeatmapViewer.tsx:47`

```tsx
src={`${API_BASE_URL}/media/live/${cameraId}/snapshot.jpg`}
```

**Behavior của endpoint `snapshot.jpg`:**

```python
@router.get("/{camera_id}/snapshot.jpg")
def get_live_snapshot(camera_id: str) -> Response:
    frame = _wait_for_frame_bytes(camera_id)   # ← BLOCKING wait
    return Response(content=frame, media_type="image/jpeg")
```

`_wait_for_frame_bytes` poll Redis với timeout. Nếu Vision không chạy:
- Request bị block đến timeout (mặc định 10s)
- Sau timeout: raise exception → API trả 500
- Frontend `<img>` nhận lỗi → render **ảnh broken icon** (không có fallback)
- Heatmap overlay vẫn render, nhưng không có camera background → overlay trôi nổi trên nền trắng

**Khi test (Jun 24, Vision đang chạy):** HTTP 200 ✅

**Ảnh hưởng khi Vision không chạy:** Background image không hiện, heatmap grid không có context visual → khó đọc vị trí hotspot.

**Fix:** Thêm `onError` handler cho `<img>` để hiện placeholder camera frame thay vì broken icon.

---

## 6. Issue 6 — "Show Zones" checkbox disabled vĩnh viễn (MEDIUM)

**File:** `frontend/src/features/heatmap/components/HeatmapSettingsPanel.tsx:35`

```tsx
<input
  className="accent-blue-600"
  disabled          // ← permanently disabled
  type="checkbox"
/>
```

Tính năng zone overlay trên heatmap **chưa được implement** nhưng UI control vẫn hiển thị. Người dùng nhìn thấy checkbox nhưng không thể click.

**Ảnh hưởng:** Misleading — người dùng kỳ vọng có thể toggle zone overlay, nhưng không thể.

**Fix ngắn hạn:** Ẩn checkbox bằng `hidden` attribute hoặc thêm tooltip "Coming soon".

---

## 7. Issue 7 — Hotspot labels không biết zone — chỉ dùng vị trí tương đối (LOW)

**File:** `frontend/src/features/heatmap/adapters/heatmapViewModels.ts`

```ts
function describeCellLocation(tileX: number, tileY: number, gridCols: number, gridRows: number): string {
  // Chia grid thành 9 vùng (upper/middle/lower × left/center/right)
  // Trả về: "upper-left area", "center area", "lower-right area", ...
}
```

`TopHotspotsList` component hiện top 5 hotspots với labels như:

```
#1: upper-right area     (tile 28, 4) — 89 intensity
#2: center area          (tile 16, 12) — 75 intensity
```

Không có mapping nào từ `(tile_x, tile_y)` → tên zone thực tế (vd: "Checkout Counter 1", "Main Aisle", "Promo Area").

**Ảnh hưởng:** Insights panel nói "hotspot at upper-right area" nhưng không giúp ích thực tế — manager cần biết đây là khu vực nào trong cửa hàng.

**Fix:** Implement zone config (`zones.yaml` đã có `region` polygon) → map tile vào zone → hiện tên zone trong hotspot label.

---

## 8. Không phải issue: Filter theo camera hoạt động đúng

Cả cam_01 và cam_02 đều có data riêng biệt và filter hoạt động đúng:
- cam_01: 3758 rows 5min / 269 active cells 7d
- cam_02: 5677 rows 5min / 470 active cells 7d

API filter `?camera_id=cam_01` và `?camera_id=cam_02` trả về đúng subset data.

---

## Tóm tắt

| Tab/Feature | Trạng thái | Vấn đề chính |
|---|---|---|
| **Heatmap Today** | ❌ Luôn trống | Không có data Jun 24 trong heatmap tables |
| **Heatmap 7d/14d/30d** | ⚠️ Data cũ, giống nhau | Tất cả preset trả cùng 90-phút Jun 21 dataset |
| **Filter camera** | ✅ Hoạt động đúng | cam_01 vs cam_02 tách biệt đúng |
| **Background image** | ⚠️ Fragile | Fail silently nếu Vision không chạy |
| **Zone overlay** | ❌ Chưa implement | Checkbox disabled vĩnh viễn |
| **Hotspot labels** | ⚠️ Generic | Không biết zone, chỉ vị trí tương đối |
| **Camera list** | ⚠️ Hardcoded | Thêm camera mới phải sửa code |

---

## Ưu tiên fix

| Ưu tiên | Việc cần làm | Effort |
|---|---|---|
| 🔴 1 | Đảm bảo `HeatmapPresenceJob` được submit khi restart → có data Jun 24 | Thấp (ops) |
| 🔴 2 | Kiểm tra `submit-jobs.sh` có include HeatmapPresenceJob không | Rất thấp (debug) |
| 🟠 3 | Thêm `onError` fallback cho `<img>` snapshot background | Rất thấp |
| 🟠 4 | Fetch camera list từ API thay vì hardcode | Thấp |
| 🟡 5 | Ẩn hoặc tooltip "Coming soon" cho "Show Zones" checkbox | Rất thấp |
| 🟡 6 | Map tile coordinates → zone name trong hotspot labels | Trung bình |
| ⚪ 7 | Implement zone polygon overlay trên heatmap canvas | Cao |
