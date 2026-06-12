# Query Routing, Cache Và Performance Cho Analyst Layer

Tài liệu này định nghĩa cách FastAPI/Trino/React nên truy cập dữ liệu sau khi có Airflow và mart tables.

## 1. Vấn đề cần giải quyết

Dashboard analyst chậm thường do một hoặc nhiều nguyên nhân:

1. Query trực tiếp `silver_detections_v2`.
2. Query scan quá nhiều ngày/camera.
3. Query thiếu partition filter.
4. Iceberg có nhiều small files.
5. Iceberg snapshot/manifests nhiều.
6. Trino single-node đọc S3 remote.
7. FastAPI không cache kết quả.
8. UI reload tạo nhiều request giống nhau.

Giải pháp không phải chỉ tăng cấu hình Trino. Giải pháp đúng là:

```text
Query đúng bảng + đúng grain + đúng cache + đúng maintenance.
```

## 2. Query routing rule

### Rule chính

```text
Live page -> Redis/runtime media
Analyst page -> mart_* tables
Drill-down -> Gold first, Silver only when needed
Debug/replay -> Bronze/Silver
```

### Mapping endpoint

| Endpoint/UI | Source mới nên dùng | Không nên dùng mặc định |
|---|---|---|
| Live dashboard | Redis | Trino |
| Analytics overview | `mart_executive_daily`, `mart_traffic_hourly` | `silver_detections_v2` |
| Traffic chart | `mart_traffic_hourly` | `silver_detections` |
| Queue analytics | `mart_queue_hourly`, `mart_queue_daily` | raw queue detections |
| Zone analytics | `mart_zone_hourly`, `mart_zone_daily` | direct detection zone rows |
| Heatmap 1d | `mart_heatmap_tile_5min` or `mart_heatmap_tile_hour` | `silver_detections_v2` |
| Heatmap 7d/14d/30d | `mart_heatmap_tile_hour` | `silver_detections_v2` |
| Alert history | `mart_alert_hourly`, `mart_alert_daily`, Gold drill-down | raw media events |
| Debug detection | `silver_detections_v2` | Bronze unless replay needed |

## 3. Heatmap performance rule

Historical heatmap là nơi dễ chậm nhất.

Trước:

```sql
SELECT tile_x, tile_y, count(*)
FROM lakehouse.rva.silver_detections_v2
WHERE camera_id = 'cam_02'
  AND capture_ts >= current_timestamp - interval '7' day
GROUP BY tile_x, tile_y;
```

Vấn đề:

- scan detection-level fact;
- phải tính tile mỗi query hoặc scan columns lớn;
- 7d/14d/30d dễ chậm;
- Trino đọc nhiều file từ S3.

Sau:

```sql
SELECT tile_x, tile_y, sum(detection_count) AS intensity
FROM lakehouse.rva_mart.mart_heatmap_tile_hour
WHERE camera_id = 'cam_02'
  AND bucket_hour >= current_timestamp - interval '7' day
GROUP BY tile_x, tile_y;
```

Lợi ích:

- scan vài nghìn rows thay vì hàng triệu detection rows;
- query ổn định;
- dễ cache;
- dễ normalize intensity.

## 4. API cache design

### Cache location

Dùng Redis hiện có:

```text
analytics:cache:{endpoint}:{hash(params)}
```

Ví dụ:

```text
analytics:cache:heatmap:cam_02:days_7:grid_32x24
analytics:cache:dashboard:store_001:today
analytics:cache:queue:store_001:days_7
```

### Cache payload

Nên cache nguyên response JSON đã serialize:

```json
{
  "status": "ready",
  "generated_at": "...",
  "source": "mart_heatmap_tile_hour",
  "data": {}
}
```

### TTL theo use case

| Data | TTL |
|---|---|
| Live | không dùng analytics cache |
| Overview today | 30-60s |
| Traffic hourly | 1-5 phút |
| Queue analytics | 1-5 phút |
| Alert history | 1-5 phút |
| Heatmap 1d | 5 phút |
| Heatmap 7d/14d/30d | 15-30 phút |
| Daily finalized report | 30 phút - 24 giờ |

### Cache invalidation

Airflow sau khi refresh mart có thể:

1. xóa cache liên quan;
2. hoặc warm lại cache bằng cách gọi API;
3. ghi `refreshed_at` vào payload.

## 5. API response status

Không nên chỉ trả empty array. Cần status để UI phân biệt:

| Status | Ý nghĩa |
|---|---|
| `ready` | mart có data hợp lệ |
| `empty` | query thành công nhưng không có rows |
| `warming` | mart/cache đang chờ refresh |
| `stale` | dữ liệu cũ hơn threshold |
| `error` | query thất bại |

Ví dụ:

```json
{
  "data_status": "stale",
  "source_table": "lakehouse.rva_mart.mart_heatmap_tile_hour",
  "latest_source_ts": "2026-06-10T10:15:00Z",
  "latest_refresh_ts": "2026-06-10T10:20:00Z",
  "message": "Heatmap mart is older than expected but still usable.",
  "heatmap": []
}
```

## 6. Trino query timeout

FastAPI nên có timeout riêng theo endpoint:

| Endpoint | Timeout |
|---|---|
| dashboard overview | 5-10s |
| queue analytics | 10-15s |
| heatmap mart | 10-15s |
| drill-down Silver | 30-60s |
| debug/ad hoc | explicit admin-only |

Nếu query mart vẫn quá 10-15s, đó là tín hiệu mart design hoặc maintenance chưa tốt.

## 7. Iceberg metadata checks

Airflow hoặc debug command nên kiểm tra:

### File count

```sql
SELECT
    count(*) AS file_count,
    sum(file_size_in_bytes) AS total_bytes,
    avg(file_size_in_bytes) AS avg_file_size
FROM lakehouse.rva."silver_detections_v2$files";
```

### Snapshot count

```sql
SELECT
    count(*) AS snapshot_count,
    min(committed_at) AS first_snapshot,
    max(committed_at) AS latest_snapshot
FROM lakehouse.rva."silver_detections_v2$snapshots";
```

### Partition pressure

```sql
SELECT *
FROM lakehouse.rva."silver_detections_v2$partitions"
ORDER BY file_count DESC
LIMIT 20;
```

Nếu `avg_file_size` rất nhỏ hoặc `file_count` cao, cần compaction.

## 8. Maintenance SQL

### Optimize

```sql
ALTER TABLE lakehouse.rva_mart.mart_heatmap_tile_hour
EXECUTE optimize(file_size_threshold => '128MB')
WHERE metric_date >= CURRENT_DATE - INTERVAL '7' DAY;
```

### Optimize manifests

```sql
ALTER TABLE lakehouse.rva_mart.mart_heatmap_tile_hour
EXECUTE optimize_manifests;
```

### Expire snapshots

```sql
ALTER TABLE lakehouse.rva_mart.mart_heatmap_tile_hour
EXECUTE expire_snapshots(retention_threshold => '7d', retain_last => 20);
```

### Remove orphan files

```sql
ALTER TABLE lakehouse.rva_mart.mart_heatmap_tile_hour
EXECUTE remove_orphan_files(retention_threshold => '7d');
```

### Analyze

```sql
ANALYZE lakehouse.rva_mart.mart_heatmap_tile_hour
WITH (columns = ARRAY['store_id', 'camera_id', 'metric_date', 'tile_x', 'tile_y']);
```

## 9. Cẩn thận với streaming Iceberg jobs

Không cleanup quá aggressive trên bảng mà Flink streaming đang ghi hoặc đang đọc incremental.

Rule an toàn cho dev/demo:

```text
Không expire snapshots dưới 7 ngày.
Không remove orphan files dưới 7 ngày.
Không optimize toàn bộ bảng lớn trong giờ demo.
Ưu tiên optimize mart tables trước, rồi Gold, sau đó mới Silver.
```

Lý do:

- Flink commit Iceberg sau checkpoint thành công;
- streaming jobs cần lịch sử snapshot/checkpoint ổn định;
- remove orphan sai thời điểm có thể ảnh hưởng job đang chạy hoặc retry.

## 10. Performance budget cho analyst API

Mục tiêu:

| API | P50 | P95 |
|---|---:|---:|
| Overview cached | < 100ms | < 300ms |
| Overview uncached mart | < 1s | < 3s |
| Heatmap cached | < 100ms | < 300ms |
| Heatmap uncached mart | < 2s | < 10s |
| Queue cached | < 100ms | < 300ms |
| Queue uncached mart | < 2s | < 10s |
| Silver drill-down | không cam kết cho dashboard chính |

## 11. UI behavior

UI nên hiển thị rõ:

- data_status;
- latest_refresh_ts;
- source table hoặc badge `mart`;
- empty state khác với error state;
- stale warning nếu dữ liệu cũ.

Không nên:

- spinner vô hạn;
- blank page;
- retry liên tục không backoff;
- query lại mỗi vài giây cho historical dashboard.

## 12. Kết luận

Analyst performance không nên dựa vào việc Trino scan nhanh bảng Silver. Thiết kế đúng là:

```text
Airflow refresh mart tables.
Airflow maintain Iceberg.
FastAPI cache response.
React chỉ query semantic endpoints.
```

Khi đó analyst dashboard sẽ giống data warehouse truyền thống: dữ liệu cuối đã chuẩn bị sẵn, query nhỏ, ổn định và dễ demo.
