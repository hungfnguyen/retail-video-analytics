---
tôi nghĩ 1 anti patten của project tôi nữa là cơ chế partition, phân tích cơ chế partition hiện tại của hệ thống, và đây là phần UI design của project tôi, để đáp ứng cho tầng BI như này /home/hungfnguyen/project/retail-video-analytics/docs/ui/rva-ui-refactor-docs thì bạn hãy thiết kế lại cơ chế partition cho hệ thống tôi đi
---

Đúng, **partition hiện tại là một technical debt / anti-pattern khá rõ** trong project của bạn.

Nó chưa làm hỏng hệ thống ngay vì data volume demo/thesis còn nhỏ, nhưng nếu đẩy lên BI thật với các filter như:

```text
Store
Camera
Zone
Date range
Layer
Traffic / Queue / Zone / Alert / Heatmap
```

thì cơ chế partition hiện tại sẽ bắt đầu gây:

```text
scan nhiều data không cần thiết
small files
compaction khó
BI query chậm
backfill khó kiểm soát
INSERT OVERWRITE rủi ro
filter UI không map tốt xuống lakehouse
```

UI spec của bạn đang hướng rõ tới business BI: Live Monitor cho vận hành realtime, Analyst Dashboard có filter Store/Camera/Zone/Date Range và các tab Overview/Traffic/Queue/Zones/Alerts, còn Heatmap cần filter Camera/Date Range/Layer và insight theo hotspot/zone/time. Nghĩa là partition phải được thiết kế xoay quanh **business date + store + optional camera/zone**, không chỉ xoay quanh camera hoặc raw technical table. 

---

# 1. Audit partition hiện tại

## 1.1 Bronze

Hiện tại:

```sql
bronze_raw
PARTITIONED BY (store_id)
```

Vấn đề:

```text
Có store_id nhưng không có ngày.
```

Trong thực tế, hầu hết thao tác với Bronze sẽ là:

```text
replay ngày hôm qua
debug camera X trong ngày Y
backfill ngày D
kiểm tra event lỗi theo time range
```

Nhưng nếu Bronze chỉ partition theo `store_id`, thì query kiểu:

```sql
WHERE store_id = 'store_01'
  AND capture_date = DATE '2026-06-14'
```

vẫn có nguy cơ scan rất nhiều file của cả store.

Đây là anti-pattern lớn nhất ở Bronze.

---

## 1.2 Silver

Hiện tại:

```sql
silver_detections_v2
partitioning = 'store_id,bucket(16, camera_id),days(capture_ts)'
```

Cái này **khá ổn hơn Bronze** vì đã có:

```text
store_id
camera_id bucket
capture_ts day
```

Nhưng vẫn có vấn đề.

Thứ nhất, UI/BI thường query theo:

```sql
WHERE metric_date BETWEEN ...
```

hoặc:

```sql
WHERE business_date = ...
```

Trong khi partition lại nằm trên:

```sql
days(capture_ts)
```

Nếu query dùng `CAST(capture_ts AS DATE)` hoặc một cột derived date khác, engine có thể không prune partition tốt bằng query trực tiếp trên partition source column.

Thứ hai, `capture_ts` thường là UTC hoặc `TIMESTAMP_LTZ`. Nhưng BI retail cần:

```text
business date theo timezone của store
```

Ví dụ store ở Sydney, event UTC 23:30 có thể là ngày hôm sau theo local business day. UI có `Today`, `Yesterday`, `Last 7 days`, nên nếu bạn dùng UTC date thì KPI ngày có thể sai.

---

## 1.3 Gold track / queue session

Hiện tại có dạng:

```sql
gold_track_summary_v2
partitioning = 'store_id,bucket(16, camera_id),days(visit_date)'
```

```sql
gold_queue_sessions
partitioning = 'store_id,bucket(16, camera_id),days(visit_date)'
```

Vấn đề:

```text
visit_date là DATE nhưng dùng days(visit_date)
```

Không phải quá nghiêm trọng, nhưng hơi lẫn giữa hidden transform và explicit date column.

Với BI, bạn nên chuẩn hóa:

```text
metric_date / business_date / visit_date là DATE rõ ràng
partition trực tiếp theo DATE đó
```

Ví dụ:

```sql
partitioning = 'visit_date,store_id,bucket(16,camera_id)'
```

hoặc nếu dùng tên chuẩn hơn:

```sql
partitioning = 'business_date,store_id,bucket(16,camera_id)'
```

---

## 1.4 Gold alerts

Hiện tại:

```sql
gold_alerts
partitioning = 'days(event_ts)'
```

nhưng table lại có:

```sql
store_id
camera_id
event_date
event_ts
severity
alert_type
zone
```

Đây là điểm chưa tốt.

UI Alerts tab sẽ query kiểu:

```text
date range
store
camera
zone
severity
alert type
```

Nếu partition chỉ là `days(event_ts)`, query theo store sẽ không prune tốt. Ngoài ra nếu API filter theo `event_date`, nhưng partition lại là `days(event_ts)`, pruning có thể không tối ưu.

Nên đổi sang:

```sql
partitioning = 'event_date,store_id'
```

hoặc:

```sql
partitioning = 'metric_date,store_id'
```

và sort/cluster theo:

```text
camera_id
severity
alert_type
event_ts
```

---

## 1.5 Gold serving tables

Hiện tại nhiều bảng serving dùng:

```sql
partitioning = 'metric_date,bucket(16, camera_id)'
```

Ví dụ:

```text
gold_serving_traffic_hourly
gold_serving_traffic_daily
gold_serving_queue_hourly
gold_serving_zone_hourly
gold_serving_heatmap_tile_5min
...
```

Vấn đề lớn:

```text
Thiếu store_id trong partition.
```

Trong UI, filter đầu tiên về mặt business là:

```text
Store
```

Camera chỉ là filter phụ. Nếu sau này có nhiều store, partition không có `store_id` sẽ rất bất lợi.

Vấn đề thứ hai:

```text
bucket(16,camera_id) bị dùng quá rộng.
```

Với bảng aggregate nhỏ như:

```text
traffic_daily
queue_daily
alert_daily
executive_daily
```

việc bucket camera có thể làm file nhỏ hơn, nhiều partition hơn, compaction khó hơn. Camera bucket hợp lý ở bảng high-volume như:

```text
silver_detections
heatmap_tile_5min
heatmap_cell_hourly
```

nhưng không nhất thiết hợp lý ở mọi bảng daily aggregate.

---

# 2. Anti-pattern partition hiện tại

Mình thấy 7 anti-pattern chính.

## Anti-pattern 1: Bronze không partition theo thời gian

Hiện tại:

```text
bronze_raw partition by store_id
```

Nên là:

```text
business_date + store_id + optional camera bucket
```

Bronze là nơi replay/backfill/debug nhiều nhất. Không có date partition là sai hướng.

---

## Anti-pattern 2: Không có chuẩn `business_date`

Bạn đang dùng nhiều khái niệm:

```text
capture_ts
event_ts
visit_date
metric_date
event_date
ingest_ts
```

Nhưng chưa có chuẩn rõ:

```text
business_date theo timezone của store
```

Với BI retail, đây là cực kỳ quan trọng.

UI hỏi:

```text
Today
Yesterday
Last 7 days
Peak day
Daily summary
```

Các khái niệm này nên dựa trên `business_date`, không nên phụ thuộc ngầm vào UTC timestamp.

---

## Anti-pattern 3: Query filter và partition field không luôn khớp

Ví dụ:

```text
partition by days(event_ts)
```

nhưng query/API có thể filter bằng:

```text
event_date
CAST(event_ts AS DATE)
metric_date
```

Trong Lakehouse, muốn pruning tốt thì query nên filter đúng column/transform mà partition spec hiểu được.

Cách tốt hơn cho BI:

```text
luôn có explicit DATE column
business_date / metric_date / event_date
```

và partition trực tiếp theo cột đó.

---

## Anti-pattern 4: Bucket camera quá nhiều ở bảng aggregate nhỏ

Ví dụ daily table chỉ có vài chục/vài trăm row mỗi ngày nhưng vẫn:

```text
bucket(16,camera_id)
```

Điều này có thể làm:

```text
nhiều file nhỏ
nhiều partition nhỏ
OPTIMIZE/compaction phải chạy nhiều hơn
query metadata overhead cao hơn data scan
```

Với aggregate serving table, thường nên partition đơn giản hơn.

---

## Anti-pattern 5: Thiếu partition theo `store_id` ở serving layer

BI dashboard gần như luôn filter theo:

```text
store_id
date range
```

Nên serving tables cần partition tối thiểu:

```text
metric_date, store_id
```

Hiện tại nhiều bảng serving chỉ có:

```text
metric_date,bucket(camera_id)
```

Điều này chưa align với UI.

---

## Anti-pattern 6: Zone BI chưa có partition/schema đúng

UI Analyst Dashboard có Zones tab, Heatmap cũng cần zone insight.

Nhưng hiện tại zone metrics đang rải trong:

```text
silver_detections_v2.primary_zone_id
gold_serving_zone_hourly
gold_serving_zone_daily
heatmap grid cells
```

Chưa có một thiết kế rõ cho:

```text
zone traffic
zone dwell
zone utilization
zone heatmap contribution
```

Partition hiện tại không sai hoàn toàn, nhưng schema/partition chưa đủ tốt cho BI zone-level.

---

## Anti-pattern 7: Partition không gắn với Airflow daily run

Airflow của bạn thiết kế:

```text
mỗi DAG run xử lý đúng 1 ngày {{ ds }}
```

Nhưng partition design chưa thống nhất quanh:

```text
metric_date = {{ ds }}
business_date = {{ ds }}
```

Đây là mismatch.

Batch serving nên luôn có contract:

```text
Airflow logical date
=
metric_date/business_date partition cần refresh
```

---

# 3. Partition strategy mới nên theo hướng nào?

Bạn nên thiết kế partition theo **query pattern của UI**, không theo cảm giác kỹ thuật.

UI của bạn cần các query chính:

```text
Live Monitor:
- realtime by camera/store
- Redis là chính, Iceberg không phải path chính

Analyst Dashboard:
- store + date range
- optional camera
- optional zone
- traffic / queue / dwell / alerts / zones

Heatmap:
- camera + date range
- later: layer = presence / dwell / queue pressure
- later: zone hotspot / zone contribution
```

Vì vậy partition nên theo nguyên tắc:

```text
High-volume fact table:
  business_date + store_id + bucket(camera_id)

Serving aggregate table:
  metric_date + store_id
  sort/cluster by camera_id, zone_id, hour

Heatmap cell/tile table:
  metric_date + store_id + bucket(camera_id)
  optional layer as sort key, not always partition

Alert table:
  metric_date/event_date + store_id
  sort by severity, alert_type, camera_id, event_ts
```

---

# 4. Chuẩn hóa field thời gian trước khi partition

Trước khi sửa partition, bạn nên chuẩn hóa các cột sau.

## Trong Bronze

Thêm:

```text
capture_ts
business_date
ingest_date
event_hour
```

Ví dụ:

```text
capture_ts     = timestamp từ event camera
business_date  = local date của store
ingest_date    = date lúc Flink ingest
event_hour     = local hour nếu cần
```

## Trong Silver

Bắt buộc có:

```text
capture_ts
business_date
hour_of_day
bucket_hour
```

## Trong Gold/Serving

Dùng tên chuẩn:

```text
metric_date
bucket_hour
hour_of_day
store_id
camera_id
zone_id
```

Không nên mỗi bảng dùng một kiểu:

```text
event_date
visit_date
metric_date
capture_date
```

Trừ khi business meaning thật sự khác nhau.

Khuyến nghị:

```text
Raw/Silver:
  business_date

Track/session:
  visit_date

Serving/BI:
  metric_date

Alerts:
  event_date hoặc metric_date
```

Nhưng trong API BI, map tất cả về:

```text
metric_date
```

---

# 5. Thiết kế partition mới theo từng layer

## 5.1 Bronze raw

### Hiện tại

```sql
PARTITIONED BY (store_id)
```

### Đề xuất

```sql
partitioning = 'business_date,store_id,bucket(8,camera_id)'
```

hoặc nếu số camera ít:

```sql
partitioning = 'business_date,store_id'
```

### Lý do

Bronze dùng cho:

```text
debug ngày D
replay store S
reprocess camera C
kiểm tra data loss theo ngày
```

Query phổ biến:

```sql
WHERE business_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
  AND store_id = 'store_01'
```

Partition mới sẽ prune tốt hơn rất nhiều.

### DDL concept

```sql
CREATE TABLE rva.bronze_raw_v2 (
  schema_version STRING,
  event_id STRING,
  pipeline_run_id STRING,
  frame_index BIGINT,
  payload STRING,
  camera_id STRING,
  store_id STRING,
  capture_ts TIMESTAMP_LTZ(3),
  business_date DATE,
  ingest_ts TIMESTAMP_LTZ(3),
  ingest_date DATE
)
WITH (
  'format-version' = '2',
  'write.format.default' = 'parquet',
  'partitioning' = 'business_date,store_id,bucket(8,camera_id)'
);
```

---

## 5.2 Silver detections

### Hiện tại

```sql
partitioning = 'store_id,bucket(16, camera_id),days(capture_ts)'
```

### Đề xuất

```sql
partitioning = 'business_date,store_id,bucket(16,camera_id)'
```

### Lý do

Silver là high-volume fact table. Nó phục vụ:

```text
traffic hourly
heatmap
zone metrics
queue session
track summary
```

Gần như tất cả đều filter theo ngày.

Nên dùng explicit `business_date` để:

```text
Airflow backfill dễ
BI filter đúng local date
query không cần CAST(capture_ts AS DATE)
```

### DDL concept

```sql
CREATE TABLE rva.silver_detections_v3 (
  schema_version STRING,
  event_type STRING,
  event_id STRING,
  detection_id STRING,
  pipeline_run_id STRING,

  store_id STRING,
  camera_id STRING,

  frame_index BIGINT,
  capture_ts TIMESTAMP_LTZ(3),
  business_date DATE,
  bucket_hour TIMESTAMP_LTZ(3),
  hour_of_day INT,

  class_id INT,
  class_name STRING,
  conf DOUBLE,

  bbox_x1 INT,
  bbox_y1 INT,
  bbox_x2 INT,
  bbox_y2 INT,

  track_id BIGINT,
  raw_track_id BIGINT,
  global_track_id STRING,
  is_predicted BOOLEAN,

  anchor_x_norm DOUBLE,
  anchor_y_norm DOUBLE,

  primary_zone_id STRING,
  primary_zone_type STRING,
  in_queue BOOLEAN,
  queue_zone_id STRING,

  processing_ts TIMESTAMP_LTZ(3)
)
WITH (
  'format-version' = '2',
  'write.format.default' = 'parquet',
  'partitioning' = 'business_date,store_id,bucket(16,camera_id)'
);
```

### Không nên partition theo

```text
global_track_id
track_id
frame_index
detection_id
zone_id
```

Vì đây là high-cardinality hoặc query phụ. Partition theo các field này sẽ gây partition explosion.

---

## 5.3 Gold track summary

### Hiện tại

```sql
partitioning = 'store_id,bucket(16, camera_id),days(visit_date)'
```

### Đề xuất

```sql
partitioning = 'visit_date,store_id'
```

hoặc nếu data lớn theo camera:

```sql
partitioning = 'visit_date,store_id,bucket(8,camera_id)'
```

### Lý do

`gold_track_summary_v2` là session/visit table. Query BI thường là:

```text
avg dwell by day
avg dwell by store
avg dwell by zone
track count by day
```

Camera filter là phụ. Không cần bucket camera quá mạnh nếu table đã aggregate theo track.

Nên sort/cluster theo:

```text
camera_id
representative_zone_id
global_track_id
```

thay vì partition quá nhỏ.

---

## 5.4 Gold queue sessions

### Hiện tại

```sql
partitioning = 'store_id,bucket(16, camera_id),days(visit_date)'
```

### Đề xuất

```sql
partitioning = 'visit_date,store_id'
```

hoặc nếu queue session volume lớn:

```sql
partitioning = 'visit_date,store_id,bucket(8,queue_zone_id)'
```

### Lý do

Queue tab sẽ hỏi:

```text
queue sessions by date
avg wait by hour
worst queue zone
SLA violations
```

Filter chính:

```text
date range + store + optional zone
```

Với vài queue zone, không cần partition zone. Nếu store có rất nhiều zone/camera, dùng bucket zone.

---

## 5.5 Gold alerts

### Hiện tại

```sql
partitioning = 'days(event_ts)'
```

### Đề xuất

```sql
partitioning = 'event_date,store_id'
```

### Lý do

Alerts tab query theo:

```text
date range
store
severity
alert_type
zone
camera
```

Partition theo `event_date,store_id` là phù hợp nhất.

Không nên partition theo `severity` hoặc `alert_type`, vì hai field này low-cardinality nhưng có thể tạo nhiều file nhỏ. Sort theo chúng là đủ.

### DDL concept

```sql
CREATE TABLE rva.gold_alerts_v2 (
  alert_id STRING,
  store_id STRING,
  camera_id STRING,
  zone STRING,
  alert_type STRING,
  severity STRING,
  event_ts TIMESTAMP_LTZ(3),
  event_date DATE,
  clip_s3_key STRING,
  clip_s3_uri STRING,
  refreshed_at TIMESTAMP_LTZ(3),
  PRIMARY KEY (alert_id) NOT ENFORCED
)
WITH (
  'format-version' = '2',
  'write.format.default' = 'parquet',
  'write.upsert.enabled' = 'true',
  'partitioning' = 'event_date,store_id'
);
```

---

# 6. Gold serving partition design cho UI mới

Đây là phần quan trọng nhất vì tầng BI sẽ query chủ yếu từ `rva_gold_serving`.

## 6.1 Traffic hourly

Dùng cho:

```text
Analyst Overview
Traffic tab
Peak hour
Visitors over time
Peak hour heatmap
```

### Grain

```text
store_id + camera_id + bucket_hour
```

### Partition đề xuất

```sql
partitioning = 'metric_date,store_id'
```

### Không nên

```sql
partitioning = 'metric_date,bucket(16,camera_id)'
```

vì thiếu store và có thể over-partition.

### Table concept

```sql
gold_serving_traffic_hourly (
  store_id STRING,
  camera_id STRING,
  bucket_hour TIMESTAMP(6),
  metric_date DATE,
  hour_of_day INT,
  visitor_observations BIGINT,
  unique_track_count BIGINT,
  avg_people_count DOUBLE,
  max_people_count BIGINT,
  avg_conf DOUBLE,
  refreshed_at TIMESTAMP(6)
)
WITH (
  'partitioning' = 'metric_date,store_id'
);
```

Nếu camera volume lớn, dùng:

```sql
partitioning = 'metric_date,store_id,bucket(8,camera_id)'
```

nhưng chỉ khi thực sự cần.

---

## 6.2 Traffic daily

Dùng cho:

```text
Total visitors
Peak day
Visitors by day
Daily summary
Executive daily
```

### Grain

```text
store_id + camera_id + metric_date
```

### Partition đề xuất

```sql
partitioning = 'metric_date,store_id'
```

Daily table nhỏ, không nên bucket camera mặc định.

---

## 6.3 Queue hourly

Dùng cho:

```text
Queue tab
Avg wait by hour
Worst queue time
SLA trend
```

### Grain

```text
store_id + camera_id + queue_zone_id + bucket_hour
```

### Partition đề xuất

```sql
partitioning = 'metric_date,store_id'
```

Nếu nhiều queue zones:

```sql
partitioning = 'metric_date,store_id,bucket(8,queue_zone_id)'
```

Nhưng với retail store thông thường, date + store là đủ.

---

## 6.4 Queue daily

Dùng cho:

```text
Avg Queue Wait
Longest Wait
Queue Sessions
SLA Violations
Worst Queue Zone
```

### Partition đề xuất

```sql
partitioning = 'metric_date,store_id'
```

Sort theo:

```text
queue_zone_id
camera_id
```

---

## 6.5 Zone hourly / zone daily

Dùng cho:

```text
Zones tab
Top zones
Zone utilization
Dwell by zone
Underused zones
```

### Grain hourly

```text
store_id + camera_id + zone_id + bucket_hour
```

### Grain daily

```text
store_id + camera_id + zone_id + metric_date
```

### Partition đề xuất

```sql
partitioning = 'metric_date,store_id'
```

Không nên partition trực tiếp theo `zone_id` nếu số zone không quá lớn. Zone nên là sort/cluster key.

Nếu sau này mỗi store có hàng trăm zones:

```sql
partitioning = 'metric_date,store_id,bucket(16,zone_id)'
```

---

## 6.6 Dwell daily

Dùng cho:

```text
Average dwell time
Dwell by camera
Dwell by zone
Executive daily
```

### Partition đề xuất

```sql
partitioning = 'metric_date,store_id'
```

Nếu muốn dwell by zone tốt hơn, nên có bảng riêng:

```text
gold_serving_zone_dwell_daily
```

hoặc merge vào:

```text
gold_serving_zone_daily
```

---

## 6.7 Alert hourly / daily

Dùng cho:

```text
Alerts tab
Alert trend
Alert severity
Most affected zone
Most frequent alert type
```

### Partition đề xuất

```sql
partitioning = 'metric_date,store_id'
```

Sort theo:

```text
severity
alert_type
zone
camera_id
```

Không partition theo severity/alert_type vì dễ tạo nhiều file nhỏ.

---

## 6.8 Executive daily

Hiện tại:

```sql
partitioning = 'metric_date'
```

Đề xuất:

```sql
partitioning = 'metric_date,store_id'
```

Vì executive dashboard chắc chắn theo store.

### Grain

```text
store_id + metric_date
```

---

# 7. Heatmap partition design mới

Heatmap là case đặc biệt vì data có thể lớn hơn daily aggregate.

UI Heatmap cần:

```text
camera
date range
layer: presence / dwell / queue pressure
top hotspots
zone contribution
```

Hiện tại bạn có:

```text
gold_serving_heatmap_tile_5min
gold_serving_heatmap_tile_hour
```

partition:

```text
metric_date,bucket(16,camera_id)
```

Thiếu `store_id`.

---

## 7.1 Heatmap tile 5min

Dùng cho chi tiết cao hoặc replay.

### Grain

```text
store_id + camera_id + bucket_start + tile_x + tile_y
```

### Partition đề xuất

```sql
partitioning = 'metric_date,store_id,bucket(16,camera_id)'
```

Lý do:

```text
Heatmap luôn chọn camera.
Date range luôn có.
Store filter nên có.
Data volume theo tile lớn hơn daily metrics.
```

---

## 7.2 Heatmap tile hour

Dùng cho BI/Heatmap page nhiều hơn 5min.

### Grain

```text
store_id + camera_id + bucket_hour + tile_x + tile_y
```

### Partition đề xuất

```sql
partitioning = 'metric_date,store_id,bucket(16,camera_id)'
```

---

## 7.3 Nên thêm bảng mới: heatmap_cell_hourly

Để phục vụ UI Heatmap tốt hơn, nên có bảng này:

```text
gold_serving_heatmap_cell_hourly
```

### Grain

```text
store_id
camera_id
metric_date
bucket_hour
layer
grid_row
grid_col
```

### DDL concept

```sql
CREATE TABLE rva_gold_serving.gold_serving_heatmap_cell_hourly (
  store_id STRING,
  camera_id STRING,
  metric_date DATE,
  bucket_hour TIMESTAMP(6),
  hour_of_day INT,

  layer STRING, -- presence | dwell | queue_pressure

  grid_rows INT,
  grid_cols INT,
  grid_row INT,
  grid_col INT,

  intensity DOUBLE,
  observation_count BIGINT,
  avg_dwell_sec DOUBLE,
  avg_wait_sec DOUBLE,

  refreshed_at TIMESTAMP(6)
)
WITH (
  'format-version' = '2',
  'write.format.default' = 'parquet',
  'partitioning' = 'metric_date,store_id,bucket(16,camera_id)'
);
```

Không cần partition theo `layer` trước mắt vì số layer ít. Sort theo:

```text
layer
camera_id
bucket_hour
grid_row
grid_col
```

Nếu sau này layer nhiều và data rất lớn, mới cân nhắc:

```sql
partitioning = 'metric_date,store_id,layer,bucket(16,camera_id)'
```

---

## 7.4 Nên thêm bảng mới: zone spatial daily

UI Heatmap muốn nói:

```text
Top Hotspots
Zone Contribution
Hottest Area
Low Activity Area
```

Nếu chỉ có grid cell thì UI chỉ nói được:

```text
upper-right area
lower-left area
```

Muốn nói được:

```text
Checkout Queue 03
Entrance
Promotion Area
Beverage Aisle
```

thì cần bảng zone-level.

### Table đề xuất

```text
gold_serving_zone_spatial_daily
```

### Grain

```text
store_id + camera_id + zone_id + metric_date + layer
```

### Partition

```sql
partitioning = 'metric_date,store_id'
```

### DDL concept

```sql
CREATE TABLE rva_gold_serving.gold_serving_zone_spatial_daily (
  store_id STRING,
  camera_id STRING,
  zone_id STRING,
  zone_name STRING,
  zone_type STRING,
  metric_date DATE,

  presence_score DOUBLE,
  presence_share DOUBLE,
  avg_dwell_sec DOUBLE,
  avg_wait_sec DOUBLE,
  max_occupancy BIGINT,
  alert_count BIGINT,

  refreshed_at TIMESTAMP(6)
)
WITH (
  'format-version' = '2',
  'write.format.default' = 'parquet',
  'partitioning' = 'metric_date,store_id'
);
```

Bảng này sẽ phục vụ:

```text
Heatmap Top Hotspots
Zones tab
Zone utilization
Zone dwell
Zone traffic share
```

---

# 8. Partition matrix đề xuất

| Table                               |      Volume | Query pattern                            | Partition nên dùng                            |
| ----------------------------------- | ----------: | ---------------------------------------- | --------------------------------------------- |
| `bronze_raw_v2`                     |        High | date + store + camera debug              | `business_date,store_id,bucket(8,camera_id)`  |
| `silver_detections_v3`              |   Very high | date + store + camera + zone aggregation | `business_date,store_id,bucket(16,camera_id)` |
| `gold_track_summary_v3`             |      Medium | visit date + store + dwell               | `visit_date,store_id`                         |
| `gold_queue_sessions_v2`            |      Medium | visit date + store + queue zone          | `visit_date,store_id`                         |
| `gold_alerts_v2`                    |  Low/medium | date + store + severity/type             | `event_date,store_id`                         |
| `gold_serving_traffic_hourly`       |      Medium | date + store + camera/hour               | `metric_date,store_id`                        |
| `gold_serving_traffic_daily`        |         Low | date + store                             | `metric_date,store_id`                        |
| `gold_serving_queue_hourly`         |  Low/medium | date + store + zone/hour                 | `metric_date,store_id`                        |
| `gold_serving_queue_daily`          |         Low | date + store + zone                      | `metric_date,store_id`                        |
| `gold_serving_zone_hourly`          |      Medium | date + store + zone/hour                 | `metric_date,store_id`                        |
| `gold_serving_zone_daily`           |         Low | date + store + zone                      | `metric_date,store_id`                        |
| `gold_serving_dwell_daily`          |         Low | date + store                             | `metric_date,store_id`                        |
| `gold_serving_alert_hourly`         |         Low | date + store + severity/type             | `metric_date,store_id`                        |
| `gold_serving_alert_daily`          |         Low | date + store + severity/type             | `metric_date,store_id`                        |
| `gold_serving_executive_daily`      |    Very low | date + store                             | `metric_date,store_id`                        |
| `gold_serving_heatmap_tile_5min`    |        High | date + store + camera                    | `metric_date,store_id,bucket(16,camera_id)`   |
| `gold_serving_heatmap_tile_hour`    | Medium/high | date + store + camera                    | `metric_date,store_id,bucket(16,camera_id)`   |
| `gold_serving_heatmap_cell_hourly`  | Medium/high | date + store + camera + layer            | `metric_date,store_id,bucket(16,camera_id)`   |
| `gold_serving_zone_spatial_daily`   |  Low/medium | date + store + zone                      | `metric_date,store_id`                        |
| `gold_serving_refresh_audit`        |         Low | partition date                           | `partition_date`                              |
| `gold_serving_data_quality_results` |         Low | partition date                           | `partition_date`                              |

---

# 9. Query examples sau khi partition đúng

## Analyst Traffic tab

```sql
SELECT
  metric_date,
  SUM(visitor_observations) AS visitors
FROM rva_gold_serving.gold_serving_traffic_daily
WHERE metric_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
  AND store_id = 'store_01'
GROUP BY metric_date
ORDER BY metric_date;
```

Pruning tốt vì dùng:

```text
metric_date
store_id
```

---

## Analyst Queue tab

```sql
SELECT
  queue_zone_id,
  SUM(sessions) AS sessions,
  AVG(avg_wait_sec) AS avg_wait_sec,
  MAX(max_wait_sec) AS max_wait_sec
FROM rva_gold_serving.gold_serving_queue_daily
WHERE metric_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
  AND store_id = 'store_01'
GROUP BY queue_zone_id;
```

Partition tốt:

```text
metric_date + store_id
```

Zone là group/filter phụ, không nhất thiết partition.

---

## Heatmap page

```sql
SELECT
  grid_row,
  grid_col,
  SUM(intensity) AS intensity
FROM rva_gold_serving.gold_serving_heatmap_cell_hourly
WHERE metric_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
  AND store_id = 'store_01'
  AND camera_id = 'cam_01'
  AND layer = 'presence'
GROUP BY grid_row, grid_col;
```

Partition tốt:

```text
metric_date + store_id + bucket(camera_id)
```

Layer nên sort/cluster, chưa cần partition.

---

# 10. Cần sửa Airflow theo partition mới

Airflow hiện đang chạy:

```text
--start {{ ds }}
--end {{ ds }}
```

Rất hợp để map vào:

```text
metric_date = {{ ds }}
```

Nhưng nên chuẩn hóa contract:

```text
Airflow DAG run date
=
business_date / metric_date cần refresh
```

## Batch task nên ghi rõ partition

Ví dụ:

```bash
python submit_batch_job.py \
  --domain traffic_hourly \
  --start {{ ds }} \
  --end {{ ds }} \
  --store-id store_01
```

Nếu multi-store, có thể dynamic task mapping:

```text
for each store_id:
  refresh traffic_hourly partition store_id + ds
```

## DQ check cũng nên partition-aware

Hiện DQ nên kiểm tra theo:

```text
table
metric_date
store_id
```

Ví dụ:

```text
gold_serving_traffic_daily
partition metric_date=2026-06-14 store_id=store_01
row_count > 0
```

Không nên chỉ check global table.

---

# 11. Cẩn thận với `INSERT OVERWRITE`

Bạn đang dùng nhiều:

```sql
INSERT OVERWRITE rva_gold_serving.table
SELECT ...
WHERE metric_date BETWEEN ...
```

Với partition mới, cần đảm bảo overwrite chỉ tác động đúng partition:

```text
metric_date + store_id
```

Nếu không chắc semantics, cách an toàn hơn là:

```sql
DELETE FROM target
WHERE metric_date BETWEEN DATE '...' AND DATE '...'
  AND store_id = 'store_01';

INSERT INTO target
SELECT ...
```

Hoặc dùng `MERGE INTO` nếu table có primary/equality key rõ.

Với batch daily BI, idempotency cực quan trọng:

```text
Airflow retry 3 lần
=
output vẫn đúng, không duplicate, không xóa nhầm ngày khác
```

---

# 12. Partition không đủ, cần compaction strategy

Flink streaming + Iceberg thường tạo small files, nhất là checkpoint 30s.

Partition tốt nhưng không compaction thì vẫn chậm.

Nên Airflow maintenance chạy theo partition gần đây:

```text
OPTIMIZE silver_detections_v3 WHERE business_date >= current_date - 2
OPTIMIZE gold_serving_* WHERE metric_date >= current_date - 7
```

Chiến lược:

```text
Bronze/Silver:
  compact last 1-3 days thường xuyên

Gold serving:
  compact partition sau khi batch refresh xong

Historical:
  compact/vacuum theo lịch 1 ngày hoặc 1 tuần
```

---

# 13. Thiết kế API BI nên đi theo partition mới

UI hiện tại muốn filter:

```text
Store
Camera
Zone
Date Range
Layer
```

Backend API nên chuyển từ:

```text
days=7
```

sang:

```text
store_id=store_01
camera_id=cam_01
zone_id=zone_03
start_date=2026-06-01
end_date=2026-06-07
layer=presence
```

Query backend sẽ map trực tiếp xuống partition:

```text
metric_date BETWEEN start_date AND end_date
store_id = ...
camera_id = ...
zone_id = ...
```

Tức là partition mới không chỉ là data-engineering optimization, nó là contract cho BI API.

---

# 14. Migration plan thực tế

Không nên sửa table cũ trực tiếp ngay nếu project đang chạy ổn. Nên làm theo version.

## Phase 1: thêm table v3/v2

Tạo:

```text
bronze_raw_v2
silver_detections_v3
gold_alerts_v2
gold_track_summary_v3
gold_queue_sessions_v2
```

và serving tables version mới nếu cần:

```text
gold_serving_traffic_hourly_v2
gold_serving_traffic_daily_v2
...
```

## Phase 2: sửa Flink jobs

Bronze:

```text
extract capture_ts
compute business_date
write bronze_raw_v2
```

Silver:

```text
read bronze_raw_v2
write silver_detections_v3
```

Gold:

```text
read silver_detections_v3
write gold_*_v2/v3
```

Batch serving:

```text
read new gold tables
write new serving tables
```

## Phase 3: backfill

Airflow chạy:

```text
for date in range:
  traffic_hourly
  traffic_daily
  queue_hourly
  queue_daily
  zone_hourly
  zone_daily
  dwell_daily
  alert_hourly
  alert_daily
  executive_daily
```

## Phase 4: switch API

API đọc từ:

```text
gold_serving_*_v2
```

## Phase 5: deprecate table cũ

Giữ table cũ một thời gian:

```text
silver_detections_v2
gold_serving_* old
```

sau đó drop hoặc archive.

---

# 15. Kết luận

Partition hiện tại **đúng một phần ở Silver**, nhưng nhìn tổng thể thì chưa align với BI/UI.

Vấn đề lớn nhất là:

```text
Bronze thiếu date partition
Serving thiếu store_id partition
Business date chưa chuẩn hóa
Camera bucket bị dùng quá rộng
Alerts partition không khớp filter BI
Heatmap/Zone chưa có bảng partition phù hợp cho insight UI
```

Thiết kế mới nên xoay quanh:

```text
business_date / metric_date
store_id
camera_id chỉ bucket ở bảng high-volume
zone_id là sort/group key, không partition mặc định
```

Công thức nhớ nhanh cho project của bạn:

```text
Raw/Silver high volume:
  business_date + store_id + bucket(camera_id)

Gold serving BI:
  metric_date + store_id

Heatmap high volume:
  metric_date + store_id + bucket(camera_id)

Alerts:
  event_date + store_id

Executive:
  metric_date + store_id
```

Đây sẽ làm hệ thống khớp hơn với UI mới: Analyst Dashboard query nhanh theo Store/Date/Camera/Zone, Heatmap query nhanh theo Camera/Date/Layer, còn Airflow daily backfill sẽ refresh đúng partition thay vì quét và overwrite quá rộng.
