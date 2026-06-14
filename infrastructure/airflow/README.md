# Airflow Orchestration

Thư mục này chứa orchestration cho kiến trúc:

- `Bronze / Silver / Gold`
- `Flink` là transform engine chính
- `Airflow` chỉ là orchestrator cho batch refresh và maintenance

## Mô hình DAG

Mỗi **domain nghiệp vụ = 1 DAG** (1 workflow). Tất cả producer chạy `schedule="@daily"`,
`catchup=True` → mỗi run xử lý **đúng 1 ngày** (`data_interval` = `{{ ds }}`), backfill N
ngày = N run. Task trong DAG = từng batch step của Gold serving, gọi:

```
python3 /opt/retail-video-analytics/services/flink-jobs/python/submit_batch_job.py \
  --domain <step> --start {{ ds }} --end {{ ds }} --run-mode daily
```

### Producer DAGs (mỗi cái 1 domain)

| DAG | Tasks (thứ tự) |
|---|---|
| `gold_serving_traffic` | `traffic_hourly -> traffic_daily` |
| `gold_serving_heatmap` | `heatmap_5min -> heatmap_hour` |
| `gold_serving_alert` | `alert_hourly -> alert_daily` |
| `gold_serving_queue` | `queue_hourly -> queue_daily` |
| `gold_serving_zone` | `zone_hourly -> zone_daily` |
| `gold_serving_dwell` | `dwell_daily` |

### Speed layer DAG

- `gold_serving_today_refresh` — chạy mỗi 30 phút, refresh chuỗi step cho **ngày hiện tại**
  để Analytics/Heatmap không phải đợi DAG `@daily` chốt xong ngày hôm trước.

### Consumer DAG (cross-domain)

- `gold_serving_executive` — `@daily`, dùng `ExternalTaskSensor` chờ
  `traffic_daily / dwell_daily / queue_daily / alert_daily` cùng `{{ ds }}` xong, rồi
  build `executive_daily`. Sensor dùng `mode="reschedule"`.

### Ops DAGs

- `iceberg_maintenance` (`0 */6 * * *`) — `maintenance.py`: OPTIMIZE + DQ nhẹ.
- `gold_quality_checks` (`0 * * * *`) — `quality_checks.py`: freshness/non-negative/presence.

**Backfill** vẫn dùng catchup theo DAG hoặc trigger thủ công theo ngày.

## Thiết kế

Airflow không chứa logic transform.

Nó chỉ submit Flink batch job hoặc gọi script ops bằng `BashOperator`.
Điều này giữ cho:

- Flink batch logic nằm trong `services/flink-jobs/java/`
- quality checks / maintenance Trino vẫn nằm trong `services/gold_serving/`
- Airflow chỉ chịu trách nhiệm schedule, retry, dependency
- Airflow task success/fail bám vào `jobId` của Flink REST thay vì local attached execution

`submit_batch_job.py` chịu trách nhiệm:

- lấy batch lock dùng chung để chỉ có 1 Gold serving batch submit chạy tại một thời điểm
- upload JAR
- submit `/jars/{id}/run`
- poll `/jobs/{jobId}`
- cancel Flink job nếu task fail/timeout sau khi đã submit
- ghi `gold_serving_refresh_audit`
- xóa uploaded JAR tạm thời

`GoldServingBatchJob` hiện tự hạ `table.exec.resource.default-parallelism` theo domain để phù hợp
với Flink local cluster nhỏ. Có thể override bằng env:

- `RVA_GOLD_SERVING_BATCH_PARALLELISM`
- hoặc `RVA_GOLD_SERVING_PARALLELISM_<DOMAIN>`
  - ví dụ: `RVA_GOLD_SERVING_PARALLELISM_QUEUE_HOURLY=2`

## Environment variables

Các DAG dùng các biến sau:

- `RVA_PROJECT_ROOT`
  - mặc định: `/opt/retail-video-analytics`
- `RVA_PYTHON_BIN`
  - mặc định: `/usr/bin/python3`
- `RVA_FLINK_BATCH_SUBMITTER`
  - mặc định: `${RVA_PROJECT_ROOT}/services/flink-jobs/python/submit_batch_job.py`
- `FLINK_REST_URL`
  - mặc định trong compose: `http://flink-jobmanager:8081`
- `FLINK_BATCH_JAR_PATH`
  - mặc định: `/opt/rva-artifacts/gold-jobs.jar`
- `RVA_FLINK_BATCH_LOCK`
  - mặc định: `/tmp/rva-flink-batch.lock`
- `TRINO_URL`
- `TRINO_USER`
- `TRINO_CATALOG`
- `TRINO_SCHEMA`
  - cần cho audit/DQ/maintenance path

Lưu ý:

- Không đặt batch JAR dưới `/opt/airflow/...` vì path này đang bị volume `airflow_data`
  mount đè trong `docker-compose`, sẽ làm artifact biến mất lúc runtime.
- `docker-compose.yml` hiện dùng `LocalExecutor + Postgres`, không còn `SequentialExecutor`.
- Batch serving hiện được serialize bằng lock mức submitter để tránh nhiều DAG cùng tranh slot
  trên cùng một Flink session cluster local.

## Ghi chú

`services/gold_serving/` hiện là thư mục phụ trợ cho **Gold serving**:

- DDL bootstrap
- maintenance
- quality checks
- legacy Trino refresh fallback
