# Final Technical Debt Assessment

> Trạng thái đánh giá: 2026-06-14. Tài liệu này là kết luận cuối cùng sau khi đọc
> `system.md`, `partition-strateric.md`, các file review của Claude (`00`-`03`), và đối chiếu với
> code hiện tại của repo.

## 1. Kết luận tổng

Kiến trúc tổng thể của project **không sai hướng**. Hệ thống hiện đã đi theo pattern hợp lý:

```text
Vision -> Pulsar -> Flink streaming -> Iceberg Bronze/Silver/Gold facts
                         |
                         +-> Redis realtime serving

Airflow -> Flink batch -> Iceberg Gold serving
Trino -> FastAPI -> React Analytics / Heatmap
```

Điểm quan trọng: technical debt hiện tại không nằm ở việc dùng `Bronze / Silver / Gold` hay dùng
Airflow để orchestrate Flink batch. Debt thật nằm ở:

- correctness của timestamp và lineage
- state management của streaming jobs
- idempotency/audit của Gold serving batch
- partition strategy chưa tối ưu cho multi-store BI
- docs/runtime bị lệch sau nhiều lần refactor
- production hardening chưa đủ nếu deploy thật

Vì vậy hướng sửa đúng không phải "đập đi làm lại kiến trúc", mà là **siết correctness trước,
siết vận hành batch/streaming sau, rồi mới tối ưu partition/production**.

## 2. Kiến trúc nào đang đúng

### 2.1 Medallion vẫn là mô hình chuẩn

Mô hình chuẩn của project là:

```text
Bronze = raw metadata events
Silver = detection-level facts đã parse/clean
Gold facts = business facts / streaming aggregates
Gold serving = bảng Gold query-ready cho dashboard
```

`Gold serving` không phải tier thứ tư ngoài Medallion. Nó là nhóm bảng thuộc Gold, có nhiệm vụ
phục vụ API/BI nhanh hơn các bảng fact.

### 2.2 Airflow là orchestrator, không phải transform engine

Quyết định hiện tại là đúng:

```text
Airflow submit Flink batch job
Airflow poll Flink REST jobId
Airflow quyết định task success/fail
```

Airflow không nên chứa logic transform lớn. Nó chỉ nên làm:

- schedule theo ngày / intraday
- dependency giữa domain
- retry
- gọi Flink batch
- gọi maintenance / quality checks
- lưu trạng thái orchestration

### 2.3 Flink là transform engine chính

Flink đang làm đúng vai trò:

- streaming ingestion và transforms cho Bronze/Silver/Gold facts
- batch transforms cho Gold serving

Trino nên giữ vai trò query/maintenance/DQ nhẹ, không còn là engine refresh Gold serving chính.

### 2.4 Một JAR nhiều entrypoint không phải anti-pattern

Một artifact chứa nhiều job class là bình thường. Anti-pattern chỉ xuất hiện khi:

- copy cùng JAR thành nhiều tên gây hiểu nhầm
- version artifact không rõ
- Airflow/runtime không kiểm soát được JAR đang chạy phiên bản nào

Nên hướng đúng là:

```text
rva-flink-jobs-<version>.jar
submit với --entry-class
Airflow log rõ jar_id + job_id + domain
```

## 3. Technical debt thật cần sửa

### D1. `parseCaptureMs` fallback về current time

Mức độ: **P0 correctness**

Hiện `ParseDetections.parseCaptureMs` fallback về `System.currentTimeMillis()` khi timestamp
null hoặc parse lỗi. Đây là bug dữ liệu thật.

Tác hại:

- record lỗi timestamp bị đưa vào ngày hiện tại
- partition `days(capture_ts)` sai
- daily KPI sai
- dwell/heatmap/traffic bucket sai
- lỗi dữ liệu bị che đi thay vì bị loại/DLQ

Kết luận: phải sửa trước khi tối ưu gì khác.

Hướng sửa:

- timestamp null/invalid -> sentinel `-1L` hoặc không collect detection
- tăng metric invalid
- sau này thêm DLQ cho Silver parse errors

### D2. Streaming state chưa có TTL

Mức độ: **P0 reliability/correctness vận hành**

Các operator stateful đáng chú ý:

- Silver dedup `ROW_NUMBER() OVER (...)`
- Gold track summary group by global track
- Queue session aggregation
- Gold dashboard aggregation

Không có TTL nghĩa là state có thể phình theo thời gian chạy. Trong demo ít ngày có thể ổn,
nhưng đây là debt thật nếu chạy lâu.

Hướng sửa tối thiểu:

- set `table.exec.state.ttl` cho các streaming jobs
- chọn TTL theo semantics từng job

Gợi ý:

| Job | TTL gợi ý | Lý do |
|---|---:|---|
| `SilverJob` dedup | 10m-30m | duplicate event/detection chỉ nên đến gần nhau |
| `GoldTrackSummaryJob` | 1d-3d | track visit có thể kéo dài nhưng không vô hạn |
| `QueueAnalyticsJob` | 12h-1d | queue session không nên sống vĩnh viễn |
| `GoldDashboardAggregateJob` | 2d-7d | daily/hourly aggregate có thể cập nhật trễ |

TTL không thay thế session lifecycle đúng, nhưng đủ cho scope project/demo.

### D3. `executive_daily` dependency lệch với SQL source

Mức độ: **P0 lineage/correctness**

Airflow `gold_serving_executive` chờ:

- `traffic_daily`
- `dwell_daily`
- `queue_daily`
- `alert_daily`

Nhưng `runExecutiveDaily` vẫn đọc một phần từ raw Gold facts:

- `rva.gold_track_summary_v2`
- `rva.gold_queue_sessions`
- `rva.gold_alerts`

Điều này làm dependency Airflow không phản ánh đúng data lineage.

Hướng sửa khuyến nghị:

```text
executive_daily đọc từ:
  gold_serving_traffic_daily/hourly
  gold_serving_dwell_daily
  gold_serving_queue_daily
  gold_serving_alert_daily
```

Khi đó sensor mới thật sự có nghĩa, và executive là rollup Gold serving đúng nghĩa.

### D4. Gold serving audit có bảng nhưng chưa được ghi đúng

Mức độ: **P0/P1 observability**

`gold_serving_refresh_audit` đã có DDL và `writeAudit`, nhưng batch path hiện tại chưa ghi audit
đầy đủ.

Lưu ý quan trọng: vì Flink batch đang được submit bằng REST detached, không nên quay lại kiểu
Java job tự `await()` để ghi audit sau insert. Pattern đúng hơn:

```text
submit_batch_job.py:
  upload jar
  run jar -> job_id
  poll /jobs/{job_id}
  if FINISHED -> write audit success
  if FAILED/CANCELED/TIMEOUT -> write audit failure
```

Audit có thể ghi bằng Trino HTTP client hoặc một task Airflow riêng. Đây là observability rất
đáng làm vì nó cho biết ngày/domain/table nào đã refresh xong.

### D5. `INSERT OVERWRITE` cần chứng minh idempotency

Mức độ: **P0 correctness check**

Gold serving batch đang dùng `INSERT OVERWRITE`. Cần verify rõ:

- rerun cùng domain/date có giữ row count ổn định không
- retry task có nhân đôi không
- ngày không có output có clear partition cũ không
- partial failure có để lại bảng ở trạng thái nửa cũ nửa mới không

Nếu test cho thấy dynamic overwrite không clear partition rỗng, cần đổi sang strategy rõ hơn:

```text
DELETE WHERE metric_date BETWEEN start AND end
INSERT INTO ...
```

hoặc giữ `INSERT OVERWRITE` nhưng ghi rõ giới hạn trong docs.

### D6. Trino refresh path cũ còn tồn tại

Mức độ: **P1 consistency**

Hiện transform chính đã chuyển sang Flink batch, nhưng vẫn còn:

- `services/gold_serving/refresh_runner.py`
- `services/gold_serving/sql/refresh/*.sql`
- một số README vẫn mô tả refresh bằng Trino

Điều này dễ gây nhầm source of truth.

Quyết định cuối:

```text
Flink batch = transform engine cho Gold serving
Trino python = DQ/maintenance/query support, không refresh serving chính
```

Hướng sửa:

- mark `refresh_runner.py` và `sql/refresh` là deprecated
- hoặc xóa khi đã chắc không cần fallback
- cập nhật README/Airflow docs

### D7. Partition Gold serving thiếu `store_id`

Mức độ: **P1/P2 performance, tùy multi-store**

Hiện nhiều bảng serving partition dạng:

```text
metric_date,bucket(16,camera_id)
```

Với BI thật, filter đầu tiên thường là `store_id`, sau đó mới camera/zone/date. Vì vậy partition
nên tiến tới:

```text
aggregate nhỏ: metric_date,store_id
heatmap lớn:   metric_date,store_id,bucket(16,camera_id)
executive:     metric_date,store_id
```

Với demo 1 store, đây chưa phải P0. Khi chuẩn bị multi-store hoặc demo performance BI, nên làm.

### D8. Checkpoint/savepoint local

Mức độ: **P2 production hardening**

Flink config comment nói lưu S3, nhưng thực tế đang là:

```text
file:///opt/flink/state/checkpoints
file:///opt/flink/state/savepoints
```

Docker volume giúp sống qua restart container, nhưng không durable qua `down -v`, đổi máy,
multi-node hoặc node failure.

Đây là production debt đúng, nhưng không nên kéo vào scope P0 nếu mục tiêu hiện là sửa correctness.

### D9. Batch/streaming chung một Flink session cluster

Mức độ: **P2 production hardening**

Với local/demo, dùng chung cluster là hợp lý để tiết kiệm RAM. Production nên có:

- cluster riêng cho streaming
- cluster/session riêng cho batch
- hoặc Airflow pool/concurrency giới hạn batch

Hiện đã tăng slot để batch chạy được, nhưng đây là local tuning, không phải isolation thật.

### D10. Docs lệch runtime

Mức độ: **P1 maintainability**

Một số docs/comment vẫn nói:

- `SequentialExecutor`, trong khi `docker-compose.yml` dùng `LocalExecutor`
- refresh bằng `refresh_runner.py`, trong khi DAG submit Flink batch
- Airflow skeleton cũ

Đây là debt nhỏ nhưng gây hại vì người mới hoặc AI agent dễ làm sai hướng.

## 4. Những claim đã stale hoặc cần giảm nhẹ

### C1. "SequentialExecutor không chạy song song"

Stale. Repo hiện dùng:

```text
AIRFLOW__CORE__EXECUTOR=LocalExecutor
Postgres metadata DB
```

Chỉ còn docs/comment cũ cần dọn.

### C2. "Bronze partition là anti-pattern lớn nhất"

Nói quá. Bronze hiện không phải nguồn query dashboard. Silver đọc Bronze bằng incremental
streaming. Bronze partition chưa tối ưu cho replay/backfill, nhưng không phải debt cấp bách nhất.

### C3. "days(capture_ts) prune kém"

Hơi quá. Với Iceberg/Trino, transform partition có thể prune được. Vấn đề thật là timezone và
business date, không phải riêng `days(capture_ts)`.

### C4. "Đóng tất cả vào 1 Flink job là anti-pattern"

Không đúng nếu hiểu là một JAR hoặc một entry class có nhiều domain. Hiện Airflow submit từng
domain/step riêng (`traffic_hourly`, `heatmap_5min`, ...), nên blast radius đã nhỏ hơn.

Debt còn lại là:

- SQL string quá dài trong Java
- audit chưa hoàn chỉnh
- artifact versioning chưa rõ

## 5. Quy tắc ưu tiên sửa

Áp dụng thứ tự sau:

1. Sửa cái làm sai số liệu.
2. Sửa cái làm job chạy lâu sẽ chết hoặc phình state.
3. Sửa lineage/audit để biết dữ liệu nào đã refresh.
4. Sửa docs lệch runtime để tránh tiếp tục tạo debt.
5. Tối ưu partition khi bắt đầu multi-store / dữ liệu lớn.
6. Production hardening để luận văn/future work nếu chưa cần deploy thật.

## 6. Kết luận cuối cùng

Project hiện có nền kiến trúc tốt, nhưng đang ở trạng thái:

```text
production-like architecture
demo/local operational hardening
partial observability
some correctness debt
```

Không cần đổi kiến trúc lớn. Cần sửa có kỷ luật theo phase:

- P0: correctness + state + lineage + audit/idempotency
- P1: consistency + docs + cleanup old Trino refresh path
- P2: partition + production hardening

File triển khai theo phase: `05_IMPLEMENTATION_PHASES.md`.
