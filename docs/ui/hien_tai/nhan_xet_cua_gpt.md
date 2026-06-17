Mình xem kỹ cả 3 màn hình rồi. Nếu đứng ở góc nhìn **Product Architect + Data Architect** thì mình thấy vấn đề lớn nhất không phải UI xấu, mà là **information architecture đang chưa đúng với đối tượng người dùng**.

---

# 1. Live Monitor (Realtime)

Màn này thực ra ổn nhất.

## Điểm tốt

Ngay khi mở lên người dùng thấy:

```text
Current count
Queue length
Longest wait
Active alerts
```

=> đúng mindset của Store Manager.

Sau đó là:

```text
Camera
Bounding box
Queue zones
Alerts
```

=> phù hợp cho realtime operation.

---

## Vấn đề

Hiện tại camera đang chiếm khoảng:

```text
70-80% màn hình
```

trong khi analytics realtime chỉ chiếm:

```text
20-30%
```

Nếu đây là:

```text
Security System
```

thì đúng.

Nhưng đây là:

```text
Retail Analytics
```

thì hơi ngược.

---

### Gợi ý

Layout nên kiểu:

```text
┌───────────────────────────────┐
│ KPI Bar                       │
├──────────────┬────────────────┤
│ Camera       │ Active Alerts  │
│              │ Queue Status   │
│              │ Zone Status    │
│              │ Recommendations│
└──────────────┴────────────────┘
```

Ví dụ:

```text
Checkout Queue 03
Wait: 2m07s
Status: Critical

Recommendation:
Open another checkout counter
```

Cái này mới đúng "analytics".

---

# 2. Heatmap

Màn này cũng khá ổn.

Thực ra heatmap rất khó làm đẹp.

Hiện tại:

```text
Camera background
+
Heatmap overlay
```

là đủ.

---

## Thiếu thứ quan trọng nhất

Hiện tại heatmap chỉ là:

```text
ảnh đẹp
```

nhưng chưa có insight.

Store manager nhìn xong sẽ hỏi:

> rồi sao?

---

Ví dụ nên thêm panel bên phải:

```text
Top Hot Zones

1. Checkout Queue 03
   35% traffic

2. Entrance
   22%

3. Beverage Shelf
   18%
```

---

Hoặc:

```text
Most congested area
Average dwell
Peak occupancy
```

Heatmap lúc đó mới có business value.

---

# 3. Analytics (màn có vấn đề nhất)

Đây là phần mình thấy cần redesign gần như toàn bộ.

---

## Vấn đề 1

Bạn đang trộn:

```text
Traffic Analytics
Queue Analytics
Alert Analytics
```

vào cùng 1 page.

---

Hiện tại flow:

```text
Traffic KPIs

Chart

Table

Queue KPIs

Queue table

Alert section
```

Rất dài.

User phải scroll.

---

Theo BI chuẩn:

### Option A

Tách thành:

```text
Overview
Queue Analytics
Heatmap Analytics
Alert Analytics
```

---

### Option B

1 page nhưng dùng tabs

```text
Overview | Queue | Alerts
```

---

# Vấn đề 2: Filter cực kỳ yếu

Đây là cái mình thấy không hợp lý nhất.

Hiện tại:

```text
1d
7d
14d
30d

Last 7 days
```

---

User sẽ không hiểu:

```text
7d khác gì Last 7 days?
```

---

Theo chuẩn BI dashboard:

Nên có:

```text
Store
Camera
Zone
Date Range
```

---

Ví dụ:

```text
Store      [Store A ▼]

Camera     [All Cameras ▼]

Zone       [All Zones ▼]

Date Range [Last 7 Days ▼]
```

---

Sau đó:

```text
Today
Yesterday
Last 7 days
Last 30 days
Custom
```

---

Giống:

```text
Power BI
Tableau
Grafana
Superset
```

---

# Vấn đề 3: KPI không phải KPI business

Hiện tại bạn show:

```text
Total detections
Avg confidence
Busiest camera
```

---

Đây là KPI của:

```text
Computer Vision Engineer
```

không phải:

```text
Store Manager
```

---

Manager quan tâm:

```text
Foot Traffic

Peak Hour

Avg Dwell Time

Avg Queue Wait

Queue SLA Violation

Alert Count

Zone Utilization
```

---

Ngược lại:

```text
Confidence
Detection count
Camera share
```

nên đưa vào:

```text
System page
```

hoặc

```text
Technical page
```

---

# Vấn đề 4: Daily Summary table không có giá trị

Hiện tại:

```text
Date
Detections
Peak
Avg dwell
Avg conf
```

---

Manager sẽ không dùng.

---

Nên đổi thành:

```text
Date
Visitors
Peak Hour
Avg Queue Wait
Longest Wait
Alerts
```

---

# Vấn đề 5: Busiest Camera

Cái card này mình nghĩ nên bỏ.

Hiện tại:

```text
Busiest camera = cam_01
```

không mang ý nghĩa business.

---

Nên đổi thành:

```text
Most Crowded Zone

Checkout Queue 03
```

hoặc

```text
Peak Occupancy

23 people
```

---

# Vấn đề 6: Analytics chưa phản ánh kiến trúc Lakehouse

Đây là điểm rất hay liên quan tới đồ án của bạn.

Bạn đang có:

```text
Bronze
Silver
Gold
```

---

Nhưng UI lại đang show:

```text
detections
confidence
camera
```

=> Silver thinking.

---

Trong Lakehouse chuẩn:

## Silver

Là technical facts

```text
detections
tracks
events
```

---

## Gold

Là business metrics

```text
traffic
queue
occupancy
alerts
conversion
zone utilization
```

---

Analytics page nên gần như chỉ đọc:

```text
gold_traffic_daily
gold_queue_metrics
gold_alert_summary
```

---

User không nên thấy:

```text
detections
confidence
camera share
```

ở dashboard chính.

---

# Nếu là mình redesign

Sidebar:

```text
Live Monitor
Analytics
Heatmap
System
```

giữ nguyên.

---

Analytics:

```text
Overview
```

KPI:

```text
Visitors Today
Peak Hour
Avg Queue Wait
Active Alerts
```

Chart:

```text
Traffic Trend
Queue Trend
```

---

Tab 2:

```text
Queue Analytics
```

```text
Queue Distribution
Wait Time Trend
SLA Violations
Worst Queue Zones
```

---

Tab 3:

```text
Alert Analytics
```

```text
Alert Types
Alert Frequency
Incident History
```

---

Tab 4:

```text
Zone Analytics
```

```text
Occupancy
Dwell
Heatmap Summary
```

---

Đánh giá tổng thể:

| Màn hình  | Điểm   |
| --------- | ------ |
| Live      | 8/10   |
| Heatmap   | 7.5/10 |
| Analytics | 5.5/10 |

Lý do Analytics thấp là vì nó đang phản ánh cách hệ thống xử lý dữ liệu (detections, confidence, camera) hơn là phản ánh insight kinh doanh của một Retail Analytics Platform. Đây cũng là chỗ mình nghĩ nên đầu tư redesign mạnh nhất trước khi làm thêm feature mới.
