# Gold Serving Runner

Thư mục này chứa implementation hiện tại của **Gold serving** bằng `Trino`.

Lưu ý kiến trúc:

- `lakehouse.rva_gold_serving.*` là tên vật lý đang tồn tại trong repo.
- Về mặt mô hình dữ liệu, các bảng này phải được hiểu là **Gold serving tables**.
- `services/gold_serving/` là implementation vật lý hiện tại; orchestration chuẩn về sau sẽ do `Airflow` gọi các script này.

## Thành phần

- `trino_client.py`
  Client Trino tối thiểu dùng HTTP `/v1/statement`.
- `apply_ddl.py`
  Bootstrap idempotent: tạo lại schema + 14 bảng `rva_gold_serving` (`CREATE ... IF NOT EXISTS`).
  Tự khôi phục schema sau khi stack/Iceberg-REST-catalog restart (schema `rva` được Flink tạo lại, còn `rva_gold_serving` thì không).
- `refresh_runner.py`
  Refresh các bảng `lakehouse.rva_gold_serving.*` theo window.
  **Tự gọi `apply_ddl.ensure_schema()` trước khi refresh** (trừ khi truyền `--skip-ddl`) → cron/manual không bao giờ gặp `SCHEMA_NOT_FOUND` sau restart.
- `maintenance.py`
  Chạy `OPTIMIZE` cho source/serving tables và ghi nhẹ `gold_serving_data_quality_results`.
- `sql/ddl/gold_serving.sql`
  DDL cho schema `lakehouse.rva_gold_serving`.
- `sql/refresh/*.sql`
  Refresh SQL cho từng bảng Gold serving.

## Cách dùng

Apply DDL (bootstrap schema — idempotent, an toàn chạy lại sau mỗi restart):

```bash
cd services/gold_serving
python3 apply_ddl.py
```

Lưu ý: `refresh_runner.py` đã tự chạy bước này, nên thường không cần gọi tay — chỉ dùng khi muốn dựng schema mà chưa refresh.

Refresh intraday:

```bash
cd services/gold_serving
python3 refresh_runner.py intraday
```

Refresh daily finalize:

```bash
cd services/gold_serving
python3 refresh_runner.py daily
```

Backfill:

```bash
cd services/gold_serving
python3 refresh_runner.py backfill --start 2026-06-01 --end 2026-06-12
```

Maintenance:

```bash
cd services/gold_serving
python3 maintenance.py
```

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

Airflow gọi các script trong thư mục này bằng `BashOperator`. Như vậy logic refresh/maintenance vẫn nằm trong codebase, còn Airflow chỉ chịu trách nhiệm schedule, dependency, retry và observability.

## Yêu cầu env

- `TRINO_URL`
- `TRINO_USER`
- `TRINO_CATALOG`
- `TRINO_SCHEMA`

Mặc định hiện tại khớp local stack:

- `TRINO_URL=http://localhost:8083`
- `TRINO_CATALOG=lakehouse`
- `TRINO_SCHEMA=rva_gold_serving`
