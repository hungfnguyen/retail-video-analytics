# Lakehouse Design

## 1. Mục tiêu

Lakehouse là nơi lưu trữ dữ liệu lịch sử và phục vụ phân tích SQL. Dữ liệu trong lakehouse phải có khả năng:

- Lưu raw events để replay và audit.
- Làm sạch và chuẩn hóa detection records.
- Tạo bảng aggregate theo phút, giờ, ngày.
- Truy vấn bằng Trino cho dashboard và phân tích.
- Hỗ trợ schema evolution và partition evolution.

## 2. Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Table format | Apache Iceberg |
| File format | Parquet |
| Object storage | Google Cloud Storage |
| Query engine | Trino |
| Writer | Flink |
| Optional batch/backfill | Flink batch hoặc Python/Spark trong tương lai |

## 3. Medallion architecture

```text
Bronze
  Raw detection frame events, gần giống input contract
    |
    v
Silver
  Cleaned detection objects, track events, normalized coordinates
    |
    v
Gold
  Aggregates: minute metrics, hourly heatmap, daily store KPI
```

## 4. Database namespace

| Namespace | Vai trò |
|---|---|
| `rva_bronze` | Raw hoặc gần raw event data |
| `rva_silver` | Cleaned, flattened, validated records |
| `rva_gold` | Aggregate tables phục vụ dashboard |
| `rva_quality` | Optional: data quality reports |

## 5. Bronze tables

### `rva_bronze.detection_frames`

Lưu một record cho mỗi frame event.

| Column | Type | Ghi chú |
|---|---|---|
| `event_id` | string | Primary logical key |
| `schema_version` | string | Contract version |
| `pipeline_run_id` | string | Lineage |
| `store_id` | string | Store |
| `camera_id` | string | Camera |
| `frame_index` | long | Frame index trong run |
| `capture_ts` | timestamp | Event time |
| `ingest_ts` | timestamp | Producer ingest time |
| `image_width` | int | Width |
| `image_height` | int | Height |
| `frame_uri` | string | Nullable |
| `detections` | array<struct> | Raw detections |
| `raw_payload` | string | Optional JSON raw để audit |
| `event_date` | date | Partition helper |
| `ingested_at` | timestamp | Flink processing time |

Partition đề xuất:

```text
days(event_date), store_id, camera_id
```

Retention:

- Demo: giữ toàn bộ.
- Production direction: 30 đến 90 ngày hoặc theo chi phí.

## 6. Silver tables

### `rva_silver.detections`

Flatten từ `detection_frames`, một row cho mỗi detection object hợp lệ.

| Column | Type | Ghi chú |
|---|---|---|
| `detection_id` | string | `event_id + detection_index` |
| `event_id` | string | Link về frame |
| `store_id` | string | Store |
| `camera_id` | string | Camera |
| `track_id` | int | Nullable nếu không có tracker |
| `event_ts` | timestamp | Từ `capture_ts` |
| `frame_index` | long | Frame |
| `class_name` | string | MVP: person |
| `confidence` | double | Filtered threshold |
| `x1` | int | Bbox |
| `y1` | int | Bbox |
| `x2` | int | Bbox |
| `y2` | int | Bbox |
| `centroid_x` | int | Center |
| `centroid_y` | int | Center |
| `norm_x` | double | `centroid_x / width` |
| `norm_y` | double | `centroid_y / height` |
| `grid_x` | int | Heatmap grid x |
| `grid_y` | int | Heatmap grid y |
| `event_date` | date | Partition helper |

Quality rules:

- `class_name = person`.
- `confidence >= configured threshold`.
- Bbox được clip trong frame.
- `grid_x`, `grid_y` nằm trong grid.

### `rva_silver.track_lifecycle`

| Column | Type | Ghi chú |
|---|---|---|
| `track_event_id` | string | Idempotency key |
| `store_id` | string | Store |
| `camera_id` | string | Camera |
| `track_id` | int | Track |
| `event_type` | string | start/sample/end |
| `event_ts` | timestamp | Time |
| `x` | int | Nullable |
| `y` | int | Nullable |
| `frame_uri` | string | Nullable |
| `event_date` | date | Partition helper |

### `rva_silver.camera_frame_metrics`

Một row cho mỗi frame, dùng để phân tích FPS, count và model behavior.

| Column | Type |
|---|---|
| `event_id` | string |
| `store_id` | string |
| `camera_id` | string |
| `event_ts` | timestamp |
| `frame_index` | long |
| `person_count` | int |
| `avg_confidence` | double |
| `max_confidence` | double |
| `has_frame_uri` | boolean |
| `event_date` | date |

## 7. Gold tables

### `rva_gold.camera_minute_metrics`

| Column | Type | Ghi chú |
|---|---|---|
| `window_start` | timestamp | Minute start |
| `window_end` | timestamp | Minute end |
| `store_id` | string | Store |
| `camera_id` | string | Camera |
| `frame_count` | long | Số frame xử lý |
| `avg_person_count` | double | Trung bình |
| `max_person_count` | int | Peak |
| `unique_tracks` | long | Approx hoặc exact |
| `avg_confidence` | double | Model signal |
| `event_date` | date | Partition |

### `rva_gold.camera_hourly_heatmap`

Lưu sparse heatmap theo giờ.

| Column | Type |
|---|---|
| `hour_start` | timestamp |
| `store_id` | string |
| `camera_id` | string |
| `grid_width` | int |
| `grid_height` | int |
| `heatmap_cells` | array<struct<grid_x:int,grid_y:int,value:double>> |
| `max_value` | double |
| `total_points` | long |
| `event_date` | date |

### `rva_gold.store_daily_metrics`

| Column | Type |
|---|---|
| `date` | date |
| `store_id` | string |
| `total_frames` | long |
| `total_detections` | long |
| `estimated_unique_tracks` | long |
| `peak_hour` | int |
| `peak_person_count` | int |
| `active_camera_count` | int |

## 8. Partitioning strategy

| Table | Partition |
|---|---|
| Bronze detection frames | `days(event_date), store_id, camera_id` |
| Silver detections | `days(event_date), store_id, camera_id` |
| Silver track lifecycle | `days(event_date), store_id, camera_id` |
| Gold minute metrics | `days(event_date), store_id` |
| Gold hourly heatmap | `days(event_date), store_id, camera_id` |
| Gold daily metrics | `date, store_id` |

Không partition theo `track_id` vì cardinality cao và dễ tạo quá nhiều file nhỏ.

## 9. File size và compaction

Streaming write thường tạo nhiều file nhỏ. Cần có kế hoạch compact.

| Setting | Giá trị đề xuất |
|---|---:|
| Target Parquet file size | 128 MB |
| Compaction interval demo | Manual hoặc daily |
| Compaction production | Scheduled |
| Snapshot expiration | Giữ 7 đến 30 ngày tùy demo |

## 10. Trino query examples

### Lượng khách theo giờ

```sql
SELECT
    date_trunc('hour', window_start) AS hour,
    camera_id,
    max(max_person_count) AS peak_count,
    avg(avg_person_count) AS avg_count
FROM rva_gold.camera_minute_metrics
WHERE store_id = 'store_001'
  AND event_date = DATE '2026-05-05'
GROUP BY 1, 2
ORDER BY 1, 2;
```

### Top camera đông nhất

```sql
SELECT
    camera_id,
    max(max_person_count) AS peak_count,
    avg(avg_person_count) AS avg_count
FROM rva_gold.camera_minute_metrics
WHERE event_date >= CURRENT_DATE - INTERVAL '7' DAY
GROUP BY camera_id
ORDER BY peak_count DESC;
```

### Heatmap lịch sử

```sql
SELECT
    hour_start,
    heatmap_cells,
    max_value
FROM rva_gold.camera_hourly_heatmap
WHERE camera_id = 'cam_01'
  AND event_date = DATE '2026-05-05'
ORDER BY hour_start;
```

## 11. Backfill strategy

Backfill cần thiết khi:

- Sửa logic Silver/Gold.
- Đổi confidence threshold.
- Thêm metric mới.
- Reprocess dữ liệu từ Bronze.

Quy trình:

1. Chọn khoảng thời gian và camera cần backfill.
2. Đọc Bronze hoặc Silver theo partition.
3. Ghi vào bảng staging hoặc overwrite partition Gold.
4. Validate row count và metric sanity.
5. Publish dashboard refresh.

## 12. Data quality tables

### `rva_quality.pipeline_quality_daily`

| Column | Type |
|---|---|
| `date` | date |
| `job_name` | string |
| `store_id` | string |
| `camera_id` | string |
| `input_records` | long |
| `valid_records` | long |
| `invalid_records` | long |
| `late_records` | long |
| `duplicate_records` | long |
| `empty_detection_frames` | long |

## 13. Lakehouse success criteria

- Bronze có đủ raw detection frame events.
- Silver flatten được detection objects và filter đúng quality rules.
- Gold query được traffic theo phút/giờ/ngày.
- Trino dashboard query chạy được trên dữ liệu demo.
- Có ít nhất một ví dụ backfill hoặc overwrite partition.
- Có giải thích rõ latency do checkpoint/commit của Iceberg.

