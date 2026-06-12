# Phase 0 Baseline - Lakehouse Analyst Layer

Ngày thực hiện: 2026-06-12

Mục tiêu Phase 0:

- Chốt trạng thái thật của pipeline lakehouse trước khi xây Airflow/mart.
- Sửa lỗi số liệu `unique_tracks` non-additive trong API analytics hiện tại.
- Đo tác động của Iceberg compaction trước khi quyết định build heatmap mart.
- Ghi baseline làm tham chiếu cho các phase sau.

---

## 1. Thay đổi code đã thực hiện

File sửa:

- `services/api/src/rva_api/api/v1/analytics_queries.py`
- `tests/unit/test_analytics_queries.py`

### 1.1. Sửa lỗi `SUM(unique_tracks)`

Trước Phase 0, các query analytics đang cộng `unique_tracks` từ bảng aggregate:

```sql
SUM(daily.unique_tracks)
SUM(unique_tracks)
```

Vấn đề: `unique_tracks` là metric non-additive. Một track có thể xuất hiện ở nhiều ngày, nhiều giờ hoặc nhiều camera bucket. Cộng `COUNT(DISTINCT ...)` từ các bucket nhỏ sẽ đếm trùng.

Sau Phase 0:

- `total_detections`, `avg_conf`, `avg_dwell` vẫn đọc từ Gold tables hiện tại.
- `unique_tracks` được tính lại từ base grain `lakehouse.rva.silver_detections`.
- Track identity dùng:

```sql
CONCAT(camera_id, ':', COALESCE(pipeline_run_id, 'unknown'), ':', CAST(track_id AS varchar))
```

Lý do vẫn dùng `silver_detections` v1:

- `GoldDashboardAggregateJob` hiện vẫn đọc nhánh v1.
- Phase 0 chỉ sửa correctness ở API query layer, chưa migrate toàn bộ dashboard Gold sang v2.
- Việc migrate `GoldDashboardAggregateJob` sang `silver_detections_v2` là quyết định Phase sau.

---

## 2. Verification code

Đã chạy:

```bash
uv run pytest tests/unit/test_analytics_queries.py
uv run ruff check services/api/src/rva_api/api/v1/analytics_queries.py tests/unit/test_analytics_queries.py
```

Kết quả:

```text
tests/unit/test_analytics_queries.py ..... [100%]
5 passed

ruff: All checks passed
```

---

## 3. Runtime stack tại thời điểm đo

Docker services đang chạy:

```text
flink-taskmanager   Up
trino               Up (healthy)
flink-jobmanager    Up (healthy)
iceberg-rest        Up (healthy)
pulsar-broker       Up (healthy)
redis               Up (healthy)
```

FastAPI:

```text
GET /health -> {"status":"ok"}
```

Frontend:

```text
GET http://localhost:5173 -> 200
```

Flink jobs RUNNING:

```text
bronze_raw
silver_detections + silver_detections_v2
gold_track_summary + gold_track_summary_v2
gold_queue_sessions + gold_zone_minute_metrics
gold_camera_hourly_metrics + gold_camera_daily_metrics + gold_camera_daily_dwell + gold_alert_events
gold_alerts
RealtimeMetricsJob
```

Kết luận: pipeline runtime đủ điều kiện để bắt đầu Phase 0 và các Gold jobs quan trọng đã được submit.

---

## 4. Lakehouse row counts sau Phase 0

Kết quả `COUNT(*)` cuối cùng:

| Bảng | Rows |
|---|---:|
| `bronze_raw` | 11,270 |
| `silver_detections` | 39,728 |
| `silver_detections_v2` | 40,423 |
| `gold_track_summary` | 96 |
| `gold_track_summary_v2` | 96 |
| `gold_queue_sessions` | 72 |
| `gold_zone_minute_metrics` | 0 |
| `gold_camera_hourly_metrics` | 1 |
| `gold_camera_daily_metrics` | 1 |
| `gold_camera_daily_dwell` | 1 |
| `gold_alert_events` | 0 |
| `gold_alerts` | 0 |

Nhận xét:

- Bronze/Silver/Gold track/queue đã có dữ liệu.
- Gold dashboard đã materialize, nhưng hiện chỉ có 1 row hourly/daily do stack mới restart và đang trong cùng một ngày/giờ.
- `gold_zone_minute_metrics = 0`, cần kiểm tra logic window/zone input ở phase sau trước khi dựa vào bảng này cho zone mart.
- Alert tables đang 0 vì chưa có alert/clip event trong window đo.

---

## 5. Iceberg file layout trước compaction

### `silver_detections_v2`

```text
file_count: 13
total_bytes: 1,220,563
avg_file_size: 93,889
records: 24,554
snapshot_count: 13
```

### `silver_detections`

```text
file_count: 19
total_bytes: 985,877
avg_file_size: 51,888
records: 36,932
```

### Gold dashboard / queue

```text
gold_camera_hourly_metrics: 18 files
gold_camera_daily_metrics: 18 files
gold_queue_sessions:       13 files
gold_zone_minute_metrics:  0 files
```

Nhận xét:

- Sau restart, số file thấp hơn nhiều so với baseline cũ trong docs (`~2,519 files / ~96K rows`).
- Dù vậy, file vẫn rất nhỏ và query dashboard vẫn chậm.

---

## 6. Compaction đã chạy

Đã chạy `OPTIMIZE` cho các bảng đang phục vụ analytics hiện tại:

```sql
ALTER TABLE lakehouse.rva.silver_detections_v2
EXECUTE optimize(file_size_threshold => '128MB');

ALTER TABLE lakehouse.rva.silver_detections
EXECUTE optimize(file_size_threshold => '128MB');

ALTER TABLE lakehouse.rva.gold_camera_hourly_metrics
EXECUTE optimize(file_size_threshold => '128MB');

ALTER TABLE lakehouse.rva.gold_camera_daily_metrics
EXECUTE optimize(file_size_threshold => '128MB');

ALTER TABLE lakehouse.rva.gold_queue_sessions
EXECUTE optimize(file_size_threshold => '128MB');
```

### Sau compaction

`silver_detections_v2`:

```text
file_count: 1
total_bytes: 1,331,257
avg_file_size: 1,331,257
records: 31,996
snapshot_count: 18
```

`silver_detections`:

```text
file_count: 2
total_bytes: 890,435
avg_file_size: 445,218
records: 38,532
```

Gold:

```text
gold_camera_hourly_metrics: 2 files
gold_camera_daily_metrics:  2 files
gold_queue_sessions:        3 files
```

Nhận xét:

- Compaction giảm rất mạnh số file.
- Snapshot count tăng là bình thường vì `OPTIMIZE` tạo snapshot mới.
- Với Flink streaming jobs, không nên expire snapshots quá aggressive. Retention nên giữ rộng trong dev/demo.

---

## 7. API latency trước và sau compaction

### Trước compaction

`GET /api/v1/analytics/dashboard?days=7`

```text
15.54s
13.50s
11.53s
11.38s
12.54s
```

`GET /api/v1/analytics/heatmap?camera_id=cam_01&days=1`

```text
7.57s
4.07s
1.78s
2.52s
7.58s
```

`GET /api/v1/analytics/heatmap?camera_id=cam_02&days=1`

```text
2.37s
4.50s
1.77s
3.75s
0.93s
```

`GET /api/v1/analytics/queue?days=7`

```text
9.29s
4.67s
3.21s
9.40s
3.20s
```

### Sau compaction

`GET /api/v1/analytics/dashboard?days=7`

```text
4.39s
4.39s
4.46s
4.37s
4.29s
```

`GET /api/v1/analytics/heatmap?camera_id=cam_01&days=1`

```text
2.62s
2.17s
2.04s
2.54s
1.90s
```

`GET /api/v1/analytics/heatmap?camera_id=cam_02&days=1`

```text
1.39s
0.88s
0.89s
0.88s
0.87s
```

`GET /api/v1/analytics/queue?days=7`

```text
2.07s
2.18s
1.75s
1.76s
1.88s
```

Kết luận:

- Compaction cải thiện rõ rệt dashboard và queue.
- Heatmap cũng cải thiện, đặc biệt `cam_02`.
- Dashboard vẫn còn khoảng 4.3s vì API chạy nhiều Trino query và vừa bổ sung exact unique-track query từ Silver. Phase sau nên thêm cache/API query routing hoặc mart nếu cần SLA thấp hơn.

---

## 8. Endpoint correctness sau Phase 0

`GET /api/v1/analytics/dashboard?days=7`:

```text
data_status: ready
total_detections: 39,728
unique_tracks: 96
peak_hour: 06:00
busiest_camera: cam_01
```

`GET /api/v1/analytics/heatmap?camera_id=cam_01&days=1`:

```text
data_status: ready
cells: non-empty
```

`GET /api/v1/analytics/heatmap?camera_id=cam_02&days=1`:

```text
data_status: empty
cells: []
```

Nhận xét:

- `cam_02` heatmap empty ở thời điểm đo không phải lỗi UI. Nó phản ánh snapshot hiện tại không có cell hợp lệ trong window query.
- Cần kiểm tra lại sau khi Vision chạy đủ lâu hoặc khi có dữ liệu `cam_02` mới.

---

## 9. Quyết định kỹ thuật sau Phase 0

### Quyết định 1 - Chưa build full mart ngay

Compaction đã giảm latency đáng kể. Vì vậy Phase tiếp theo không nên nhảy thẳng vào full mart/Airflow lớn.

Thứ tự hợp lý:

1. Đưa Iceberg maintenance thành job định kỳ.
2. Thêm cache cho API analytics.
3. Chỉ build mart cho query nào vẫn chậm sau maintenance/cache.

### Quyết định 2 - Heatmap mart chưa phải blocker ngay

Với dataset hiện tại:

- `silver_detections_v2` sau compaction còn 1 file.
- Heatmap cam_01 khoảng 2s, cam_02 khoảng 1s.

Heatmap mart vẫn đúng cho scale lớn và thesis architecture, nhưng không cần là việc đầu tiên nếu mục tiêu trước mắt là demo ổn định.

### Quyết định 3 - Cần xử lý `gold_zone_minute_metrics = 0`

Trước khi xây zone mart, cần kiểm tra:

- `silver_detections_v2.primary_zone_id` có data không;
- `primary_zone_type` có data không;
- `QueueAnalyticsJob` có đang group đúng window không;
- checkpoint/commit của job queue analytics có tạo output zone không.

### Quyết định 4 - Dual lineage vẫn còn

Hiện tại:

- dashboard traffic/dwell: `silver_detections` v1 -> Gold dashboard;
- heatmap/queue/zone: `silver_detections_v2`.

Phase sau nên quyết định:

- migrate `GoldDashboardAggregateJob` sang v2;
- hoặc document rõ v1 là dependency bắt buộc cho dashboard analytics.

Khuyến nghị: migrate sang v2 sau khi Phase 0 ổn, vì v2 có `global_track_id`, zone, queue, predicted-track flags và khớp với Vision Supervision pipeline mới.

---

## 10. Việc nên làm tiếp theo

### Phase 1 đề xuất

1. Tạo maintenance runner tối thiểu:
   - `OPTIMIZE` hot tables;
   - đo file count;
   - ghi audit.
2. Thêm cache TTL cho API analytics:
   - dashboard: 60-120s;
   - queue: 60-120s;
   - heatmap: 5-15 phút.
3. Debug `gold_zone_minute_metrics = 0`.
4. Quyết định migrate `GoldDashboardAggregateJob` sang `silver_detections_v2`.

### Phase 2 đề xuất

Chỉ build mart đầu tiên nếu sau maintenance/cache vẫn chậm:

- `mart_heatmap_tile_5min`
- `mart_heatmap_tile_hour`

Nếu build mart heatmap, bắt buộc giữ parity với query production hiện tại:

```sql
class_id = 0
is_predicted = false
anchor_x_norm IS NOT NULL
anchor_y_norm IS NOT NULL
LEAST/GREATEST clamp cho grid index
```

Không thêm filter `global_track_id IS NOT NULL` hoặc `anchor BETWEEN 0 AND 1` nếu chưa sửa production query tương ứng.

