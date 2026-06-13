# Airflow Dags And Operations

Tài liệu này mô tả Airflow nên điều phối gì trong project.

## 1. Vai trò của Airflow

Airflow chỉ điều phối workflow hữu hạn:

- submit job
- chờ dependency
- retry
- backfill
- maintenance
- audit

Airflow không làm:

- consume stream liên tục
- transform detection event trực tiếp
- thay Flink realtime

## 2. Airflow có thể điều phối job gì

### Silver -> Gold batch jobs

Dùng khi:

- cần build lại aggregate theo window
- cần finalize partition theo giờ/ngày
- cần backfill từ Silver

Engine thực thi có thể là:

- Flink batch job
- Flink SQL job
- Spark job
- Trino SQL

### Gold -> Gold serving jobs

Dùng khi:

- đã có Gold facts
- cần serving table nhỏ hơn, ổn định hơn cho analyst

Ví dụ:

- `gold_queue_sessions -> gold_serving_queue_daily`
- `silver_detections_v2 -> gold_serving_zone_hourly`
- `gold_camera_hourly_metrics -> gold_serving_traffic_daily`
- `gold_alerts -> gold_serving_alert_hourly`

### Iceberg maintenance jobs

Ví dụ:

- `OPTIMIZE`
- `optimize_manifests`
- `expire_snapshots`
- `remove_orphan_files`
- `ANALYZE`

## 3. DAGs hợp lý cho project này

### DAG 1: `gold_serving_intraday_refresh`

Mục tiêu:

- refresh các Gold serving tables cần cập nhật trong ngày

Task kiểu mẫu:

1. check source freshness
2. refresh heatmap serving
3. refresh traffic hourly serving
4. refresh queue hourly serving
5. refresh zone hourly serving
6. write refresh audit

### DAG 2: `gold_serving_daily_finalize`

Mục tiêu:

- finalize serving partitions của ngày hôm qua

Task kiểu mẫu:

1. finalize traffic daily serving
2. finalize queue daily serving
3. finalize zone daily serving
4. finalize dwell/executive serving
5. run reconciliation checks

### DAG 3: `iceberg_maintenance`

Mục tiêu:

- giữ Iceberg tables khỏe

Task kiểu mẫu:

1. inspect files/snapshots
2. optimize hot partitions
3. optimize manifests
4. expire snapshots
5. remove orphan files
6. analyze tables

## 4. Airflow không ép phải dùng SQL file

Airflow có thể điều phối:

- một command submit Flink job
- một script gọi Trino SQL
- một Spark submit

Nghĩa là:

```text
Airflow không quyết định logic transform viết bằng gì.
Airflow chỉ quyết định job nào chạy khi nào và theo thứ tự nào.
```

## 5. Khi nào nên dùng Flink job thay vì Trino SQL

Ưu tiên `Flink` nếu:

- transform cần incremental / stateful
- cần event-time semantics
- cần streaming-first
- cần consistency với pipeline realtime/lakehouse hiện tại

Ưu tiên `Trino SQL` hoặc job SQL đơn giản nếu:

- chỉ là batch aggregate bounded
- logic nhẹ
- cần triển khai nhanh
- không có stateful complexity

## 6. Khuyến nghị cho project hiện tại

Hướng thực dụng:

1. `Bronze -> Silver -> Gold facts` tiếp tục do Flink xử lý
2. `Gold facts -> Gold serving` có thể bắt đầu bằng SQL jobs hoặc Flink batch jobs
3. Airflow chỉ điều phối các job đó và maintenance

Nếu muốn narrative nhất quán hơn với kiến trúc hiện tại, có thể ưu tiên:

```text
Airflow -> submit Flink batch/SQL job -> build Gold serving
```

thay vì để Airflow trực tiếp tự tính toán trong Python.

## 7. Checklist cho mỗi DAG

Mỗi DAG nên có:

- source freshness check
- refresh/backfill window rõ ràng
- audit output
- failure alert
- idempotent behavior

## 8. Kết luận

Airflow trong project này nên được hiểu là:

```text
workflow orchestrator cho batch jobs và maintenance,
không phải engine transform thay Flink
```

Đó là cách đúng nhất để nối lakehouse streaming hiện tại với nhu cầu analyst theo batch.
