# Gold Serving Physical Model

Tài liệu này chốt trạng thái implementation hiện tại của `Gold serving` sau khi quay lại kiến trúc medallion chính:

```text
Bronze / Silver / Gold
```

`Gold serving` là một nhóm bảng thuộc Gold, không phải tier thứ 4.

## 1. Kết luận

Implementation hiện tại:

- schema vật lý: `lakehouse.rva_gold_serving`
- code refresh: `services/gold_serving/`
- engine hiện tại: `Trino SQL`
- orchestration về sau: `Airflow`

Điều này hợp lệ vì:

- `Airflow` chỉ schedule/retry/dependency/backfill
- `Trino` là engine thực thi các aggregate batch bounded hiện tại
- `Flink` vẫn giữ vai trò chính cho streaming transforms và stateful Gold facts

Không cần chuyển toàn bộ `gold_serving_*` sang Flink batch ngay.

## 2. Code debt đã dọn

### Zone

`gold_zone_minute_metrics` không còn là flow chính thức.

Trạng thái hiện tại:

- không còn insert target trong `QueueAnalyticsJob`
- `gold_serving_zone_hourly`
- `gold_serving_zone_daily`

được build trực tiếp từ:

```text
lakehouse.rva.silver_detections_v2
```

Lý do:

- source đã có `primary_zone_id`, `primary_zone_type`, anchor và queue facts
- bảng zone minute cũ không có consumer API
- serving zone hiện chỉ cần aggregate bounded theo hour/day

### Alert

Hai bảng alert có semantics khác nhau:

```text
lakehouse.rva.gold_alerts
```

Ý nghĩa:

- 1 row = 1 clip-backed alert incident
- source = `media-events` topic, event_type `clip_created`
- job ghi = `GoldAlertsJob`
- dùng cho alert history và `gold_serving_alert_*`

```text
lakehouse.rva.gold_alert_events
```

Ý nghĩa:

- 1 row = 1 frame-level density threshold signal
- source = `silver_detections_v2`
- job ghi = `GoldDashboardAggregateJob`
- không thay thế `gold_alerts`

Rule:

```text
Alert history / alert serving -> gold_alerts
Density signal analysis       -> gold_alert_events
```

Không union hai bảng này nếu chưa normalize semantics.

## 3. Bảng nào giữ bằng Trino SQL

Các bảng dưới đây hiện nên giữ bằng Trino SQL vì chúng là aggregate bounded, ít stateful complexity, dễ audit và dễ gọi từ Airflow.

| Gold serving table | Source hiện tại | Engine hiện tại | Lý do giữ Trino SQL |
|---|---|---|---|
| `gold_serving_traffic_hourly` | `silver_detections_v2` | Trino SQL | per-frame/per-hour aggregate đơn giản |
| `gold_serving_traffic_daily` | `gold_serving_traffic_hourly` | Trino SQL | daily rollup đơn giản |
| `gold_serving_queue_hourly` | `gold_queue_sessions_v2` | Trino SQL | queue session đã là Gold fact, serving chỉ aggregate |
| `gold_serving_queue_daily` | `gold_queue_sessions_v2` | Trino SQL | daily aggregate + percentile bounded |
| `gold_serving_dwell_daily` | `gold_camera_daily_dwell` | Trino SQL | đọc aggregate theo camera/ngày để tránh scan trực tiếp bảng upsert track-level |
| `gold_serving_executive_daily` | nhiều Gold facts / serving tables | Trino SQL | store/day rollup cho dashboard |
| `gold_serving_alert_hourly` | `gold_alerts` | Trino SQL | count incident theo hour |
| `gold_serving_alert_daily` | `gold_serving_alert_hourly` | Trino SQL | daily rollup đơn giản |

## 4. Bảng có thể chuyển sang Flink batch sau

Không chuyển ngay. Chỉ chuyển khi đo được Trino SQL không còn đủ hoặc logic cần semantics giống Flink.

| Candidate | Source | Khi nào chuyển sang Flink batch |
|---|---|---|
| `gold_serving_heatmap_tile_5min` | `silver_detections_v2` | khi historical heatmap scan lớn, refresh lâu, hoặc cần backfill nhiều ngày ổn định hơn |
| `gold_serving_heatmap_tile_hour` | `gold_serving_heatmap_tile_5min` | khi rollup lớn cần chạy chung trong batch pipeline |
| `gold_serving_zone_hourly` | `silver_detections_v2` | khi zone occupancy chuyển từ aggregate detection sang session/event-time semantics |
| `gold_serving_zone_daily` | `silver_detections_v2` hoặc hourly serving | khi daily finalize cần consistency với Flink batch |
| `gold_serving_traffic_hourly` | `silver_detections_v2` | khi muốn tất cả traffic aggregate lấy từ Flink SQL/batch thay vì Trino |

Nguyên tắc chuyển:

```text
Trino SQL -> Flink batch chỉ khi có lý do đo được:
- latency refresh vượt budget
- dữ liệu lớn khiến Trino single-node không ổn
- cần event-time/stateful semantics
- cần replay/backfill lớn với cùng logic Flink
```

## 5. Airflow sẽ điều phối như thế nào

Airflow không chứa logic transform.

Trong trạng thái hiện tại, Airflow gọi:

```text
services/flink-jobs/python/submit_batch_job.py --domain <step> --start <ds> --end <ds>
services/gold_serving/maintenance.py
```

Ý nghĩa:

```text
Airflow -> Flink REST detached batch -> GoldServingBatchJob -> rva_gold_serving.*
```

`services/gold_serving/refresh_runner.py` chỉ còn là legacy/manual fallback path bằng Trino SQL,
không còn là source of truth cho refresh theo lịch.

## 6. Quy tắc quyết định engine

Dùng `Flink streaming` cho:

- Bronze ingest
- Silver detection facts
- track lifecycle
- queue session
- realtime Gold facts
- Redis live state

Dùng `Trino SQL` cho:

- serving aggregate đơn giản
- daily/hourly rollup
- dashboard-ready tables
- maintenance
- lightweight quality checks

Dùng `Flink batch` cho:

- bounded transform nhưng logic phức tạp
- backfill lớn
- serving table cần event-time semantics
- logic cần reuse Flink SQL/state assumptions

## 7. Trạng thái chốt

Trạng thái đúng của project sau bước này:

```text
Bronze -> Silver -> Gold facts:
  Flink streaming

Gold facts / Silver -> Gold serving:
  Trino SQL hiện tại
  Flink batch chỉ khi cần

Airflow:
  orchestration
  không phải transform engine
```

Đây là điểm cân bằng thực dụng: giữ kiến trúc medallion sạch, không over-engineer toàn bộ serving layer sang Flink batch khi logic hiện tại vẫn là bounded SQL aggregate.
