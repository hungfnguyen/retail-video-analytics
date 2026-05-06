# Streaming Pipeline

## 1. Mục tiêu

Streaming pipeline xử lý detection events từ Pulsar để tạo hai nhóm output:

1. Realtime output cho live dashboard và cảnh báo.
2. Analytical output cho Iceberg lakehouse.

Thiết kế dùng Apache Flink vì cần event time, watermark, stateful processing, window aggregation và checkpointing.

## 2. Topology tổng thể

```text
Pulsar detection-frames-v1
    |
    v
Flink source
    |
    v
Parse + schema validation
    |
    +--> invalid events -> DLQ
    |
    v
Assign event time + watermark
    |
    v
Deduplicate by event_id
    |
    +-----------------------------+
    |                             |
    v                             v
Realtime branch              Lakehouse branch
    |                             |
    +--> live count -> Redis      +--> Bronze Iceberg
    +--> heatmap -> Redis         +--> Silver detections
    +--> alerts -> Redis/Postgres +--> Gold aggregates
    +--> metrics -> Prometheus
```

## 3. Flink jobs đề xuất

| Job | Input | Output | Vai trò |
|---|---|---|---|
| `DetectionIngestJob` | Pulsar detection frames | Bronze Iceberg, DLQ | Validate, dedup, lưu raw structured event |
| `RealtimeMetricsJob` | Pulsar detection frames | Redis, PostgreSQL alerts | Live count, heatmap, active tracks, alert |
| `SilverCurationJob` | Bronze hoặc Pulsar | Silver Iceberg | Flatten detections, clean bbox, filter confidence |
| `GoldAggregationJob` | Silver Iceberg stream/table | Gold Iceberg | Minute/hour/day aggregate |
| `SystemMetricsJob` | Logs/metrics topic | Prometheus/PostgreSQL | Service health và pipeline health |

MVP có thể gộp `DetectionIngestJob`, `RealtimeMetricsJob` và `SilverCurationJob` trong ít job hơn. Khi viết báo cáo, nên trình bày logical jobs rõ ràng dù triển khai ban đầu gộp.

## 4. Event time và watermark

Detection events từ camera có thể đến trễ vì:

- RTSP/network jitter.
- Vision inference chậm.
- Pulsar broker backlog.
- Worker restart và retry.

Đề xuất:

| Setting | Giá trị MVP | Ghi chú |
|---|---:|---|
| Event time field | `capture_ts` | Thời điểm frame được đọc |
| Watermark delay | 5 giây | Chấp nhận event trễ nhẹ |
| Allowed lateness | 30 giây | Dùng cho historical aggregate nếu cần |
| Late event handling | Side output | Ghi late event count và optional DLQ |

Pseudo logic:

```text
event_time = parse(capture_ts)
watermark = max_seen_event_time - 5 seconds
```

## 5. Validation stage

Validation tách event thành ba nhóm:

| Nhóm | Điều kiện | Output |
|---|---|---|
| Valid | Schema đúng, timestamp hợp lệ, bbox hợp lệ hoặc sửa được | Pipeline chính |
| Invalid | Thiếu required field, timestamp sai, image size sai | DLQ |
| Recoverable | Bbox lệch biên, confidence thiếu nhưng có default | Clean và ghi quality flag |

Các metric cần emit:

- `events_in_total`
- `events_valid_total`
- `events_invalid_total`
- `events_late_total`
- `events_duplicate_total`
- `detections_valid_total`
- `detections_filtered_low_conf_total`

## 6. Deduplication

Dedup theo `event_id` trong state TTL ngắn.

| Thuộc tính | Giá trị |
|---|---|
| Key | `event_id` |
| State type | Flink keyed state hoặc RocksDB state |
| TTL | 10 đến 30 phút |
| Duplicate action | Drop và tăng metric |

Lý do cần dedup:

- Vision producer retry publish.
- Pulsar redelivery.
- Flink restart từ checkpoint.
- Backfill/replay nhầm vào realtime path.

## 7. Realtime branch

### 7.1 Current person count

Mục tiêu: số người hiện tại theo camera.

Cách tính MVP:

- Với mỗi `DetectionFrameEvent`, đếm số detection `class_name = person` và `confidence >= threshold`.
- Ghi Redis key `stats:count:{camera_id}` bằng `SET` với TTL ngắn.

Redis:

```redis
SET stats:count:cam_01 15 EX 5
SET stats:fps:cam_01 24.8 EX 10
```

### 7.2 Active tracks

Mỗi detection có `track_id` được cập nhật vào Redis:

```redis
HSET track:active:cam_01:42 last_x 200 last_y 410 last_seen 2026-05-05T10:30:00Z
EXPIRE track:active:cam_01:42 30
```

Metric:

```redis
PFADD stats:tracks:cam_01:hour 42
PFCOUNT stats:tracks:cam_01:hour
```

### 7.3 Live heatmap

Heatmap dùng grid cố định, ví dụ `64 x 48`.

```text
grid_x = floor(centroid_x / frame_width  * 64)
grid_y = floor(centroid_y / frame_height * 48)
```

Redis sorted set:

```redis
ZINCRBY heatmap:live:cam_01 1 "32,18"
EXPIRE heatmap:live:cam_01 60
```

Decay:

- Mỗi 3 giây nhân score với `0.95`.
- Xóa cell có score dưới `0.1`.
- Có thể thực hiện bằng API worker hoặc Flink timer.

### 7.4 Density alert

Alert không nên chỉ dựa vào số detection trong một frame vì dễ nhiễu. Đề xuất dùng sliding window.

| Alert | Logic |
|---|---|
| `crowd_threshold` | max person count trong 5 giây >= threshold |
| `density_spike` | count tăng nhanh so với baseline window |
| `hotspot_density` | một heatmap cell hoặc vùng lân cận vượt threshold |
| `camera_offline` | không có frame mới quá N giây |

Ví dụ window:

```text
keyBy(camera_id)
window(SlidingEventTimeWindows.of(10 seconds, 2 seconds))
aggregate(max_count, avg_count, max_heatmap_cell)
```

Alert id:

```text
alert_id = hash(camera_id, alert_type, window_start, window_end)
```

## 8. Lakehouse branch

Lakehouse branch có hai cách triển khai:

### Option A: Streaming trực tiếp từ Pulsar vào Iceberg

```text
Pulsar -> Flink -> Bronze/Silver/Gold Iceberg
```

Ưu điểm:

- Gần realtime hơn.
- Pipeline đơn giản trong demo.

Nhược điểm:

- Gold aggregate phức tạp hơn nếu cần backfill nhiều.

### Option B: Bronze streaming, Silver/Gold batch hoặc incremental

```text
Pulsar -> Flink -> Bronze
Bronze -> Silver job
Silver -> Gold job
```

Ưu điểm:

- Tách rõ raw và curated.
- Dễ backfill.
- Phù hợp giải thích lakehouse trong đồ án.

Nhược điểm:

- Latency cao hơn.

Đề xuất cho đồ án: dùng Option B về mặt thiết kế, nhưng MVP có thể triển khai Silver/Gold bằng scheduled job nếu Flink Table job phức tạp.

## 9. Checkpointing

| Setting | Giá trị đề xuất |
|---|---:|
| Checkpoint interval | 30 giây |
| Checkpoint timeout | 2 phút |
| Min pause | 10 giây |
| State backend | RocksDB hoặc filesystem state backend cho demo |
| Checkpoint storage | local volume hoặc GCS path |
| Restart strategy | fixed delay hoặc exponential delay |

Lakehouse commit vào Iceberg thường gắn với checkpoint. Vì vậy historical path có latency cao hơn realtime path.

## 10. Exactly-once và at-least-once

| Sink | Guarantee thực tế | Ghi chú |
|---|---|---|
| Iceberg | Exactly-once với Flink checkpoint nếu cấu hình đúng | Phù hợp lakehouse path |
| PostgreSQL | Có thể idempotent với unique key | Không mặc định exactly-once |
| Redis | At-least-once | Dùng SET/TTL/idempotent key để giảm sai lệch |
| Prometheus metrics | At-least-once hoặc best-effort | Dùng để quan sát, không làm source of truth |

Kết luận cho báo cáo: hệ thống đạt exactly-once cho analytical storage, còn realtime serving chấp nhận at-least-once có kiểm soát.

## 11. Failure handling

| Lỗi | Cách xử lý |
|---|---|
| Event lỗi schema | Gửi DLQ, tăng metric |
| Pulsar redelivery | Dedup bằng `event_id` |
| Flink restart | Restore từ checkpoint |
| Redis down | Log lỗi, retry, pipeline chính vẫn ghi lakehouse |
| PostgreSQL down | Retry có backoff, alert có thể giữ tạm trong Redis |
| Iceberg commit fail | Flink retry theo checkpoint |
| Camera offline | System metric và camera offline alert |

## 12. Test cases cho streaming

- Event hợp lệ được ghi vào Bronze.
- Event thiếu `camera_id` đi vào DLQ.
- Duplicate `event_id` chỉ được xử lý một lần.
- Event trễ hơn watermark được đánh dấu late.
- Current count trong Redis cập nhật theo frame mới.
- Heatmap cell tăng khi centroid rơi vào cell.
- Alert được tạo khi count vượt threshold.
- Flink restart vẫn tiếp tục từ checkpoint.

## 13. Output cần chứng minh trong demo

1. Pulsar topic có detection events.
2. Flink UI hiển thị job đang chạy.
3. Redis có `stats:count`, `heatmap:live`, `track:active`.
4. PostgreSQL có alert hoặc track lifecycle records.
5. Iceberg có Bronze/Silver/Gold data.
6. Trino query được historical metrics.
7. Streamlit/Grafana hiển thị kết quả.

