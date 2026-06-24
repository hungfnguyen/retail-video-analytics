# Issue: Các vấn đề phát sinh khi restart hệ thống hàng ngày

**Ngày phát hiện:** 2026-06-24  
**Bối cảnh:** Hệ thống không chạy liên tục — mỗi ngày stop rồi start lại  
**Status:** Đã verify với codebase; fix đã implement trong code, pending runtime verification

---

## 1. Bối cảnh

Project chạy trên AWS EC2 (Singapore) và Vision service chạy local. Do giới hạn chi phí và tài nguyên, hệ thống **không chạy 24/7** — mỗi ngày khởi động thủ công và tắt sau khi demo/test xong.

Thiết kế ban đầu của một số thành phần giả định hệ thống chạy liên tục, dẫn đến một số issue khi restart thường xuyên.

---

## 2. Issues

### Issue 1 — Analytics thiếu data hôm nay tối đa 30 phút sau restart (HIGH)

**Triệu chứng:** Sau khi `docker compose up`, Analytics dashboard chưa có slice của ngày hôm nay trong khoảng tối đa 30 phút. Trong trạng thái vận hành bình thường, UI mặc định vẫn còn data các ngày trước; nếu vừa reset hoặc chưa có historical data thì chart có thể trống hoàn toàn.

**Root cause:**

DAG `gold_serving_today_refresh` schedule `*/30 * * * *` với `catchup=False`:

```
Stack restart lúc 9:00
  → First DAG run: 9:30 (hoặc 10:00 nếu vừa lỡ 30-min slot)
  → Trong window đó: gold_serving tables chưa có partition intraday mới cho hôm nay
  → Analytics API query → trả về data ngày cũ hoặc thiếu phần hôm nay
```

**File liên quan:**
- `infrastructure/airflow/dags/gold_serving_today_refresh.py` — schedule `*/30 * * * *`, catchup=False
- `frontend/src/features/analytics/AnalyticsPage.tsx` — preset mặc định là `last_7_days`
- `services/api/src/rva_api/api/v1/analytics_queries.py` — query theo range ngày, không chỉ `today`

---

### Issue 2 — Live dashboard có cold-start gap sau restart (MEDIUM)

**Triệu chứng:** Ngay sau khi stack start, Live Monitor có thể hiện occupancy = 0, heatmap trống, không có track nào cho đến khi Vision phát frame mới và `RealtimeMetricsJob` bắt đầu ghi Redis.

**Root cause:**

`flink-job-submitter` phải chờ tuần tự:

```
docker compose up
  → flink-jobmanager healthy         (~30s)
  → sleep 10s (TaskManager register)
  → submit Bronze → wait RUNNING
  → submit SilverRealtimeJob → wait RUNNING
  → submit Gold jobs...
  → submit RealtimeMetricsJob
  → chỉ sau đó Redis live keys mới bắt đầu được ghi
```

Trong giai đoạn cold start này:
- `stats:count:{cam}` không tồn tại → API trả về 0 người
- `heatmap:live:{cam}` trống → Heatmap page empty

**Lưu ý quan trọng:** con số `~90 giây` chỉ là estimate theo flow submit job, không phải bound tin cậy. Thời gian thực tế còn phụ thuộc vào việc Vision service có được khởi động chưa, vì Vision đang chạy thủ công ngoài `docker compose`.

**File liên quan:**
- `infrastructure/flink/scripts/submit-jobs.sh` — sequential job submission
- `services/flink-jobs/java/src/main/java/org/rva/realtime/RealtimeMetricsJob.java` — writes Redis live keys
- `services/api/src/rva_api/alert_evaluator.py` — cold start **không** tự bắn `pipeline_lag` nếu `live:frame:{cam}` chưa tồn tại

---

### Issue 3 — Restart có thể làm dwell analytics bị lệch / visit bị cắt đôi (MEDIUM)

**Triệu chứng:** Các visit đang diễn ra tại thời điểm restart có thể bị chia làm 2 đoạn độc lập trước/sau restart. Hệ quả là `duration_sec` bị ngắn hơn thực tế và tỉ lệ `short dwell` có thể tăng bất thường.

**Root cause:**

Có **hai nguyên nhân độc lập**:

1. `GoldTrackSummaryJob` là streaming aggregation job và checkpoint hiện được cấu hình:

- `execution.checkpointing.interval: 30s`
- `execution.checkpointing.externalized-checkpoint-retention: DELETE_ON_CANCELLATION`

Điều này nghĩa là khi job bị cancel bởi restart / `docker compose down`, externalized checkpoint sẽ bị xóa. `submit-jobs.sh` cũng không restore từ savepoint/checkpoint khi submit lại.

2. Vision tạo `pipeline_run_id` mới mỗi lần worker start. `global_track_id` cũng không chứa `pipeline_run_id`, mà chỉ có dạng `cam_xx_g_000001`. Vì `GoldTrackSummaryJob` group theo `(store_id, camera_id, pipeline_run_id, global_track_id)`, cùng một người trước và sau restart sẽ bị coi là hai track summary khác nhau.

```
Người vào store lúc 9:05, hệ thống stop lúc 9:10
  → Job bị cancel, externalized checkpoint bị xóa
  → Vision restart tạo pipeline_run_id mới
  → Restart xong: track đang dang dở không còn aggregate state cũ
  → Cùng một người trước/sau restart bị tách thành 2 summary rows

Kết quả: dwell_band có thể bị lệch về "short" dù thực tế người đứng lâu hơn
```

**File liên quan:**
- `services/flink-jobs/java/src/main/java/org/rva/gold/GoldTrackSummaryJob.java`
- `infrastructure/flink/conf/flink-conf.yaml` — `DELETE_ON_CANCELLATION`
- `infrastructure/flink/scripts/submit-jobs.sh` — submit không dùng `-s <savepoint>` / restore path
- `services/vision/worker.py` — tạo `pipeline_run_id` mới mỗi lần start
- `services/vision/features/detections.py` — `global_track_id` không gắn `pipeline_run_id`

---

### Issue 4 — Alert history mất sau mỗi restart (LOW)

**Triệu chứng:** Sau restart, tab Alerts trên Live Monitor trống hoàn toàn dù hôm qua có alerts.

**Root cause:**

Redis không có persistent volume → mọi alert key bị xóa khi restart:

```yaml
# docker-compose.yml — không có redis_data volume
volumes:
  trino_data: ✅
  flink_state: ✅
  pulsar_data: ✅
  pg_data: ✅
  # redis_data: ← KHÔNG CÓ
```

Alert evaluator repopulate sau ~10s nhưng **chỉ tạo alert mới** khi có threshold violation mới — không restore lịch sử. Alert lịch sử dài hạn chỉ tồn tại trong `gold_alerts` (Iceberg), không hiện trực tiếp trên Live Monitor.

**File liên quan:**
- `services/api/src/rva_api/alert_evaluator.py` — viết vào `alert:live:{cam}` ZSET (24h TTL)
- `docker-compose.yml` — Redis service không có volume mount

---

### Issue 5 — SilverRealtimeJob xử lý Pulsar backlog chậm (INFO)

**Triệu chứng:** Sau restart, Silver và các Gold jobs downstream **có thể** nhận data chậm hơn bình thường nếu Pulsar còn backlog chưa được ack từ lần chạy trước.

**Root cause:**

`SilverRealtimeJob` dùng named subscription `flink-silver-realtime-ok` — Pulsar nhớ offset. Sau restart, job phải process toàn bộ messages chưa ack từ lần stop trước trước khi xử lý realtime:

```
Stop lúc 11:00 PM, restart lúc 9:00 AM hôm sau
  → backlog cũ trong Pulsar vẫn còn
  → Silver job phải consume phần backlog đó trước khi bám sát realtime hoàn toàn
```

Đây là hành vi **đúng về correctness** (không mất data), nhưng có thể gây delay initial analytics. Con số `5-10 phút` hiện chưa được benchmark trong repo, nên chỉ nên coi là estimate.

**File liên quan:**
- `services/flink-jobs/java/src/main/java/org/rva/silver/SilverRealtimeJob.java` — subscription `flink-silver-realtime-ok`

---

## 3. Timeline thực tế sau mỗi restart

```
T+0s    docker compose up
T+30s   Flink JobManager healthy, Redis/Pulsar/Trino ready
T+60-120s*  Các Flink jobs lần lượt RUNNING
T+?     Vision service khởi động thủ công → live frame/count bắt đầu có data
T+30m** gold_serving_today_refresh chạy lần đầu → analytics có slice hôm nay
T+24h   @daily DAGs (dwell/queue/zone) chạy → data ngày hôm qua hoàn chỉnh

* chỉ là estimate theo trình tự submit hiện tại, không phải SLA cứng
** worst case: restart đúng lúc vừa lỡ 30-min slot → phải chờ đến slot tiếp theo
```

---

## 4. Những thứ KHÔNG bị ảnh hưởng khi restart

| Thành phần | Lý do an toàn |
|---|---|
| Iceberg tables (bronze/silver/gold) | Lưu trên S3, không mất |
| Gold Serving schema (`rva_gold_serving`) | Iceberg catalog dùng Postgres JDBC — persist qua restart |
| Airflow DAG history và state | Postgres-backed (`pg_data` volume) |
| Pulsar messages | `pulsar_data` volume — persist, Silver job sẽ process backlog |
| Analytics Redis cache bị xóa | **Tốt** — buộc fresh Trino query thay vì serve stale data |

---

## 5. Hướng xử lí

| Issue | Hướng fix | Độ phức tạp |
|---|---|---|
| Analytics thiếu slice hôm nay | Trigger `gold_serving_today_refresh` ngay khi stack start (startup script hoặc Airflow sensor) | Thấp |
| Live cold-start gap | Chấp nhận cho demo, hoặc pre-warm Redis / tự động start Vision sớm hơn / submit `RealtimeMetricsJob` sớm hơn | Trung bình |
| Dwell lệch do restart | Giữ checkpoint khi cancel hoặc restore từ savepoint; đồng thời làm rõ semantics identity qua restart | Cao |
| Alert history mất | Thêm `redis_data` volume + Redis persistence (`appendonly yes`) | Thấp |
| Pulsar backlog delay | Thêm lag metric monitoring — không cần fix, chỉ cần document | Không cần fix |
