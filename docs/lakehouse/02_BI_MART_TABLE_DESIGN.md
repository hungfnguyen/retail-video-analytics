# Gold Serving Table Design

Tài liệu này thay cho cách gọi `mart layer`. Từ đây trở đi, các bảng phục vụ analyst sẽ được gọi là **Gold serving tables**.

## 1. Nguyên tắc

### 1.1 Vẫn là Gold

Những bảng này không tạo một tier mới.

Chúng là:

- Gold aggregate
- Gold serving
- query-ready Gold

Tức là:

```text
Gold facts
Gold serving tables
```

đều cùng thuộc `Gold`.

### 1.2 Thiết kế từ use case analyst

Mỗi bảng serving phải trả lời đúng một nhóm câu hỏi analyst:

- traffic theo giờ/ngày
- heatmap lịch sử
- queue performance
- zone occupancy
- dwell summary

### 1.3 Grain phải rõ

Mỗi bảng phải nói rõ:

```text
1 row đại diện cho cái gì
```

Ví dụ:

- `gold_serving_traffic_hourly`: `store + camera + hour`
- `gold_serving_heatmap_tile_5min`: `store + camera + 5-minute bucket + tile`
- `gold_serving_queue_hourly`: `store + camera + queue zone + hour`

### 1.4 Không ép mọi thứ thành SQL-only

Serving tables có thể được build bằng:

- Flink batch job
- Trino SQL
- Spark

SQL file chỉ là một cách định nghĩa logic, không phải kiến trúc riêng.

## 2. Phân nhóm Gold cho project này

### Gold facts

Đây là các bảng business fact / aggregate gần realtime:

- `gold_track_summary_v2`
- `gold_queue_sessions_v2`
- `gold_camera_hourly_metrics`
- `gold_camera_daily_metrics`
- `gold_camera_daily_dwell`
- `gold_alert_events`
- `gold_alerts`

Ghi chú:

- `gold_zone_minute_metrics` đã bị loại khỏi flow hiện tại, không còn là source chính thức
- `gold_alert_events` và `gold_alerts` là hai bảng khác semantics:
  - `gold_alert_events`: aggregate alert/density facts từ Flink dashboard job
  - `gold_alerts`: incident/clip-backed alert history đang được serving path sử dụng

### Gold serving

Đây là các bảng query-ready cho analyst:

- hourly traffic serving
- daily traffic serving
- heatmap serving
- queue serving
- zone serving
- alert serving
- executive daily serving

## 3. Serving tables nên lấy từ đâu

Rule chung:

- ưu tiên build từ `Gold facts`
- chỉ đọc `Silver` trực tiếp khi serving logic thật sự cần grain detection-level

Ví dụ:

`Traffic serving`:
- source tốt: `gold_camera_hourly_metrics`, `gold_camera_daily_metrics`

`Queue serving`:
- source tốt: `gold_queue_sessions_v2`

`Zone serving`:
- source tốt: `silver_detections_v2`
- lý do: `gold_zone_minute_metrics` đã bị loại khỏi flow hiện tại, còn zone serving hiện đang build trực tiếp từ detection-level source đã enrich zone

`Dwell serving`:
- source tốt: `gold_track_summary_v2`, `gold_camera_daily_dwell`

`Heatmap serving`:
- có thể cần đọc `silver_detections_v2` nếu Gold facts hiện chưa có heatmap aggregate

`Alert serving`:
- source đúng cho serving/history path hiện tại: `gold_alerts`
- `gold_alert_events` chỉ nên dùng khi cần density/event aggregate riêng

## 4. Khi nào Silver -> Gold serving là hợp lý

Không phải mọi bảng serving đều bắt buộc phải đi:

```text
Silver -> Gold facts -> Gold serving
```

Một số bảng có thể đi:

```text
Silver -> Gold serving
```

nếu:

- Gold facts trung gian chưa tồn tại
- grain serving rất sát với Silver
- thêm một bảng Gold facts trung gian không tạo giá trị rõ

Ví dụ heatmap lịch sử có thể đi thẳng từ `silver_detections_v2` sang `gold_serving_heatmap_*`.

## 5. Bảng serving đề xuất cho project

### Traffic

- `gold_serving_traffic_hourly`
- `gold_serving_traffic_daily`

### Queue

- `gold_serving_queue_hourly`
- `gold_serving_queue_daily`

### Zone

- `gold_serving_zone_hourly`
- `gold_serving_zone_daily`

### Heatmap

- `gold_serving_heatmap_tile_5min`
- `gold_serving_heatmap_tile_hour`

### Dwell / Executive

- `gold_serving_dwell_daily`
- `gold_serving_executive_daily`

### Alert

- `gold_serving_alert_hourly`
- `gold_serving_alert_daily`

## 6. Naming rule

Để giữ taxonomy sạch, có hai cách hợp lệ:

1. giữ cùng schema `rva` và dùng prefix:

```text
gold_serving_traffic_hourly
gold_serving_queue_daily
```

2. hoặc dùng schema riêng chỉ để tách logical namespace, nhưng vẫn document rõ đây là Gold:

```text
lakehouse.rva_gold_serving.*
```

Implementation hiện tại dùng schema `lakehouse.rva_gold_serving` và thư mục `services/gold_serving/`. Đây là physical implementation của Gold serving, không phải một tier medallion mới.

## 7. Điều không nên làm

- không nói `Bronze / Silver / Gold / Mart` như 4 tier ngang hàng
- không biến serving tables thành một hệ riêng tách khỏi Gold
- không để dashboard query Silver mặc định nếu Gold facts/serving đã có

## 8. Kết luận

Từ góc nhìn modeling, project nên chốt:

```text
Bronze
Silver
Gold
  - Gold facts
  - Gold serving
```

Đó là cách sạch hơn, đúng medallion hơn, và vẫn giữ được chỗ cho batch serving sau này.
