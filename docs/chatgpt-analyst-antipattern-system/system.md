----
phân tích chuyên sâu xem, phần thiết kế các job flink, các dags airflow và cách airflow orchestrator các job flink đã chuẩn chưa??? cần tối ưu hay thay đổi kiến trúc chỗ nào không??? và chỗ đóng gòi tất cả thành 1 job flink duy nhất này có phải là anti pattern không?? và review lại toàn bộ code, kiến trúc, thiết kế xem chỗ nào là technical dept, anti pattern
-----


Kết luận thẳng: **kiến trúc của bạn đang đúng hướng, khá sát production pattern cho một hệ thống Retail Video Analytics Lakehouse**, nhưng hiện tại nó vẫn ở mức **production-like / thesis-grade**, chưa phải production-hardening thật sự.

Bạn đã làm đúng các ý lớn:

```text
Pulsar → Flink Streaming → Iceberg Bronze/Silver/Gold
Airflow → submit Flink Batch → Gold Serving
Redis → realtime dashboard state
Iceberg → lakehouse storage
```

Nhưng có một số điểm là **technical debt nghiêm trọng** nếu đem sang production thật: checkpoint local, streaming SQL aggregation giữ state vô hạn, batch + streaming chạy chung một Flink session cluster, REST upload jar từ Airflow còn đơn giản, `INSERT OVERWRITE` cần kiểm soát idempotency, và đang có trùng lặp giữa Trino/Flink trong Gold serving.

---

# 1. Đánh giá tổng quan

Mình chấm theo mức độ production-readiness:

| Thành phần               | Đánh giá | Nhận xét                                                                          |
| ------------------------ | -------: | --------------------------------------------------------------------------------- |
| Layer Bronze/Silver/Gold |     8/10 | Thiết kế đúng hướng Lakehouse                                                     |
| Tách streaming vs batch  |     8/10 | Đúng tư duy production                                                            |
| Airflow orchestration    |   6.5/10 | Đúng vai trò, nhưng submit/monitor còn đơn giản                                   |
| Flink job design         |   6.5/10 | Logic rõ, nhưng state/TTL/overwrite còn rủi ro                                    |
| Packaging/deployment     |     6/10 | Một artifact dùng nhiều entry class ổn, nhưng cách copy nhiều tên gây nợ kỹ thuật |
| Reliability              |     5/10 | Checkpoint local là điểm yếu lớn                                                  |
| Observability/audit      |   5.5/10 | Có ý tưởng audit/DQ nhưng chưa được dùng đầy đủ                                   |
| Production isolation     |     5/10 | Streaming và batch đang tranh slot trong cùng cluster                             |

Tổng thể:

```text
Đúng kiến trúc.
Chưa đủ production-hardening.
```

---

# 2. Phần thiết kế Flink jobs có chuẩn không?

## 2.1. BronzeIngestJob

Job này làm:

```text
Pulsar detection events
  ↓
Iceberg bronze_raw
```

Nó đọc raw payload từ Pulsar rồi ghi nguyên JSON vào Bronze, kèm `schema_version`, `event_id`, `pipeline_run_id`, `frame_index`, `camera_id`, `store_id`, `ingest_ts`. Đây là đúng pattern Bronze: giữ raw event để replay/debug/audit. Code cũng tạo Iceberg REST catalog và table trực tiếp trong job. 

Thiết kế này **đúng hướng**.

Nhưng có vài điểm cần cải thiện:

### Vấn đề 1: Bronze partition chưa tối ưu

Hiện Bronze partition theo:

```sql
PARTITIONED BY (store_id)
```

Với dữ liệu video analytics, query thường lọc theo:

```text
store_id
camera_id
date/time
```

Nếu Bronze chỉ partition theo `store_id`, lâu dài table sẽ khó scan theo ngày. Nên thêm trường như:

```text
ingest_date
capture_date
```

và partition kiểu:

```text
store_id, days(ingest_ts)
```

hoặc:

```text
store_id, bucket(camera_id), days(capture_ts)
```

Bronze có thể giữ raw, nhưng vẫn nên có partition phục vụ replay theo ngày.

### Vấn đề 2: Job tự tạo DDL

Trong demo/local thì ổn. Production thường tách:

```text
DDL/migration
```

ra khỏi:

```text
runtime streaming job
```

Lý do: job xử lý dữ liệu không nên là nơi quản lý schema lifecycle. Nếu mỗi lần job restart đều `CREATE TABLE IF NOT EXISTS`, thì vẫn chạy được, nhưng về vận hành sẽ khó kiểm soát schema evolution.

Khuyến nghị:

```text
Airflow / migration job / catalog bootstrap
  ↓
tạo database/table

Flink streaming job
  ↓
chỉ read/write
```

---

## 2.2. SilverJob

Job này làm:

```text
bronze_raw
  ↓
parse_detections UDTF
  ↓
silver_detections_v2
```

Đây là job quan trọng nhất trong pipeline. Nó parse JSON, explode mỗi detection thành một row, chuẩn hóa detection fields, track info, zone info, queue info. `ParseDetections` là UDTF parse Bronze JSON thành nhiều row detection, có counter `detection_parse_invalid_total` cho record lỗi. 

Điểm tốt:

```text
Bronze raw payload
  ↓
Silver structured table
```

Đây là đúng chuẩn Medallion Architecture.

Bạn cũng có dedup logic bằng:

```sql
ROW_NUMBER() OVER (
  PARTITION BY event_id, detection_id
  ORDER BY conf DESC, capture_ts DESC
) AS rn
...
WHERE rn = 1
```

và đọc Bronze Iceberg ở streaming incremental mode:

```sql
OPTIONS(
  'streaming'='true',
  'monitor-interval'='1s',
  'starting-strategy'='TABLE_SCAN_THEN_INCREMENTAL'
)
```



Nhưng có mấy điểm cần chú ý.

### Vấn đề 1: `TABLE_SCAN_THEN_INCREMENTAL` có thể rất nặng khi restart

Khi job start lần đầu, nó scan toàn bộ table rồi mới incremental. Với dataset nhỏ thì tốt.

Nhưng khi Bronze lớn lên, nếu checkpoint/savepoint mất hoặc job deploy lại sai cách, Silver có thể scan lại toàn bộ Bronze.

Production nên tách rõ:

```text
initial backfill
```

và:

```text
continuous incremental
```

Ví dụ:

```text
Job batch backfill:
Bronze historical → Silver historical

Job streaming:
Bronze incremental/latest → Silver realtime
```

Hoặc phải đảm bảo checkpoint/savepoint bền vững để job không phải scan lại lịch sử.

### Vấn đề 2: Parse lỗi đang bị skip, chưa có Silver DLQ

Trong `ParseDetections`, nếu parse lỗi thì job chỉ log warn và tăng counter. Điều này tốt ở mức basic, nhưng production nên có DLQ table/topic.

Hiện Realtime job có DLQ Pulsar, còn Silver job thì chưa có DLQ tương tự.

Nên thêm:

```text
silver_parse_errors
```

hoặc:

```text
persistent://retail/metadata/dlq-events
```

để lưu:

```text
event_id
reason
raw_payload
failed_at
job_name
```

### Vấn đề 3: `parseCaptureMs` fallback về current time là nguy hiểm

Trong `ParseDetections`, nếu timestamp parse fail thì fallback:

```java
return System.currentTimeMillis();
```

Đây là technical debt khá lớn.

Vì nếu capture timestamp lỗi, record sẽ bị đưa vào **ngày hiện tại**, gây sai partition, sai daily KPI, sai dwell, sai heatmap.

Production nên làm một trong hai cách:

```text
invalid capture_ts → DLQ
```

hoặc:

```text
capture_ts = NULL, record bị filter khỏi Silver
```

Không nên tự bịa timestamp hiện tại.

---

## 2.3. GoldTrackSummaryJob

Job này làm:

```text
silver_detections_v2
  ↓
gold_track_summary_v2
```

Nó group theo:

```text
store_id
camera_id
pipeline_run_id
global_track_id
```

để tính:

```text
enter_ts
exit_ts
duration_sec
frames
predicted_frames
representative_zone
```

Đây là đúng về mặt business: từ detection events tạo ra visit/track summary.

Nhưng đây là một trong các điểm rủi ro nhất.

### Vấn đề lớn: unbounded streaming aggregation

Query kiểu:

```sql
GROUP BY store_id, camera_id, pipeline_run_id, global_track_id
```

trên streaming source là **unbounded aggregation**.

Nghĩa là Flink phải giữ state cho từng `global_track_id`. Nếu mỗi ngày có hàng trăm nghìn track, state sẽ tăng mãi nếu không có TTL hoặc logic đóng session.

Về mặt production, đây là rủi ro lớn:

```text
state grows forever
checkpoint càng ngày càng nặng
recovery chậm
backpressure
out of memory
```

Cách sửa tốt hơn:

### Cách 1: dùng event/session completion

Nếu pipeline upstream biết khi nào track kết thúc, phát event:

```text
track_started
track_updated
track_ended
```

Khi nhận `track_ended`, Flink ghi summary rồi clear state.

### Cách 2: dùng session window

Ví dụ:

```text
global_track_id inactive 30s / 60s
→ close session
→ emit track summary
```

### Cách 3: nếu vẫn dùng SQL aggregation

Set state TTL:

```java
tEnv.getConfig().set("table.exec.state.ttl", "2 h");
```

Nhưng TTL chỉ là workaround. Với dữ liệu track/person, tốt nhất vẫn là có logic session/track end.

---

## 2.4. QueueAnalyticsJob

Job này tương tự `GoldTrackSummaryJob`, nhưng cho queue:

```text
silver_detections_v2
  ↓
gold_queue_sessions
```

Nó group theo:

```text
store_id
camera_id
queue_zone_id
global_track_id
```

và tính:

```text
enter_ts
exit_ts
wait_time_sec
frame_count
```



Vấn đề giống GoldTrackSummaryJob:

```text
unbounded group by global_track_id
```

Nếu không có TTL hoặc session close, state sẽ tăng mãi.

Ngoài ra, field:

```text
completed = FALSE
```

đang hardcode. Điều này cho thấy queue session chưa có lifecycle hoàn chỉnh.

Production nên có logic:

```text
person enters queue zone
person remains in queue zone
person exits queue zone
session completed = true
```

Hiện tại job đang tính wait time bằng:

```text
MAX(capture_ts) - MIN(capture_ts)
```

nhưng chưa thật sự biết session đã kết thúc hay chưa.

---

## 2.5. GoldDashboardAggregateJob

Job này tạo nhiều bảng Gold realtime/near-realtime:

```text
gold_camera_hourly_metrics
gold_camera_daily_metrics
gold_camera_daily_dwell
gold_alert_events
```

Nó dùng `StatementSet` để gom nhiều insert vào một Flink job. Đây là cách hợp lý nếu các sink này cùng lifecycle. Ví dụ nếu đây đều là dashboard metrics gần realtime, gom chung sẽ tiết kiệm scan source và dễ deploy. 

Nhưng có 2 vấn đề.

### Vấn đề 1: state cũng có thể tăng lâu dài

Các query kiểu:

```sql
GROUP BY store_id, camera_id, CAST(capture_ts AS DATE)
```

hoặc:

```sql
GROUP BY store_id, camera_id, CAST(capture_ts AS DATE), HOUR(capture_ts)
```

vẫn là streaming aggregation không có TTL.

State không tăng nhanh như track-level, nhưng vẫn tăng theo:

```text
store_id × camera_id × date × hour
```

Sau nhiều tháng/năm, state vẫn phình ra.

Nên set TTL cho realtime dashboard aggregation, ví dụ:

```text
table.exec.state.ttl = 3 d
```

hoặc chỉ giữ realtime window ngắn:

```text
last 24h / last 7d
```

Daily/weekly/monthly final metrics nên do batch job Airflow chạy.

### Vấn đề 2: realtime Gold và batch Gold serving đang bị trùng business logic

Bạn có:

```text
GoldDashboardAggregateJob
```

tính hourly/daily realtime facts.

Nhưng `GoldServingBatchJob` cũng tính:

```text
traffic_hourly
traffic_daily
dwell_daily
queue_daily
alert_daily
executive_daily
```

Điều này không sai, nhưng phải đặt tên rõ:

```text
Gold realtime/provisional
```

và:

```text
Gold serving/finalized
```

Nếu không, sau này dashboard/API sẽ không biết nên tin bảng nào.

Khuyến nghị:

```text
rva.gold_*              = realtime/upsert/provisional facts
rva_gold_serving.*      = batch finalized serving marts
```

và document rõ:

```text
Dashboard realtime dùng Redis + rva.gold_* gần realtime.
Dashboard historical dùng rva_gold_serving.* finalized.
```

---

## 2.6. RealtimeMetricsJob

Đây là job dùng DataStream API, thiết kế khá đúng với nhu cầu low-latency:

```text
Pulsar detection events
  ↓
parse + validate
  ↓
dedup event_id
  ↓
Redis live state
  ↓
DLQ Pulsar cho invalid events
```

Job có validate event, check `event_id`, `camera_id`, `store_id`, `capture_ts`, `image_size`, parse detections, gán watermark 5 giây, dedup bằng keyed state TTL 10 phút, rồi ghi Redis và DLQ. 

Điểm tốt:

```text
Realtime serving không ghi Iceberg rồi mới query.
Nó ghi thẳng Redis để UI latency thấp.
```

Đây là đúng.

Nhưng production có vài vấn đề:

### Vấn đề 1: Redis sink không exactly-once

Redis là external side-effect sink. Code dùng `RichSinkFunction` và ghi Redis trực tiếp bằng Jedis. Redis write không gắn với Flink checkpoint, nên không exactly-once. 

Nhưng với realtime cache thì điều này **chấp nhận được**.

Bạn chỉ cần document rõ:

```text
Redis = live serving cache, not source of truth.
Iceberg = source of truth.
```

### Vấn đề 2: Redis exception đang bị swallow

Trong `invoke`, nếu Redis write fail, code:

```java
LOG.warn(...)
```

rồi bỏ qua. 

Điều này giúp job không chết, nhưng dashboard có thể sai mà Airflow/Flink vẫn báo xanh.

Nên thêm metric:

```text
redis_write_failed_total
redis_write_latency_ms
redis_pool_exhausted_total
```

và alert nếu Redis lỗi quá nhiều.

Có thể chọn một trong hai policy:

```text
Best-effort cache:
  log + metric + alert, job không fail

Strict realtime:
  fail job để restart khi Redis lỗi
```

Với dashboard realtime, best-effort là được, nhưng phải có monitoring.

### Vấn đề 3: Redis write nên dùng pipeline

Hiện mỗi event có nhiều Redis command:

```text
setex
zincrby
expire
hset
expire
lpush
ltrim
...
```

Ở throughput cao, nên dùng Redis pipeline để giảm round-trip.

---

# 3. Thiết kế Airflow DAGs có chuẩn không?

Tư duy của bạn là đúng:

```text
Airflow không transform data.
Airflow chỉ schedule, retry, dependency, backfill, maintenance.
Flink/Trino mới xử lý data.
```

README cũng mô tả rõ mỗi domain nghiệp vụ là một DAG, daily schedule, catchup=True, mỗi run xử lý đúng một ngày. Đây là pattern hợp lý.

Ví dụ:

```text
gold_serving_traffic:
apply_ddl
  ↓
traffic_hourly
  ↓
traffic_daily
```

```text
gold_serving_heatmap:
apply_ddl
  ↓
heatmap_5min
  ↓
heatmap_hour
```

```text
gold_serving_executive:
wait traffic/dwell/queue/alert
  ↓
executive_daily
```

Thiết kế này **ổn cho đồ án và MVP**.

Nhưng nếu xét production thì cần sửa vài điểm.

---

## 3.1. Cross-DAG `ExternalTaskSensor` có thể gây nợ vận hành

Bạn dùng consumer DAG `gold_serving_executive` chờ các DAG domain khác chạy xong. Pattern này dùng được, nhưng khi:

```text
catchup=True
nhiều DAG
nhiều ngày backfill
SequentialExecutor hoặc ít worker
```

thì dễ gặp:

```text
sensor chờ lâu
logical_date lệch
task bị serialize
backfill khó debug
```

Nếu production, có 2 lựa chọn tốt hơn.

### Option A: Một master DAG với TaskGroup

```text
gold_serving_daily
  ├── traffic group
  ├── heatmap group
  ├── queue group
  ├── zone group
  ├── dwell group
  ├── alert group
  └── executive_daily
```

Ưu điểm:

```text
dependency rõ trong một DAG
backfill dễ
UI dễ nhìn
ít sensor hơn
```

### Option B: Vẫn nhiều DAG nhưng dùng Dataset/Event-based scheduling

Các domain DAG publish dataset:

```text
gold_serving_traffic_daily partition={{ ds }}
gold_serving_queue_daily partition={{ ds }}
...
```

Executive DAG consume dataset.

Cách này sạch hơn ExternalTaskSensor, nhưng Airflow Dataset partition awareness cần thiết kế thêm.

Với hệ thống hiện tại, mình nghiêng về:

```text
MVP/thesis: giữ nhiều DAG + ExternalTaskSensor.
Production nhỏ: gom thành một master DAG với TaskGroup.
Production lớn nhiều team: dùng Dataset/event-based orchestration.
```

---

## 3.2. Executive DAG đang có mismatch dependency

Theo README, `gold_serving_executive` chờ:

```text
traffic_daily
dwell_daily
queue_daily
alert_daily
```

Nhưng trong `GoldServingBatchJob.runExecutiveDaily`, query lại đọc trực tiếp từ:

```text
rva.gold_track_summary_v2
rva.gold_queue_sessions
rva.gold_alerts
```

chứ không đọc từ:

```text
rva_gold_serving.gold_serving_dwell_daily
rva_gold_serving.gold_serving_queue_daily
rva_gold_serving.gold_serving_alert_daily
```

Nó chỉ dùng serving traffic tables nhiều hơn các domain còn lại. 

Đây là một design inconsistency.

Bạn nên chọn một trong hai hướng.

### Hướng nên làm

`executive_daily` nên đọc từ các bảng serving đã finalized:

```text
gold_serving_traffic_daily
gold_serving_dwell_daily
gold_serving_queue_daily
gold_serving_alert_daily
```

Khi đó dependency Airflow có ý nghĩa thật.

### Hoặc nếu executive đọc raw Gold facts trực tiếp

Thì không cần chờ:

```text
dwell_daily
queue_daily
alert_daily
```

vì executive không dùng output của chúng.

Production nên tránh kiểu:

```text
DAG dependency nói một đằng,
SQL dependency chạy một nẻo.
```

Đây là technical debt đáng sửa sớm.

---

## 3.3. Airflow submit Flink qua REST API có chuẩn không?

Hiện flow là:

```text
Airflow BashOperator
  ↓
submit_batch_job.py
  ↓
POST /jars/upload
  ↓
POST /jars/{jar_id}/run
  ↓
GET /jobs/{job_id}
  ↓
DELETE /jars/{jar_id}
```

Đây là cách **dùng được**, nhất là local stack hoặc non-Kubernetes.

Nhưng production thì chưa phải cách tốt nhất.

### Điểm tốt

```text
Đơn giản
Dễ hiểu
Không cần Flink Kubernetes Operator
Airflow poll được job FINISHED/FAILED
```

### Điểm yếu

1. Upload jar lặp lại cho mỗi task.
2. Airflow worker bị giữ trong lúc chờ job.
3. Nếu Airflow task timeout/fail, Flink job có thể bị orphan nếu không cancel.
4. Không có savepoint/checkpoint lifecycle cho streaming.
5. Không có resource isolation tốt.
6. Không version artifact rõ ràng theo deployment.
7. Khó trace từ Airflow task sang Flink job nếu không persist job_id.

Với batch job ngắn thì chấp nhận được. Nhưng production nên chuyển sang một trong hai cách:

### Nếu dùng Kubernetes

```text
Airflow
  ↓
Flink Kubernetes Operator
  ↓
FlinkDeployment / FlinkSessionJob
```

### Nếu chưa dùng Kubernetes

```text
Airflow
  ↓
flink run hoặc REST submit
  ↓
Flink session cluster
```

nhưng cần bổ sung:

```text
job cancellation on timeout
job_id XCom
Flink UI link
retry idempotency
artifact versioning
resource pool
```

---

# 4. Đóng gói tất cả thành một Flink job duy nhất có anti-pattern không?

Ở đây cần phân biệt rất rõ.

## 4.1. Một JAR chứa nhiều Flink entry class: không phải anti-pattern

Bạn đang có một Maven artifact, rồi trong đó có nhiều class:

```text
org.rva.BronzeIngestJob
org.rva.silver.SilverJob
org.rva.gold.GoldTrackSummaryJob
org.rva.gold.QueueAnalyticsJob
org.rva.gold.GoldDashboardAggregateJob
org.rva.gold.GoldServingBatchJob
org.rva.realtime.RealtimeMetricsJob
```

Đây **không phải anti-pattern**.

Nhiều team production vẫn làm:

```text
one repo
one artifact
many entry classes
```

đặc biệt khi các jobs cùng domain, dùng chung model/schema/util.

## 4.2. Nhưng copy cùng một JAR thành nhiều tên là technical debt

Dockerfile đang copy cùng một file:

```text
silver-job-0.1.0.jar
```

thành:

```text
bronze-job.jar
silver-job.jar
gold-job.jar
gold-jobs.jar
realtime-job.jar
```

Điều này không sai về runtime, nhưng gây hiểu nhầm.

Người đọc sẽ tưởng đây là nhiều artifact khác nhau, trong khi thực ra là cùng một JAR.

Nên đổi thành:

```text
/opt/flink/usrlib/rva-flink-jobs-0.1.0.jar
```

và submit bằng entry class:

```text
--entry-class org.rva.silver.SilverJob
--entry-class org.rva.gold.GoldServingBatchJob
```

Tức là:

```text
Một JAR versioned
Nhiều entry class
Không copy nhiều tên giả
```

## 4.3. Một Flink job xử lý tất cả pipeline mới là anti-pattern

Nếu bạn làm kiểu:

```text
Bronze + Silver + Gold + Realtime + Batch
```

trong **một Flink job duy nhất**, thì đó là anti-pattern.

Vì:

```text
một sink lỗi → cả pipeline chết
upgrade Silver → ảnh hưởng Bronze/Gold
scale Gold → kéo theo Bronze
debug khó
checkpoint/state phình to
rollback khó
```

Nhưng hiện tại bạn **không làm vậy**. Bạn có nhiều entry class/job riêng.

Điểm cần sửa không phải là “một JAR”, mà là:

```text
một cluster session đang chạy quá nhiều streaming + batch cùng nhau
```

Đó mới là vấn đề production lớn hơn.

---

# 5. Technical debt và anti-pattern lớn nhất hiện tại

## Mức nghiêm trọng cao

### 1. Checkpoint/savepoint đang local

Config hiện tại:

```yaml
state.checkpoints.dir: file:///opt/flink/state/checkpoints
state.savepoints.dir: file:///opt/flink/state/savepoints
```

Đây là điểm yếu lớn nhất.

Nếu container/VM chết, state mất. Khi đó các job Iceberg incremental có thể scan lại table, dedup state mất, aggregation state mất.

Production nên dùng:

```yaml
state.checkpoints.dir: s3://.../flink/checkpoints
state.savepoints.dir: s3://.../flink/savepoints
```

hoặc MinIO nếu local.

Nếu không sửa điểm này, các claim như:

```text
exactly-once
recoverable
production streaming
```

chưa thật sự vững.

---

### 2. Streaming aggregation không có TTL/session close

Các job như:

```text
GoldTrackSummaryJob
QueueAnalyticsJob
GoldDashboardAggregateJob
```

đang có nhiều unbounded group-by. 

Điều này dễ làm Flink state tăng vô hạn.

Nên thêm ít nhất:

```java
tEnv.getConfig().set("table.exec.state.ttl", "2 h");
```

cho track/queue session nếu tạm thời.

Nhưng giải pháp đúng hơn:

```text
track session logic có timeout
queue session logic có enter/exit
daily/hourly final metrics chạy batch
```

---

### 3. Streaming và batch chạy chung một Flink session cluster

Bạn tăng:

```yaml
taskmanager.numberOfTaskSlots: 16
```

vì streaming layer đã ăn hết slot và batch bị timeout.

Điều này giải quyết được triệu chứng, nhưng production thì nên tách:

```text
Flink cluster A: streaming jobs 24/7
Flink cluster B: batch jobs do Airflow submit
```

Hoặc nếu Kubernetes:

```text
Mỗi streaming job = FlinkDeployment riêng
Batch job = ephemeral FlinkDeployment/FlinkSessionJob riêng
```

Hiện tại batch và streaming tranh slot là một dạng noisy-neighbor risk.

---

### 4. Airflow timeout chưa chắc cancel Flink job

`submit_batch_job.py` wait job tới timeout. Nếu timeout/fail, script delete uploaded jar nhưng không thấy cơ chế cancel job rõ ràng.

Nên sửa flow:

```text
submit job
store job_id
if timeout/failure:
    POST /jobs/{job_id}/yarn-cancel hoặc cancel endpoint
then fail Airflow task
```

Nếu không, Airflow task fail nhưng Flink job có thể vẫn chạy ngầm.

---

### 5. `INSERT OVERWRITE` cần kiểm chứng semantics

`GoldServingBatchJob` dùng nhiều:

```sql
INSERT OVERWRITE rva_gold_serving.table
SELECT ...
WHERE metric_date BETWEEN start AND end
```

Với Iceberg, bạn cần test kỹ:

```text
Overwrite toàn table?
Overwrite dynamic partitions?
Nếu output rỗng thì partition cũ có bị xóa không?
Retry có idempotent không?
```

Đây là điểm rất quan trọng.

Với batch daily serving, cách an toàn hơn là:

```text
DELETE FROM target WHERE metric_date BETWEEN start AND end
INSERT INTO target SELECT ...
```

hoặc dùng MERGE/upsert nếu phù hợp.

Nếu vẫn dùng `INSERT OVERWRITE`, phải có test chứng minh nó chỉ overwrite đúng partition.

---

## Mức nghiêm trọng trung bình

### 6. Gold Serving đang có hai implementation: Trino và Flink Batch

Bạn có:

```text
services/gold_serving/*.py + Trino SQL
```

và:

```text
GoldServingBatchJob.java
```

Hai hướng này cùng giải quyết Gold serving.

Trong giai đoạn migration thì ổn. Nhưng nếu để lâu sẽ thành debt:

```text
metric logic lệch nhau
bug fix phải sửa 2 nơi
Airflow DAG không biết source of truth là cái nào
```

Nên quyết định rõ:

```text
Option A: Trino là engine Gold serving chính.
Option B: Flink Batch là engine Gold serving chính.
Option C: Migration phase, deadline xóa Trino path.
```

Theo hướng hệ thống của bạn, mình khuyên:

```text
Flink streaming: Bronze/Silver/realtime Gold
Flink batch: finalized Gold serving
Trino: ad-hoc query/BI/debug, không phải transform engine chính
```

---

### 7. DDL trong job runtime bị lặp nhiều

Các job đều tự tạo catalog/table. Batch job `ensureServingTables` còn tạo rất nhiều bảng trước mỗi domain run.

Demo thì ổn.

Production nên tách:

```text
schema migration
catalog bootstrap
runtime transform
```

Ít nhất nên có một class chung:

```java
IcebergCatalogSupport
```

thay vì lặp code catalog ở mọi job.

---

### 8. SQL viết thành Java string quá dài

Các SQL lớn đang nằm trong Java string.

Điều này làm:

```text
khó review
khó format
khó test
khó diff
```

Nên chuyển sang:

```text
src/main/resources/sql/gold_serving/traffic_hourly.sql
```

rồi Java load file SQL.

Hoặc nếu muốn production hơn:

```text
Flink SQL Gateway
Airflow submit SQL file
```

Nhưng với hệ thống hiện tại, chỉ cần move SQL ra file resource đã tốt hơn nhiều.

---

### 9. `GoldServingSupport.executeAndAwait` không thật sự await rõ ràng

Tên method:

```java
executeAndAwait
```

nhưng code chỉ:

```java
tEnv.executeSql(sql);
```

Trong batch job, nên rõ ràng hơn:

```java
TableResult result = tEnv.executeSql(sql);
result.await();
```

Dù REST polling có thể thấy job status, code hiện tại gây hiểu nhầm và có thể tạo edge case tùy deployment mode.

---

### 10. Audit code có nhưng chưa dùng

`GoldServingSupport` có:

```text
writeAudit
scalarLong
runId
runMode
sourceTable
tableName
```

nhưng `executeStep` đang ignore các tham số này. 

Đây là debt tốt nên hoàn thiện.

Mỗi batch step nên ghi:

```text
run_id
domain
start/end
source_row_count
output_row_count
status
started_at
finished_at
error_message
```

vào:

```text
gold_serving_refresh_audit
```

---

## Mức thấp nhưng nên dọn

### 11. Default config hardcoded nhiều

Ví dụ:

```text
pulsar://pulsar-broker:6650
persistent://retail/metadata/events
flink-realtime-sub
```

Một số đã dùng env, nhưng chưa nhất quán.

Production nên đưa toàn bộ vào:

```text
env vars
config file
Kubernetes ConfigMap/Secret
```

---

### 12. `parallelism.default: 1`

Default 1 tốt cho debug, nhưng production gần như chắc chắn là bottleneck.

Nên set parallelism theo:

```text
Pulsar partitions
camera count
store count
throughput
Iceberg sink capacity
```

Ví dụ:

```text
Bronze ingest: parallelism = Pulsar partitions
Silver parse: parallelism = CPU-bound parse capacity
Realtime Redis: parallelism = camera shard count
Batch serving: parallelism = data volume/date partition size
```

---

### 13. 16 slots / 2GB TaskManager là cấu hình demo

```yaml
taskmanager.memory.process.size: 2048m
taskmanager.numberOfTaskSlots: 16
```

Nghĩa là trung bình mỗi slot chỉ khoảng:

```text
128MB process memory share
```

Slot không chia RAM cứng, nhưng thực tế nhiều task chạy cùng JVM sẽ tranh memory/CPU.

Với local/demo thì ổn.

Production nên sizing kiểu:

```text
slots ≈ CPU cores
memory đủ cho state + network + RocksDB/native memory
```

---

# 6. Kiến trúc nên sửa thành gì?

Mình đề xuất target architecture như sau.

## 6.1. Streaming layer

```text
Pulsar events
  ↓
BronzeIngestJob
  ↓
Iceberg bronze_raw
```

```text
bronze_raw hoặc Pulsar events
  ↓
SilverJob
  ↓
Iceberg silver_detections_v2
```

```text
Pulsar events
  ↓
RealtimeMetricsJob
  ↓
Redis live state + DLQ
```

```text
silver_detections_v2
  ↓
Gold realtime jobs
  ↓
rva.gold_* provisional tables
```

Nhưng với Gold realtime jobs, cần TTL/session close.

---

## 6.2. Batch serving layer

```text
Airflow
  ↓
Flink batch GoldServingBatchJob
  ↓
rva_gold_serving.*
```

Các bảng serving nên là finalized:

```text
traffic_daily
heatmap_hour
queue_daily
zone_daily
dwell_daily
alert_daily
executive_daily
```

Executive nên đọc từ serving tables, không đọc raw facts trực tiếp.

---

## 6.3. Cluster/deployment layout

Hiện tại:

```text
1 Flink session cluster
  ├── streaming jobs
  └── batch jobs
```

Nên đổi thành:

```text
Flink streaming cluster
  ├── BronzeIngestJob
  ├── SilverJob
  ├── RealtimeMetricsJob
  ├── GoldTrackSummaryJob
  ├── QueueAnalyticsJob
  └── GoldDashboardAggregateJob

Flink batch cluster/session
  └── Airflow-submitted GoldServingBatchJob
```

Nếu dùng Kubernetes thì tốt nhất:

```text
BronzeIngestJob         = FlinkDeployment riêng
SilverJob              = FlinkDeployment riêng
RealtimeMetricsJob     = FlinkDeployment riêng
Gold batch jobs        = FlinkSessionJob hoặc ephemeral FlinkDeployment
```

---

# 7. Airflow DAG nên tối ưu thế nào?

## Option đề xuất cho bạn hiện tại

Giữ per-domain DAG, nhưng sửa như sau:

```text
gold_serving_traffic
  apply_ddl
    ↓
  submit_flink_batch(domain=traffic_hourly)
    ↓
  submit_flink_batch(domain=traffic_daily)
    ↓
  quality_check_traffic
```

```text
gold_serving_executive
  wait/consume finalized serving daily tables
    ↓
  submit_flink_batch(domain=executive_daily)
    ↓
  quality_check_executive
```

Thêm Airflow pool:

```text
flink_batch_pool size = 1 hoặc 2
```

để tránh submit quá nhiều batch jobs cùng lúc làm nghẽn cluster.

## Nếu muốn production hơn

Gom thành một DAG:

```text
gold_serving_daily
  ├── traffic
  │    ├── traffic_hourly
  │    └── traffic_daily
  ├── heatmap
  │    ├── heatmap_5min
  │    └── heatmap_hour
  ├── queue
  │    ├── queue_hourly
  │    └── queue_daily
  ├── zone
  │    ├── zone_hourly
  │    └── zone_daily
  ├── dwell_daily
  ├── alert
  │    ├── alert_hourly
  │    └── alert_daily
  └── executive_daily
```

Dễ backfill hơn nhiều.

---

# 8. Cần sửa gì trước?

Thứ tự ưu tiên mình khuyên:

## P0 — Sửa ngay

1. Đổi checkpoint/savepoint sang S3/MinIO.
2. Tách batch và streaming resource, ít nhất bằng Airflow pool; tốt hơn là cluster riêng.
3. Thêm cancel Flink job khi Airflow task timeout/fail.
4. Kiểm chứng `INSERT OVERWRITE` Iceberg có overwrite đúng partition không.
5. Fix `executive_daily` đọc từ serving daily tables hoặc sửa lại dependency Airflow.

## P1 — Sửa sớm

6. Thêm `table.exec.state.ttl` cho streaming SQL aggregation.
7. Thiết kế lại `GoldTrackSummaryJob` và `QueueAnalyticsJob` theo session/track lifecycle.
8. Thêm DLQ cho Silver parse errors.
9. Không fallback invalid capture_ts về current time.
10. Hoàn thiện audit table cho Gold serving batch.

## P2 — Refactor sạch

11. Không copy cùng JAR thành nhiều tên.
12. Extract catalog config/common util.
13. Move SQL Java string ra resource `.sql`.
14. Dọn Trino vs Flink batch path, chọn một source of truth.
15. Thêm metrics cho Redis sink, parse errors, batch row counts, checkpoint duration.

---

# 9. Câu trả lời ngắn cho từng câu hỏi của bạn

## Thiết kế Flink jobs chuẩn chưa?

**Đúng hướng**, nhưng chưa production chuẩn hoàn toàn.

Đúng ở chỗ:

```text
Bronze raw
Silver structured
Gold facts
Realtime Redis
Batch serving
```

Chưa chuẩn ở chỗ:

```text
streaming aggregation có state vô hạn
checkpoint local
runtime job tự tạo DDL nhiều
gold realtime và gold serving trùng logic
```

---

## Thiết kế Airflow DAGs chuẩn chưa?

**Khá ổn cho MVP/thesis**, nhưng production nên cải thiện.

Đúng ở chỗ:

```text
Airflow chỉ orchestrate
mỗi domain có DAG riêng
daily/catchup/backfill rõ
```

Chưa ổn ở chỗ:

```text
ExternalTaskSensor cross-DAG có thể rối
Executive dependency mismatch với SQL
REST submit còn thiếu cancel/job tracking
SequentialExecutor không chạy song song thật
```

---

## Airflow orchestrate Flink jobs như hiện tại ổn không?

**Ổn cho local/non-K8s**, nhưng chưa tối ưu production.

Flow REST upload/run/wait/delete dùng được, nhưng nên thêm:

```text
cancel on timeout
job_id tracking
artifact versioning
Airflow pool
Flink UI link
async/deferrable waiting
```

Nếu production trên Kubernetes, nên chuyển sang:

```text
Flink Kubernetes Operator
```

---

## Đóng gói tất cả thành một JAR có anti-pattern không?

**Không.**

Một JAR chứa nhiều Flink entry class là bình thường.

Nhưng:

```text
copy cùng một JAR thành bronze-job.jar, silver-job.jar, gold-job.jar...
```

là technical debt vì gây hiểu nhầm.

Nên dùng:

```text
rva-flink-jobs-0.1.0.jar
```

và phân biệt bằng:

```text
entryClass
```

Anti-pattern thật sự là:

```text
một Flink job duy nhất xử lý tất cả Bronze/Silver/Gold/Realtime/Batch
```

Bạn hiện chưa rơi vào anti-pattern đó.

---

# 10. Kết luận cuối

Kiến trúc của bạn đã đi đúng đường:

```text
Flink = processing engine
Airflow = orchestration engine
Iceberg = lakehouse storage
Redis = realtime serving cache
Pulsar = event bus
```

Điểm mạnh nhất là bạn đã tách được:

```text
streaming realtime path
```

và:

```text
batch finalized serving path
```

Đây là tư duy rất production.

Nhưng để nâng từ “demo tốt” lên “production-grade”, bạn nên ưu tiên 5 việc:

```text
1. Durable checkpoint/savepoint trên S3/MinIO
2. Tách streaming và batch resources
3. Xử lý state TTL/session close cho streaming aggregations
4. Làm Airflow submit Flink robust hơn
5. Chuẩn hóa Gold serving source of truth và bỏ trùng Trino/Flink dần
```

Nói ngắn gọn: **khung kiến trúc đúng, nhưng phần reliability/state management/deployment lifecycle còn là technical debt lớn nhất.**
