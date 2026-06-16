# Remediation Plan — phân tầng & cách sửa

Mỗi item: **Vấn đề → Bằng chứng → Cách sửa cụ thể → Effort → Scope (đồ án / future).**
Effort: S (≤1h), M (vài giờ), L (≥1 ngày).

Phân tầng:
- **P0** — Correctness. Sai số liệu / sai tính đúng. Nên sửa trong đồ án.
- **P1** — Consistency & debt vừa. Làm nếu còn thời gian; tăng chất lượng luận văn.
- **P2 / Future Work** — Production hardening. **Ghi vào chương "Hạn chế & Hướng phát
  triển"** của luận văn; không bắt buộc code.

---

## P0 — Correctness (ưu tiên cao nhất)

### P0.1 — `parseCaptureMs` không được fallback về current time
- **Vấn đề:** Timestamp parse lỗi bị gán `System.currentTimeMillis()` ⇒ record rơi vào
  **ngày hiện tại** ⇒ sai `days(capture_ts)`, sai daily KPI/dwell/heatmap.
- **Bằng chứng:** `ParseDetections.java:215-226`; filter `capture_ts_ms IS NOT NULL`
  (`SilverJob.java:195`) bị vô hiệu vì fallback luôn trả giá trị.
- **Cách sửa:**
  1. Trong `ParseDetections.parseCaptureMs`, khi parse fail → trả **sentinel** (vd `-1L`)
     thay vì `System.currentTimeMillis()`. Trường `null` (`ts == null`) cũng trả `-1L`.
  2. Trong `eval(...)`: nếu `captureMs < 0` → **không `collect()`** detection đó và
     `invalidRecordCounter.inc()` (kết hợp P1.10 nếu thêm DLQ).
  3. Giữ nguyên filter `t.capture_ts_ms IS NOT NULL` ở Silver như lớp chặn thứ 2 (đổi thành
     `> 0` nếu cần).
- **Effort:** S. **Scope:** Đồ án (bug correctness rõ ràng).

### P0.2 — Khớp lại dependency `executive_daily` với nguồn SQL thật
- **Vấn đề:** DAG chờ `dwell/queue/alert_daily` nhưng SQL đọc raw facts
  (`rva.gold_track_summary_v2`, `rva.gold_queue_sessions`, `rva.gold_alerts`).
- **Bằng chứng:** `gold_serving_executive.py:11-16` vs `GoldServingBatchJob.java:433,443,453`.
- **Cách sửa — chọn 1 hướng (khuyến nghị Hướng A):**
  - **Hướng A (đúng kiến trúc serving):** sửa `runExecutiveDaily` đọc từ các bảng **serving
    finalized**: `gold_serving_dwell_daily`, `gold_serving_queue_daily`,
    `gold_serving_alert_daily`, `gold_serving_traffic_daily`. Khi đó 4 sensor mới *có nghĩa*.
    Lợi: executive = rollup thuần trên serving, idempotent theo ngày, không phụ thuộc state
    streaming của raw facts.
  - **Hướng B (giữ đọc raw facts):** **bỏ** 3 sensor `wait_dwell/wait_queue/wait_alert`,
    chỉ giữ phụ thuộc dữ liệu thực tế (traffic + raw facts sẵn có). Đơn giản hơn nhưng
    executive không nhất quán "đọc từ serving".
- **Effort:** M (Hướng A) / S (Hướng B). **Scope:** Đồ án.

### P0.3 — Đặt `table.exec.state.ttl` cho streaming aggregation
- **Vấn đề:** State vô hạn ở dedup Silver + các `GROUP BY` Gold ⇒ checkpoint phình, recovery
  chậm, nguy cơ OOM kể cả khi demo chạy dài.
- **Bằng chứng:** `SilverJob.java:185-189` (dedup ROW_NUMBER), `GoldTrackSummaryJob.java:95`,
  `QueueAnalyticsJob.java:98`, `GoldDashboardAggregateJob.java:167,188`. Không có TTL.
- **Cách sửa (giải pháp tối thiểu, hợp đồ án):** thêm vào từng job streaming sau khi tạo
  `TableEnvironment`:
  ```java
  tEnv.getConfig().set("table.exec.state.ttl", "6 h");   // hoặc giá trị phù hợp dữ liệu demo
  ```
  - Silver dedup: TTL phải ≥ độ trễ tối đa giữa các bản trùng của cùng `event_id` (thực tế
    vài giây) ⇒ TTL nhỏ vài phút là đủ và an toàn.
  - Track/Queue/Dashboard: TTL nên ≥ độ dài 1 visit/ngày bạn muốn còn cập nhật (vd 6h–3d).
- **Lưu ý:** TTL là **workaround**. Giải pháp đúng (session/track lifecycle có enter/exit,
  hoặc daily final do batch) ⇒ ghi Future Work (P2). Với đồ án, TTL là đủ để chứng minh hiểu
  vấn đề.
- **Effort:** S. **Scope:** Đồ án (TTL) + Future (session lifecycle).

### P0.4 — Hoàn thiện audit cho Gold serving batch
- **Vấn đề:** `gold_serving_refresh_audit` được tạo nhưng batch job không ghi row nào;
  `executeStep` bỏ qua `tableName/sourceTable`.
- **Bằng chứng:** `GoldServingBatchJob.java:487-489`; `GoldServingSupport.writeAudit` (`:368-402`)
  không được gọi; `executeAndAwait` không await (`:347-349`).
- **Cách sửa:**
  1. Sửa `executeAndAwait` thật sự await:
     ```java
     TableResult r = tEnv.executeSql(sql);
     r.await();
     ```
  2. Trong `executeStep`: bọc try/catch quanh `executeAndAwait`, ghi `started_at/finished_at`,
     `status` (`ok`/`error`), `error_message`, và (nếu rẻ) `output_row_count` qua
     `GoldServingSupport.scalarLong("SELECT COUNT(*) FROM ... WHERE metric_date BETWEEN ...")`,
     rồi gọi `writeAudit(...)` với `runId/runMode/tableName/sourceTable`.
- **Effort:** M. **Scope:** Đồ án (điểm cộng observability, tận dụng code có sẵn).

### P0.5 — Kiểm chứng semantics `INSERT OVERWRITE` (idempotency)
- **Vấn đề:** Batch dùng `INSERT OVERWRITE ... WHERE metric_date BETWEEN start AND end`. Cần
  chắc chắn chỉ overwrite **đúng partition** trong window, và retry không nhân đôi / không
  xoá nhầm ngày khác.
- **Bằng chứng:** `GoldServingBatchJob.java` (mọi `runXxx` dùng `INSERT OVERWRITE`).
- **Cách sửa / kiểm chứng:**
  1. Flink Iceberg batch `INSERT OVERWRITE` trên bảng partitioned mặc định là **dynamic
     partition overwrite** (chỉ ghi đè partition xuất hiện trong output). ⇒ Rủi ro: nếu một
     `(metric_date, camera_bucket)` ra **0 row**, partition cũ **không** bị clear.
  2. **Test thực nghiệm** (ghi kết quả vào doc/luận văn): chạy 1 domain 2 lần cho cùng `ds`,
     `SELECT COUNT(*)` trước/sau phải bằng nhau (idempotent); chạy với data rỗng ngày D, xác
     nhận partition ngày D có bị clear không.
  3. Nếu cần "xoá sạch window rồi ghi": thay bằng `DELETE FROM ... WHERE metric_date BETWEEN
     ...` rồi `INSERT INTO ...` (như chính `refresh_runner.py` cũ làm) — semantics rõ ràng hơn.
- **Effort:** M (chủ yếu là test + ghi nhận). **Scope:** Đồ án (chứng minh tính đúng batch).

---

## P1 — Consistency & debt vừa

### P1.6 — Chọn 1 source of truth Gold serving, bỏ dần Trino path
- **Vấn đề:** Hybrid Flink-batch (refresh) + Trino-python (DQ/maintenance + refresh_runner
  chết). Logic metric dễ lệch 2 nơi.
- **Bằng chứng:** `01_*` mục D1.
- **Cách sửa (khuyến nghị):**
  - Chốt **Flink batch = engine transform Gold serving chính** (khớp ALIGNMENT doc).
  - **Trino = chỉ query/DQ/maintenance**, không transform refresh.
  - Đánh dấu `services/gold_serving/refresh_runner.py` + `sql/refresh/*.sql` là
    **DEPRECATED** (thêm header rõ + ghi trong README), hoặc xoá nếu chắc không dùng làm
    fallback. `quality_checks.py` + `maintenance.py` giữ lại (đang chạy thật).
- **Effort:** S (deprecate) / M (xoá + cập nhật README). **Scope:** Đồ án.

### P1.7 — Dọn comment/doc còn nhắc SequentialExecutor
- **Vấn đề:** Repo đã dùng `LocalExecutor` nhưng comment còn nói SequentialExecutor.
- **Bằng chứng:** `docker-compose.yml:290` vs `gold_serving_executive.py:36`.
- **Cách sửa:** Sửa comment dòng 36 (sensor `reschedule` vẫn hợp lý dưới LocalExecutor để
  nhường slot, nhưng lý do không còn là "required under SequentialExecutor"). Rà các doc khác
  nếu có nhắc.
- **Effort:** S. **Scope:** Đồ án.

### P1.8 — Tách catalog/DDL bootstrap khỏi runtime job
- **Vấn đề:** Block tạo catalog copy-paste 7 lần; `ensureServingTables` chạy mỗi domain.
- **Bằng chứng:** `01_*` mục A10.
- **Cách sửa:**
  1. Extract `org.rva.common.IcebergCatalogSupport` (1 method `createCatalogSql(...)` +
     `createBatch/StreamEnv`), các job gọi chung.
  2. (Tuỳ chọn) Tách bước tạo schema/table thành 1 job/bootstrap riêng (hoặc dùng
     `apply_ddl.py` đã có ở Trino path) chạy 1 lần, runtime job chỉ read/write.
- **Effort:** M. **Scope:** Đồ án (refactor sạch, ít rủi ro) — phần (2) có thể Future.

### P1.9 — Move SQL khỏi Java string → resource `.sql`
- **Bằng chứng:** `01_*` mục A11.
- **Cách sửa:** Đưa SQL vào `services/flink-jobs/java/src/main/resources/sql/...`, load bằng
  classloader, inject `{start}/{end}` (giống pattern `refresh_runner.py` đã làm cho Trino).
- **Effort:** M/L. **Scope:** Đồ án nếu còn thời gian; nếu không → Future.

### P1.10 — DLQ cho Silver parse errors
- **Vấn đề:** Parse lỗi chỉ log+counter, không lưu lại.
- **Bằng chứng:** `ParseDetections.java:109-114`.
- **Cách sửa:** Thêm side-output / ghi vào topic `persistent://retail/metadata/dlq-events`
  (đã có cho realtime) hoặc bảng `rva.silver_parse_errors` gồm
  `event_id, reason, raw_payload, failed_at, job_name`. Kết hợp P0.1 (invalid capture_ts).
- **Effort:** M. **Scope:** Đồ án nếu còn thời gian; ưu tiên thấp hơn P0.

---

## P2 / Future Work — Production hardening (ghi vào luận văn)

> Các mục này **đúng** về mặt production nhưng **out-of-scope đồ án**. Trình bày trong chương
> "Hạn chế hiện tại & Hướng phát triển" để thể hiện đã hiểu giới hạn, không cần code lại.

| # | Hạng mục | Hiện trạng | Hướng production |
|---|---|---|---|
| F1 | Durable state | checkpoint `file://` (`flink-conf.yaml:45-46`) | S3/MinIO checkpoint+savepoint |
| F2 | Resource isolation | 1 session cluster, 16 slot (`flink-conf.yaml:18`) | Tách cluster streaming/batch, hoặc Airflow `pool` cho batch |
| F3 | Job lifecycle | Airflow timeout không cancel (`submit_batch_job.py:114-117`) | cancel `/jobs/{id}` on fail + job_id XCom + Flink UI link |
| F4 | Packaging | 1 jar copy 5 tên (`Dockerfile:31-35`) | 1 jar versioned `rva-flink-jobs-x.y.z.jar` + `--entry-class` |
| F5 | Streaming aggregation | TTL workaround (P0.3) | session/track lifecycle (enter/exit/close), daily final do batch |
| F6 | Parallelism | `parallelism.default: 1` (`flink-conf.yaml:26`) | sizing theo Pulsar partitions / camera count |
| F7 | Redis sink | swallow exception (`RealtimeMetricsJob.java:448`) | metric `redis_write_failed_total` + Jedis pipeline |
| F8 | Orchestration | per-DAG + ExternalTaskSensor | master-DAG TaskGroup hoặc Dataset/event-based |
| F9 | Deploy | docker-compose | Flink Kubernetes Operator (`FlinkDeployment`/`FlinkSessionJob`) |
| F10 | Partition redesign | xem `03_PARTITION_REDESIGN.md` | business_date + store_id (làm theo version v2/v3) |

---

## Thứ tự thực thi đề xuất (cho đồ án)

```
Sprint 1 (correctness, rẻ):   P0.1 → P0.2(B hoặc A) → P0.3 → P1.7
Sprint 2 (chất lượng):        P0.4 → P0.5 → P1.6
Sprint 3 (nếu còn thời gian): P1.8 → P1.10 → P1.9
Luận văn (viết, không code):  toàn bộ P2/Future + kết quả test P0.5
```

Mỗi P0 sau khi sửa cần **verify lại** bằng query Trino đếm row / so sánh KPI trước–sau (theo
`docs/README.md` & các lệnh trong `README.md` gốc). Build/restart/trigger do người dùng chạy.
