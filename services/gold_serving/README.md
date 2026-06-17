# Gold Serving Support

Thư mục này chứa các thành phần phụ trợ cho **Gold serving**.

Source of truth hiện tại cho refresh theo lịch:

```text
Airflow -> submit_batch_job.py -> Flink REST -> GoldServingBatchJob
```

Nói ngắn gọn:

- `lakehouse.rva_gold_serving.*` vẫn là tên vật lý hiện tại
- về mặt mô hình, đây là **Gold serving tables**
- `services/gold_serving/` không còn là refresh engine chính
- thư mục này giữ DDL bootstrap, maintenance, DQ và legacy fallback bằng Trino

## Thành phần

- `trino_client.py`
  Client Trino tối thiểu dùng HTTP `/v1/statement`.
- `apply_ddl.py`
  Bootstrap idempotent: tạo lại schema + 14 bảng `rva_gold_serving` (`CREATE ... IF NOT EXISTS`).
  Tự khôi phục schema sau khi stack/Iceberg-REST-catalog restart (schema `rva` được Flink tạo lại, còn `rva_gold_serving` thì không).
- `refresh_runner.py`
  Legacy/manual fallback path bằng Trino SQL.
  Không còn là source of truth cho Airflow refresh theo lịch.
- `maintenance.py`
  Chạy `OPTIMIZE` cho source/serving tables và ghi nhẹ `gold_serving_data_quality_results`.
- `sql/ddl/gold_serving.sql`
  DDL cho schema `lakehouse.rva_gold_serving`.
- `sql/refresh/*.sql`
  Legacy refresh SQL cho từng bảng Gold serving.

## Cách dùng

Apply DDL (bootstrap schema — idempotent, an toàn chạy lại sau mỗi restart):

```bash
cd services/gold_serving
python3 apply_ddl.py
```

### Maintenance / DQ

```bash
cd services/gold_serving
python3 maintenance.py
```

```bash
cd services/gold_serving
python3 quality_checks.py
```

### Legacy fallback: `refresh_runner.py`

Chỉ dùng khi bạn chủ động muốn chạy đường Trino fallback để debug/so sánh:

```bash
cd services/gold_serving
python3 refresh_runner.py intraday --allow-legacy
python3 refresh_runner.py daily --allow-legacy
python3 refresh_runner.py backfill --start 2026-06-01 --end 2026-06-12 --allow-legacy
```

Lưu ý:

- path này đang được giữ lại để hỗ trợ phân tích/đối chiếu
- Airflow không dùng nó để refresh serving theo lịch nữa
- script sẽ từ chối chạy nếu không có `--allow-legacy` hoặc env
  `RVA_ALLOW_LEGACY_TRINO_REFRESH=1`

## Airflow orchestration

Repo hiện đã có DAGs tại:

- `infrastructure/airflow/dags/gold_serving_today_refresh.py`
- `infrastructure/airflow/dags/gold_serving_traffic.py`
- `infrastructure/airflow/dags/gold_serving_heatmap.py`
- `infrastructure/airflow/dags/gold_serving_queue.py`
- `infrastructure/airflow/dags/gold_serving_zone.py`
- `infrastructure/airflow/dags/gold_serving_dwell.py`
- `infrastructure/airflow/dags/gold_serving_alert.py`
- `infrastructure/airflow/dags/gold_serving_executive.py`
- `infrastructure/airflow/dags/gold_quality_checks.py`
- `infrastructure/airflow/dags/iceberg_maintenance.py`

Airflow hiện:

- submit Flink batch step qua `services/flink-jobs/python/submit_batch_job.py`
- chạy `maintenance.py` và `quality_checks.py` bằng `BashOperator`

Refresh serving logic chính nằm ở:

- `services/flink-jobs/java/src/main/java/org/rva/gold/GoldServingBatchJob.java`

## Yêu cầu env

- `TRINO_URL`
- `TRINO_USER`
- `TRINO_CATALOG`
- `TRINO_SCHEMA`

Mặc định local:

- `TRINO_URL=http://localhost:8083`
- `TRINO_CATALOG=lakehouse`
- `TRINO_SCHEMA=rva_gold_serving`

Nếu chạy trong container Airflow, các biến này trỏ qua network nội bộ Docker.
