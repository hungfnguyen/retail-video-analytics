# Airflow Orchestration

Thư mục này chứa skeleton orchestration cho kiến trúc:

- `Bronze / Silver / Gold`
- `Flink` là transform engine chính
- `Airflow` chỉ là orchestrator cho batch refresh và maintenance

## Mô hình DAG

Mỗi **domain nghiệp vụ = 1 DAG** (1 workflow). Tất cả producer chạy `schedule="@daily"`,
`catchup=True` → mỗi run xử lý **đúng 1 ngày** (`data_interval` = `{{ ds }}`), backfill N
ngày = N run. Task trong DAG = từng bảng theo thứ tự phụ thuộc, gọi:

```
refresh_runner.py backfill --start {{ ds }} --end {{ ds }} --only <table> --skip-ddl
```

### Producer DAGs (mỗi cái 1 domain)

| DAG | Tasks (thứ tự) |
|---|---|
| `gold_serving_traffic` | apply_ddl → traffic_hourly → traffic_daily |
| `gold_serving_heatmap` | apply_ddl → heatmap_tile_5min → heatmap_tile_hour |
| `gold_serving_alert` | apply_ddl → alert_hourly → alert_daily |
| `gold_serving_queue` | apply_ddl → [queue_hourly ∥ queue_daily] |
| `gold_serving_zone` | apply_ddl → [zone_hourly ∥ zone_daily] |
| `gold_serving_dwell` | apply_ddl → dwell_daily |

### Consumer DAG (cross-domain)

- `gold_serving_executive` — `@daily`, dùng `ExternalTaskSensor` chờ
  `traffic_daily / dwell_daily / queue_daily / alert_daily` cùng `{{ ds }}` xong, rồi
  build `executive_daily`. Sensor dùng `mode="reschedule"`.

### Ops DAGs

- `iceberg_maintenance` (`0 */6 * * *`) — `maintenance.py`: OPTIMIZE + DQ nhẹ.
- `gold_quality_checks` (`0 * * * *`) — `quality_checks.py`: freshness/non-negative/presence.

> Task `apply_ddl` (chạy `apply_ddl.py`) dựng lại `rva_gold_serving` sau mỗi restart.
> Vì DDL idempotent, refresh dùng `--skip-ddl` để tránh chạy 2 lần trong cùng DAG run.

**Backfill** không có DAG riêng — dùng catchup: `airflow dags backfill <dag_id> -s <start> -e <end>`.

> ⚠️ Container Airflow hiện chạy `airflow standalone` (SequentialExecutor — 1 task/lúc).
> `ExternalTaskSensor` cross-DAG + catchup nhiều DAG sẽ bị serialize. Để chạy song song
> đúng nghĩa nên chuyển sang **LocalExecutor + Postgres** (tốn RAM hơn).

## Thiết kế

Airflow không chứa logic transform.

Nó chỉ gọi các script orchestration có sẵn bằng `BashOperator`.
Điều này giữ cho:

- SQL/Trino logic vẫn nằm trong `services/gold_serving/`
- Airflow chỉ chịu trách nhiệm schedule, retry, dependency
- sau này nếu thay `Trino SQL` bằng `Flink batch`, DAG chỉ cần đổi command target

## Environment variables

Các DAG dùng các biến sau:

- `RVA_PROJECT_ROOT`
  - mặc định: `/opt/retail-video-analytics`
- `RVA_PYTHON_BIN`
  - mặc định: `/usr/bin/python3`
- `RVA_SERVING_RUNNER_DIR`
  - mặc định: `${RVA_PROJECT_ROOT}/services/gold_serving`
- `FLINK_BATCH_JAR_PATH`
  - mặc định: `/opt/rva-artifacts/gold-jobs.jar`

Lưu ý:

- Không đặt batch JAR dưới `/opt/airflow/...` vì path này đang bị volume `airflow_data`
  mount đè trong `docker-compose`, sẽ làm artifact biến mất lúc runtime.

## Ghi chú

`services/gold_serving/` hiện là implementation vật lý của **Gold serving**.
