# Job Mapping And Data Modeling

Tài liệu này trả lời 4 câu hỏi cho project Retail Video Analytics:

1. data modeling toàn project nên nhìn như thế nào
2. job nào nên là `Flink streaming`
3. job nào nên là `Flink batch`
4. job nào chỉ cần `Trino SQL`
5. `Airflow` sẽ điều phối các job đó ra sao

## 1. Kết luận ngắn

Kiến trúc chuẩn cho project là:

```text
Bronze / Silver / Gold
```

Trong `Gold` chia làm 2 nhóm:

- `Gold facts`
- `Gold serving`

Vai trò công nghệ:

- `Flink streaming`: materialize `Bronze -> Silver -> Gold facts`
- `Flink batch`: chỉ dùng khi serving/finalize cần logic stateful hoặc muốn giữ nhất quán với SQL/Flink hiện có
- `Trino SQL`: dùng cho aggregate batch bounded, refresh serving table, maintenance, quality checks
- `Airflow`: orchestrate các job batch và maintenance, không thay Flink

## 2. Data model toàn project

### 2.1 Source layer

Nguồn dữ liệu:

- `Vision metadata events` từ camera/video
- `media-events` cho sampled frame / clip

Chúng được phát vào Pulsar:

- `persistent://retail/metadata/events`
- `persistent://retail/metadata/media-events`
- `persistent://retail/metadata/dlq-events`

### 2.2 Bronze

Mục tiêu:

- lưu raw payload
- giữ audit trail
- replay/debug

Bảng chính:

| Tier | Table | Grain | Vai trò |
|---|---|---|---|
| Bronze | `lakehouse.rva.bronze_raw` | 1 row = 1 raw event/frame payload | Raw immutable event log |

### 2.3 Silver

Mục tiêu:

- parse JSON
- flatten detections
- clean / normalize / dedup
- enrich detection facts

Bảng chính:

| Tier | Table | Grain | Vai trò |
|---|---|---|---|
| Silver | `lakehouse.rva.silver_detections_v2` | 1 row = 1 detection | canonical enriched facts với `global_track_id`, queue, zone, anchor |

### 2.4 Gold facts

Mục tiêu:

- aggregate business-level facts
- serving-ready enough cho nhiều use case
- vẫn còn generic, chưa nhất thiết là bảng cuối cho dashboard

Bảng hiện tại trong codebase:

| Tier | Table | Grain | Vai trò |
|---|---|---|---|
| Gold facts | `lakehouse.rva.gold_track_summary_v2` | 1 row = 1 global track | lifecycle / dwell / visit summary |
| Gold facts | `lakehouse.rva.gold_queue_sessions_v2` | 1 row = 1 queue session within a pipeline run | queue wait analytics |
| Gold facts | `lakehouse.rva.gold_camera_hourly_metrics` | 1 row = 1 camera + 1 hour | traffic aggregate theo giờ |
| Gold facts | `lakehouse.rva.gold_camera_daily_metrics` | 1 row = 1 camera + 1 day | traffic aggregate theo ngày |
| Gold facts | `lakehouse.rva.gold_camera_daily_dwell` | 1 row = 1 camera + 1 day | dwell aggregate theo ngày |
| Gold facts | `lakehouse.rva.gold_alert_events` | 1 row = 1 alert aggregate event | density/event aggregate |
| Gold facts | `lakehouse.rva.gold_alerts` | 1 row = 1 alert incident | clip-backed / serving-path alert history |

Ghi chú:

- `gold_zone_minute_metrics` từng được thiết kế nhưng đã bị loại khỏi flow hiện tại
- nó không còn là bảng target chính thức trong trạng thái code hiện nay

### 2.5 Gold serving

Mục tiêu:

- query-ready tables cho analyst/dashboard
- bounded batch aggregates
- grain khớp đúng màn hình

Các bảng nên tồn tại về mặt thiết kế:

| Nhóm | Table đề xuất | Grain |
|---|---|---|
| Traffic serving | `gold_serving_traffic_hourly` | `store + camera + hour` |
| Traffic serving | `gold_serving_traffic_daily` | `store + camera + day` |
| Queue serving | `gold_serving_queue_hourly` | `store + camera + queue zone + hour` |
| Queue serving | `gold_serving_queue_daily` | `store + camera + queue zone + day` |
| Zone serving | `gold_serving_zone_hourly` | `store + camera + zone + hour` |
| Zone serving | `gold_serving_zone_daily` | `store + camera + zone + day` |
| Heatmap serving | `gold_serving_heatmap_tile_5min` | `store + camera + 5-minute bucket + tile` |
| Heatmap serving | `gold_serving_heatmap_tile_hour` | `store + camera + hour + tile` |
| Alert serving | `gold_serving_alert_hourly` | `store + camera + alert_type + severity + hour` |
| Alert serving | `gold_serving_alert_daily` | `store + camera + alert_type + severity + day` |
| Executive serving | `gold_serving_executive_daily` | `store + day` |

Ghi chú thực tế:

- implementation hiện tại nằm ở `services/gold_serving/` và schema `lakehouse.rva_gold_serving`
- đây là physical implementation của `Gold serving`, không phải tier thứ 4

## 3. Job mapping rất rõ cho project

### 3.1 Flink streaming jobs

Đây là nhóm **nên giữ bằng Flink streaming**.

| Job | Input | Output | Vì sao là Flink streaming |
|---|---|---|---|
| `BronzeIngestJob` | Pulsar `events` | `bronze_raw` | ingest liên tục, raw stream |
| `SilverJob` | `bronze_raw` | `silver_detections_v2` | parse/flatten/enrich liên tục |
| `GoldTrackSummaryJob` | `silver_detections_v2` | `gold_track_summary_v2` | track lifecycle là stateful/incremental |
| `QueueAnalyticsJob` | `silver_detections_v2` | `gold_queue_sessions_v2` | queue session là stateful/incremental |
| `GoldDashboardAggregateJob` | `silver_detections_v2`, `gold_track_summary_v2` | `gold_camera_hourly_metrics`, `gold_camera_daily_metrics`, `gold_camera_daily_dwell`, `gold_alert_events` | near-real-time facts cho traffic/dwell/alerts |
| `RealtimeMetricsJob` | Pulsar `events` | Redis | low-latency live serving |

Rule:

```text
Mọi transform cần consume stream liên tục, giữ state, hoặc phụ thuộc event-time
=> ưu tiên Flink streaming
```

### 3.2 Flink batch jobs

Đây là nhóm **có thể dùng Flink batch**, nhưng không bắt buộc.

Dùng khi:

- logic serving/finalize vẫn khá phức tạp
- muốn giữ cùng engine/SQL semantics với Flink
- cần bounded run theo ngày/giờ nhưng logic vẫn stateful hơn SQL aggregate đơn thuần

| Job | Input | Output | Khi nào nên dùng Flink batch |
|---|---|---|---|
| `GoldServingHeatmapBatchJob` | `silver_detections_v2` | `gold_serving_heatmap_tile_*` | nếu muốn bounded heatmap build nhưng vẫn bám Flink SQL |
| `GoldServingZoneBatchJob` | `silver_detections_v2` hoặc `gold facts` | `gold_serving_zone_*` | nếu zone serving logic phức tạp hơn Trino SQL |
| `GoldServingFinalizeJob` | `gold facts` | daily serving/finalized Gold | nếu muốn gom nhiều serving outputs trong 1 batch pipeline |
| `BackfillTrackOrQueueJob` | `silver_detections_v2` | backfill Gold facts | khi cần replay/backfill theo range lớn |

Rule:

```text
Flink batch hợp khi job là bounded,
nhưng logic vẫn đủ phức tạp để nên giữ trong cùng ecosystem Flink
```

### 3.3 Trino SQL jobs

Đây là nhóm **chỉ cần Trino SQL**.

Dùng khi:

- query bounded
- aggregate đơn giản
- không cần stateful streaming semantics
- chủ yếu là serving/maintenance/DQ

| Job | Input | Output | Vì sao chỉ cần Trino SQL |
|---|---|---|---|
| `gold_serving_traffic_hourly_refresh` | `gold_camera_hourly_metrics` | `gold_serving_traffic_hourly` | simple rollup / filter / select |
| `gold_serving_traffic_daily_refresh` | `gold_camera_daily_metrics` | `gold_serving_traffic_daily` | bounded daily serving |
| `gold_serving_queue_hourly_refresh` | `gold_queue_sessions_v2` | `gold_serving_queue_hourly` | aggregate batch đơn giản |
| `gold_serving_queue_daily_refresh` | `gold_queue_sessions_v2` | `gold_serving_queue_daily` | aggregate batch đơn giản |
| `gold_serving_executive_daily_refresh` | nhiều `gold facts` | `gold_serving_executive_daily` | serving rollup cho dashboard |
| `heatmap_serving_refresh` | `silver_detections_v2` | `gold_serving_heatmap_tile_*` | nếu logic chỉ là bounded aggregate theo tile |
| `iceberg_optimize` | Iceberg tables | same tables | maintenance |
| `iceberg_analyze` | Iceberg tables | same tables | stats |
| `dq_rowcount_checks` | Bronze/Silver/Gold tables | audit table/log | data quality nhẹ |

Rule:

```text
Nếu job chỉ là aggregate bounded, serving refresh, maintenance, DQ
=> Trino SQL là đủ
```

## 4. Airflow sẽ điều phối ra sao

### 4.1 Airflow không transform

Airflow chỉ:

- schedule
- dependency
- retry
- backfill
- audit
- alert

Compute thực sự vẫn do:

- Flink streaming
- Flink batch
- Trino SQL

### 4.2 DAG mapping đề xuất

| DAG | Engine được Airflow gọi | Mục tiêu |
|---|---|---|
| `silver_to_gold_facts_backfill` | Flink batch | backfill `Silver -> Gold facts` |
| `gold_serving_intraday_refresh` | Trino SQL hoặc Flink batch | refresh `Gold -> Gold serving` theo giờ |
| `gold_serving_daily_finalize` | Trino SQL hoặc Flink batch | finalize serving theo ngày |
| `iceberg_maintenance` | Trino SQL | optimize / analyze / snapshot cleanup |
| `gold_quality_checks` | Trino SQL | row count / freshness / null ratio / stale source |

### 4.3 Luồng điều phối chuẩn

#### Luồng 1: streaming liên tục

```text
Pulsar
  -> Flink streaming
  -> Bronze / Silver / Gold facts
```

Airflow **không** chạm vào luồng này trong runtime bình thường.

#### Luồng 2: serving theo batch

```text
Airflow
  -> run Trino SQL refresh hoặc Flink batch job
  -> build Gold serving
  -> warm cache
```

#### Luồng 3: backfill/finalize

```text
Airflow
  -> trigger bounded Flink batch job hoặc SQL refresh theo date range
  -> write audit
  -> verify output
```

#### Luồng 4: maintenance

```text
Airflow
  -> optimize hot partitions
  -> analyze
  -> expire snapshots
  -> remove orphan files
```

## 5. Recommendation rất cụ thể cho project hiện tại

### 5.1 Những gì nên giữ nguyên

- `BronzeIngestJob`
- `SilverJob`
- `GoldTrackSummaryJob`
- `QueueAnalyticsJob`
- `GoldDashboardAggregateJob`
- `RealtimeMetricsJob`

Tức là:

```text
toàn bộ streaming core hiện tại tiếp tục do Flink chịu trách nhiệm
```

### 5.2 Những gì không cần vội biến thành Flink batch

Ở phase sắp tới, đừng mặc định viết thêm Flink job mới cho mọi serving table.

Ưu tiên:

1. dùng Gold facts đã có
2. nếu cần serving table batch đơn giản, bắt đầu bằng Trino SQL
3. chỉ nâng lên Flink batch khi serving logic trở nên phức tạp thật

### 5.3 Trình tự thực dụng nhất

1. ổn định `Gold facts`
2. xác định serving table nào thật sự cần
3. refresh serving table bằng `Trino SQL` trước nếu logic nhẹ
4. đưa `Airflow` vào để điều phối
5. chỉ viết thêm `Flink batch` nếu bounded SQL không còn đủ

## 6. Modeling quyết định code sau này như thế nào

### Nếu logic là streaming-first

Ví dụ:

- active track lifecycle
- queue session
- rolling zone occupancy

=> model nó thành `Gold facts` bằng Flink streaming

### Nếu logic là analyst-serving bounded

Ví dụ:

- daily executive summary
- hourly serving table
- finalized heatmap table

=> model nó thành `Gold serving`

### Nếu logic là maintenance / DQ

=> không phải data model tier, chỉ là operational workflow do Airflow điều phối

## 7. Kết luận cuối

Cho project này, mapping đúng là:

```text
Bronze / Silver / Gold

Flink streaming:
  Bronze -> Silver -> Gold facts

Flink batch:
  chỉ dùng cho bounded transforms phức tạp hoặc backfill lớn

Trino SQL:
  Gold serving refresh, maintenance, DQ

Airflow:
  orchestration cho batch jobs và maintenance
```

Đây là mô hình production hợp lý hơn việc mở một tier `mart` độc lập hoặc cố ép mọi job batch đều phải là Flink.
