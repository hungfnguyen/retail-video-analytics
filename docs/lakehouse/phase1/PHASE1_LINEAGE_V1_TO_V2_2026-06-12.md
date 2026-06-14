# Phase 1 — Item 4: Consolidate Dashboard Lineage v1 → v2

Người thực hiện: Claude (Opus 4.8)
Ngày: 2026-06-12
Mục tiêu: gỡ dual-lineage smell — đưa toàn bộ đường dashboard về **một nguồn sự thật `silver_detections_v2`**.

---

## 1. Vấn đề trước khi sửa

Tầng analyst phụ thuộc **hai nhánh silver song song**:

| Đường | Nguồn (trước) |
|---|---|
| `GoldDashboardAggregateJob` (hourly/daily/dwell/alert_events) | `silver_detections` **v1** + `gold_track_summary` **v1** |
| API unique_tracks recompute (`analytics_queries.py`) | `silver_detections` **v1** |
| Heatmap / queue / zone | `silver_detections_v2` |

Rủi ro: deprecate v1 sẽ làm traffic/dwell dashboard chết âm thầm; hai nhánh có thể lệch số.

---

## 2. Verify column parity (làm trước khi sửa)

`silver_detections_v2` có đủ cột job cần + nhiều hơn:
`store_id, camera_id, capture_ts, track_id, conf, frame_index, class_id` **+ `global_track_id` + `is_predicted`**.

`gold_track_summary_v2` có đủ cột dwell cần: `store_id, camera_id, visit_date, duration_sec` (dùng `global_track_id` thay `track_id`, nhưng dwell không đọc track id).

Hai khác biệt ngữ nghĩa quan trọng của v2:
- **`is_predicted`**: v2 có rows Kalman-interpolated (90 predicted / 10389 real trong window đo). v1 không có. → phải thêm `is_predicted = false` để đếm detection thật, parity với v1.
- **`global_track_id`** dạng `cam_01_g_000001` — **sequence reset theo `pipeline_run_id`**. Để an toàn đa-run/đa-ngày phải đếm distinct theo `CONCAT(pipeline_run_id, ':', global_track_id)`, không dùng global_track_id trần.

---

## 3. Thay đổi đã thực hiện

### 3.1. `GoldDashboardAggregateJob.java` (4 insert)

- **hourly / daily**: `FROM silver_detections` → `silver_detections_v2`; thêm `AND is_predicted = false`; `COUNT(DISTINCT track_id)` → `COUNT(DISTINCT CONCAT(COALESCE(pipeline_run_id,'unknown'), ':', global_track_id))`.
- **dwell**: `FROM gold_track_summary` → `gold_track_summary_v2` (cột dùng giống hệt; v2 per global track = chính xác hơn).
- **alert_events**: `FROM silver_detections` → `silver_detections_v2`; thêm `AND is_predicted = false` (đếm người thật/frame).

### 3.2. `analytics_queries.py` (4 hàm: summary/hourly/camera/daily)

Recompute unique_tracks: `FROM silver_detections` → `silver_detections_v2`; identity `CONCAT(camera_id, pipeline_run_id, track_id)` → `CONCAT(pipeline_run_id, ':', global_track_id)`; filter `track_id IS NOT NULL` → `global_track_id IS NOT NULL AND is_predicted = false`.

### 3.3. `tests/unit/test_analytics_queries.py`

Cập nhật assertion theo expression v2 mới.

---

## 4. Verification

```text
uv run pytest tests/unit/test_analytics_queries.py tests/unit/test_analytics_api.py  -> 9 passed
uv run ruff check ...                                                                -> passed
mvn clean package -DskipTests                                                        -> BUILD SUCCESS
```

Deploy (hot-swap jar + cancel/resubmit qua REST API):
- `GoldDashboardAggregateJob` cancel (JID `dc96004a...`) → resubmit (JID `538922bb...`).
- Job mới **RUNNING, root-exception: none, history: 0**.
- Gold tables commit từ v2: hourly/daily/dwell đều có row (counts nhỏ vì stack mới restart, sẽ tăng dần).
- Dashboard API: `data_status = ready`, không lỗi.
- v2 unique recompute trả **66** distinct global tracks (7 ngày) — hợp lý.

`gold_alert_events = 0`: đúng dự kiến — Flink env `ALERT_DENSITY_THRESHOLD` vẫn = 10 (max thực tế 8). Bảng này mồ côi (không API query), nằm ngoài scope Item 4. (Khác với `gold_alerts` đã hạ ngưỡng ở vision worker — xem PHASE1_ZONE_ALERT_DIAGNOSIS.)

---

## 5. Hệ quả & follow-up

Sau migration, **nhánh v1 giờ là dead weight cho tầng analyst**:
- `silver_detections` (v1) chỉ còn feed `GoldTrackSummaryJob` → `gold_track_summary` (v1).
- `gold_track_summary` (v1) **không còn ai đọc** (dwell đã chuyển sang v2).

→ Follow-up (ngoài scope, quyết định sau): có thể deprecate hẳn `SilverJob` ghi v1 + `GoldTrackSummaryJob` v1 + drop `gold_track_summary` v1 để giảm tải Flink/Iceberg. **Chưa làm** — cần xác nhận không còn debug/drill-down nào dựa vào v1.

⚠️ Deploy bằng hot-swap jar vào container đang chạy. Lần `docker compose build` flink tiếp theo sẽ tự bake source đã sửa.
