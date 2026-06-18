# Implementation Phases

> Tài liệu này biến kết luận trong `04_FINAL_TECH_DEBT_ASSESSMENT.md` thành kế hoạch thực hiện.
> Mục tiêu là sửa hệ thống có kiểm soát, tránh over-engineering và tránh loop dài không cần thiết.

## Nguyên tắc thực hiện

1. Mỗi phase phải có output rõ ràng.
2. Không trộn correctness fix với refactor lớn.
3. Không đổi partition/source table khi chưa có test hoặc kế hoạch backfill.
4. Runtime verification nên do người vận hành start stack, nhưng code phải có test/build tối thiểu.
5. Nếu một bước phát hiện scope lớn hơn dự kiến, dừng lại ghi nhận thay vì kéo dài.

## Phase 0 — Baseline & Safety Check

Mục tiêu: ghi lại trạng thái hiện tại trước khi sửa để có điểm so sánh.

### Việc cần làm

- Kiểm tra working tree và commit hiện tại.
- Ghi lại row count các bảng chính:
  - `lakehouse.rva.bronze_raw`
  - `lakehouse.rva.silver_detections_v2`
  - `lakehouse.rva.gold_track_summary_v2`
  - `lakehouse.rva.gold_queue_sessions`
  - `lakehouse.rva.gold_alerts`
  - các bảng `lakehouse.rva_gold_serving.gold_serving_*`
- Ghi lại Flink jobs đang chạy.
- Ghi lại Airflow DAGs đang paused/unpaused.

### Output

- Một note ngắn trong docs hoặc final response:
  - row counts
  - job states
  - DAG states
  - commit hash

### Verify

- Không sửa code ở phase này.
- Không cần restart stack nếu người dùng không yêu cầu.

## Phase 1 — Correctness Fixes

Mục tiêu: sửa các lỗi có thể làm số liệu sai.

### 1.1 Sửa timestamp parsing trong Silver

File chính:

- `services/flink-jobs/java/src/main/java/org/rva/silver/udf/ParseDetections.java`
- `services/flink-jobs/java/src/main/java/org/rva/silver/SilverJob.java` nếu cần filter thêm

Việc cần làm:

- `parseCaptureMs(null)` trả sentinel invalid, không trả `System.currentTimeMillis()`.
- timestamp parse lỗi trả sentinel invalid.
- trong `eval`, nếu `captureMs < 0`, tăng counter và skip payload/detection.
- đảm bảo invalid timestamp không vào `silver_detections_v2`.

Output:

- code fix
- unit test hoặc test UDF nếu repo đã có harness phù hợp
- build Java pass

Verify:

- `mvn -q -DskipTests package`
- nếu có test UDF thì chạy riêng test đó

### 1.2 Chốt lineage `executive_daily`

File chính:

- `services/flink-jobs/java/src/main/java/org/rva/gold/GoldServingBatchJob.java`
- `infrastructure/airflow/dags/gold_serving_executive.py`

Quyết định khuyến nghị:

```text
executive_daily đọc từ Gold serving daily tables:
  gold_serving_traffic_daily
  gold_serving_traffic_hourly
  gold_serving_dwell_daily
  gold_serving_queue_daily
  gold_serving_alert_daily
```

Việc cần làm:

- sửa `runExecutiveDaily` không đọc trực tiếp `gold_track_summary_v2`, `gold_queue_sessions`,
  `gold_alerts` nữa.
- giữ `ExternalTaskSensor` vì khi đó dependency phản ánh đúng source thật.
- comment sensor đổi từ `SequentialExecutor` sang lý do đúng: nhường worker slot và tránh busy wait.

Output:

- executive lineage rõ ràng
- Airflow dependency có ý nghĩa thật

Verify:

- Java build pass
- nếu stack đang chạy: trigger `gold_serving_executive` sau khi upstream daily xong và kiểm tra
  `gold_serving_executive_daily`.

## Phase 2 — Streaming State Control

Mục tiêu: ngăn state streaming phình vô hạn trong demo chạy dài.

### 2.1 Thêm state TTL cho streaming jobs

Files:

- `SilverJob.java`
- `GoldTrackSummaryJob.java`
- `QueueAnalyticsJob.java`
- `GoldDashboardAggregateJob.java`

Việc cần làm:

- sau khi tạo `TableEnvironment`, set:

```java
tEnv.getConfig().set("table.exec.state.ttl", "<duration>");
```

TTL gợi ý:

| Job | TTL |
|---|---:|
| `SilverJob` | `30 min` |
| `GoldTrackSummaryJob` | `3 d` |
| `QueueAnalyticsJob` | `1 d` |
| `GoldDashboardAggregateJob` | `7 d` |

Lưu ý:

- TTL là solution thực dụng cho demo/local.
- Session lifecycle chuẩn hơn nên để future work.

Output:

- state TTL documented trong code hoặc docs
- Java build pass

Verify:

- `mvn -q -DskipTests package`
- sau restart, Flink jobs vẫn RUNNING

## Phase 3 — Gold Serving Audit & Idempotency

Mục tiêu: biết chính xác table/domain/date nào đã refresh thành công, và retry có an toàn không.

### 3.1 Ghi audit từ submitter/Airflow

Files:

- `services/flink-jobs/python/submit_batch_job.py`
- có thể thêm helper Trino client nhỏ hoặc reuse `services/gold_serving/trino_client.py`
- `services/flink-jobs/java/src/main/java/org/rva/gold/GoldServingSupport.java` có thể giữ DDL

Không khuyến nghị:

- không quay lại Java `TableResult.await()` để ghi audit vì batch đang chạy REST detached.

Pattern khuyến nghị:

```text
submit_batch_job.py:
  upload jar
  run job -> job_id
  poll job state
  FINISHED -> write audit ok
  FAILED/CANCELED/TIMEOUT -> write audit error
  delete uploaded jar
```

Audit fields tối thiểu:

- `job_name`
- `run_id`
- `run_mode`
- `gold_serving_table`
- `partition_date`
- `source_table`
- `output_row_count`
- `status`
- `error_message`
- `started_at`
- `finished_at`
- `refreshed_at`

Output:

- `gold_serving_refresh_audit` có rows sau mỗi task serving
- Airflow/Flink job_id có trong log

Verify:

- trigger 1 domain nhỏ, ví dụ `traffic_daily`
- query:

```sql
SELECT * FROM lakehouse.rva_gold_serving.gold_serving_refresh_audit
ORDER BY refreshed_at DESC
LIMIT 10;
```

### 3.2 Chốt semantics idempotency cho Gold serving refresh

Việc cần làm:

- đổi batch SQL sang `INSERT INTO`
- để submitter chủ động:
  - `DELETE` đúng `metric_date` window trên target
  - submit Flink batch
  - poll `jobId`
  - ghi audit
- chạy cùng domain 2 lần và so sánh row count trước/sau

Nếu verify fail:

- kiểm tra logic pre-delete window hoặc target partitioning
- không quay lại `INSERT OVERWRITE` nếu chưa có lý do rất rõ

Output:

- note kết quả trong docs hoặc commit message
- xác nhận rerun không nhân đôi
- xác nhận audit vẫn phản ánh đúng `ok/error`

## Phase 4 — Cleanup Old Paths & Docs

Mục tiêu: code/docs không còn nói hai hướng khác nhau.

### 4.1 Dọn Trino refresh path cũ

Files:

- `services/gold_serving/refresh_runner.py`
- `services/gold_serving/sql/refresh/*.sql`
- `services/gold_serving/README.md`
- `infrastructure/airflow/README.md`

Việc cần làm:

- nếu vẫn muốn giữ fallback: thêm banner `DEPRECATED: Flink batch is the serving refresh source of truth`.
- nếu không cần fallback: xóa path refresh cũ, giữ lại:
  - `maintenance.py`
  - `quality_checks.py`
  - `trino_client.py` nếu DQ/maintenance dùng

Output:

- người đọc không nhầm Trino SQL là transform path chính.

### 4.2 Sửa docs Airflow

Files:

- `infrastructure/airflow/README.md`
- `infrastructure/airflow/dags/gold_serving_executive.py`
- `AGENTS.md` nếu còn nói skeleton cũ

Việc cần làm:

- mô tả Airflow hiện dùng `LocalExecutor + Postgres`.
- mô tả DAG gọi `submit_batch_job.py`, không phải `refresh_runner.py`.
- bỏ comment `SequentialExecutor`.
- mô tả JAR path `/opt/rva-artifacts/gold-jobs.jar`.

Output:

- docs khớp runtime.

## Phase 5 — Partition Strategy

Mục tiêu: tối ưu dần cho BI theo store/date mà không phá source of truth.

### 5.1 Gold serving partition redesign

Chỉ làm sau khi Phase 1-4 ổn.

Target:

| Bảng | Partition mục tiêu |
|---|---|
| traffic/queue/zone/dwell/alert hourly/daily | `metric_date,store_id` |
| heatmap 5min/hour | `metric_date,store_id,bucket(16,camera_id)` |
| executive_daily | `metric_date,store_id` |

An toàn nhất:

- drop/recreate `rva_gold_serving`
- backfill lại Gold serving bằng Airflow/Flink batch

Không động vào:

- `bronze_raw`
- `silver_detections_v2`
- Gold facts chính

trừ khi đã có migration plan riêng.

### 5.2 Business date

Future/P1 tùy nhu cầu UI:

- thêm `business_date` theo timezone store
- API query dùng `business_date/metric_date` thay vì cast UTC timestamp

Với demo 1 timezone, có thể document assumption trước.

## Phase 6 — Production Hardening

Mục tiêu: ghi vào luận văn hoặc làm sau khi hệ thống demo ổn.

Items:

- checkpoint/savepoint lên S3/MinIO
- tách Flink cluster streaming và batch
- Airflow cancel Flink job khi timeout/fail
- versioned JAR artifact
- move SQL Java strings ra resource `.sql`
- extract `IcebergCatalogSupport`
- DLQ cho Silver parse errors
- Redis write metrics/pipeline
- Airflow pools/concurrency policy

Đây không phải blocker để dashboard demo chạy đúng.

## Checklist triển khai nhanh

Thứ tự khuyến nghị:

```text
Phase 1.1 parseCaptureMs
Phase 1.2 executive lineage
Phase 2.1 state TTL
Phase 3.1 audit
Phase 3.2 overwrite idempotency
Phase 4 docs/old path cleanup
Phase 5 partition redesign
Phase 6 future work
```

## Done definition

Một phase chỉ được coi là xong khi có đủ:

- code change hoặc quyết định explicit "defer"
- build/test tối thiểu
- tài liệu hoặc final response ghi rõ output
- nếu là runtime phase: có query/job evidence sau khi người dùng start stack
