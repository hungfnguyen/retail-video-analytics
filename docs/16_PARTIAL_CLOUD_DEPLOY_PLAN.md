# 16. Partial Cloud Deploy Plan

> Mục tiêu tài liệu này: mô tả kế hoạch đưa **một phần hệ thống Retail Video Analytics lên cloud**, trong khi **Vision Service vẫn chạy trên máy local**. Đây là phương án thực dụng để phục vụ dev, demo và thuyết trình đồ án với chi phí AWS thấp hơn nhiều so với việc đưa toàn bộ pipeline, đặc biệt là inference Vision, lên cloud.

---

## 1. Mục tiêu triển khai

Phạm vi triển khai cloud trong giai đoạn này:

- giữ `Vision Service` chạy trên máy local của người dùng;
- deploy các service còn lại lên AWS;
- ưu tiên môi trường `dev/demo`, không phải production HA;
- tối ưu theo ràng buộc ngân sách credits AWS hiện có.

Mục tiêu không bao gồm:

- đưa YOLO / tracking / inference GPU lên cloud;
- tách nhiều EC2 theo từng lớp service;
- tối ưu HA, autoscaling, backup/DR hoàn chỉnh;
- triển khai production-grade security/compliance đầy đủ.

---

## 2. Phạm vi hệ thống sẽ deploy

### 2.1. Chạy local

Các thành phần giữ trên máy local:

- `services/vision/`
- model weights `YOLO11`
- camera/video input
- annotated live frames ghi local

Lý do:

- inference Vision là phần nặng nhất;
- local machine hiện có GPU/NVIDIA phù hợp hơn EC2 giá rẻ;
- nếu đưa Vision lên cloud sẽ đẩy chi phí EC2 tăng mạnh;
- pipeline còn lại có thể vận hành trên CPU cloud.

### 2.2. Chạy trên AWS

Các thành phần dự kiến đưa lên cloud:

- `Pulsar`
- `Flink JobManager`
- `Flink TaskManager`
- `Redis`
- `Iceberg REST`
- `Trino`
- `FastAPI`
- `Frontend` hoặc static frontend bundle

Storage cloud:

- `AWS S3` cho lakehouse
- `AWS EBS` cho EC2 root/data volume

---

## 3. Kiến trúc mục tiêu

```text
Local machine
  ├── Vision Service
  ├── YOLO / tracking
  └── Pulsar producer
          │
          │ Internet
          ▼
AWS EC2
  ├── Pulsar broker
  ├── Flink cluster (JM/TM)
  ├── Redis
  ├── Iceberg REST
  ├── Trino
  ├── FastAPI
  └── Frontend / static serving
          │
          ▼
AWS S3
  ├── lakehouse/
  ├── frames/
  └── clips/
```

Triết lý:

- compute CV giữ ở edge/local;
- cloud chịu phần stream processing, serving, query và storage;
- hạn chế số máy để giữ chi phí thấp.

---

## 4. Mô hình hạ tầng đề xuất

## 4.1. Giai đoạn đầu: 1 EC2 duy nhất

Phương án khuyến nghị đầu tiên:

- `1 EC2` duy nhất
- tất cả service backend chạy bằng `docker compose`
- `Vision` local kết nối ra cloud qua public endpoint

Lý do:

- đơn giản nhất để vận hành;
- dễ debug;
- chi phí thấp nhất;
- phù hợp cho đồ án và demo ngắn hạn.

Nhược điểm:

- single point of failure;
- tài nguyên CPU/RAM dễ tranh chấp;
- không đẹp cho production.

## 4.2. Chưa nên làm ở giai đoạn này

Chưa cần:

- tách riêng EC2 cho Trino/Flink/Pulsar;
- dùng Kubernetes/EKS;
- dùng MSK/ElastiCache/EMR/managed services;
- load balancer / auto scaling / multi-AZ.

---

## 5. Sizing EC2 thực dụng

Với stack hiện tại của project, nếu `Vision` chạy local thì bottleneck cloud chủ yếu là:

- Java processes: `Flink`, `Trino`, `Pulsar`
- memory pressure từ query analytics / checkpoints
- Docker overhead trên một host duy nhất

### Option khuyến nghị

#### Option A — 16 GB RAM

Phù hợp khi:

- chỉ dev/demo;
- concurrency thấp;
- không mở nhiều query nặng cùng lúc;
- Vision không chạy trên chính EC2.

Đánh giá:

- khả thi;
- là mức vào cửa hợp lý nhất;
- có thể cần giảm memory config của Trino/Flink/Pulsar.

#### Option B — 32 GB RAM

Phù hợp khi:

- muốn môi trường cloud dễ thở hơn;
- chạy demo analyst dashboard + queue analytics + alert pipeline mượt hơn;
- muốn giảm nguy cơ OOM khi query Trino/Flink hoạt động song song.

Đánh giá:

- phù hợp hơn cho project này;
- vẫn còn trong khả năng nếu chỉ bật khi cần dùng;
- là phương án mình nghiêng về hơn cho demo chính thức.

### Không khuyến nghị lúc này

#### 8 GB RAM

Không khuyến nghị cho full stack cloud của repo này vì:

- `Pulsar + Flink + Trino + Redis + API` trên cùng máy sẽ rất chật;
- query analytics rất dễ chạm trần RAM;
- độ ổn định kém.

---

## 6. Ước lượng chi phí ở mức thực dụng

Ràng buộc đầu vào hiện tại:

- credits còn khoảng `~$99`
- có khả năng cộng thêm khoảng `~$100`
- thời gian sử dụng dự kiến: khoảng `20 ngày`
- không chạy liên tục, chỉ bật lúc dev/demo

### Kết luận chi phí

Nếu chỉ bật khi dùng:

- `16 GB RAM` là **khả thi cao**
- `32 GB RAM` cũng **khả thi**, nếu không để chạy 24/7

Nếu chạy liên tục ngày đêm:

- credit sẽ bị ăn khá nhanh;
- phương án 32GB không còn đẹp.

### Kết luận vận hành

Nên áp dụng nguyên tắc:

- bật EC2 khi dev/demo;
- tắt EC2 khi không dùng;
- dùng cùng một máy cho toàn bộ backend cloud;
- giữ S3 là nơi lưu trữ lâu dài, không để EC2 chạy nền vô ích.

---

## 7. Phân bổ service trên EC2

### 7.1. Chạy bằng Docker Compose

Khuyến nghị giữ mô hình gần với local nhất:

- `pulsar-broker`
- `redis`
- `flink-jobmanager`
- `flink-taskmanager`
- `iceberg-rest`
- `trino`

Host-level có thể chạy:

- `FastAPI`
- `frontend preview` hoặc web server static

Hoặc cũng có thể đưa cả API/frontend vào compose để đồng nhất.

### 7.2. Ưu tiên đơn giản hơn tối ưu

Ở giai đoạn này nên chọn:

- ít moving parts hơn;
- ít khác biệt hơn so với local;
- dễ rollback hơn khi demo lỗi.

---

## 8. Network và kết nối local -> cloud

### 8.1. Cách Vision local kết nối cloud

Vision local sẽ publish trực tiếp tới:

- `Pulsar` trên EC2 public IP / domain

API/Frontend phục vụ qua:

- public IP hoặc domain của EC2

### 8.2. Security tối thiểu

Nên có ngay từ đầu:

- security group chỉ mở đúng port cần dùng
- giới hạn truy cập admin ports
- không public Trino/Flink/Pulsar admin UI ra Internet nếu không cần
- dùng `.env` rõ ràng cho secrets

Port public tối thiểu nên cân nhắc:

- `8000` cho FastAPI
- `5173` hoặc web server port cho frontend nếu cần
- `6650` cho Pulsar client nếu Vision local bắn trực tiếp

Port nội bộ nên hạn chế public:

- `8081` Flink UI
- `8083` Trino
- `8181` Iceberg REST
- Redis

Nếu cần admin UI, ưu tiên:

- chỉ mở tạm thời từ IP cá nhân;
- hoặc SSH tunnel.

---

## 9. Trình tự triển khai đề xuất

## Phase A — Chuẩn bị hạ tầng cloud tối thiểu

1. Tạo `EC2` 16GB hoặc 32GB.
2. Gắn `EBS` đủ dùng.
3. Gán IAM role nếu cần truy cập S3.
4. Cấu hình security group.
5. Cài Docker + Docker Compose.

Output mong đợi:

- EC2 truy cập được;
- pull image / build container thành công;
- S3 credentials hoạt động.

## Phase B — Đưa backend stack lên EC2

1. Copy source code hoặc pull từ git.
2. Chuẩn bị `.env` production-lite.
3. Chạy `docker compose up -d`.
4. Verify:
   - Pulsar up
   - Redis up
   - Flink jobs submit được
   - Trino query được

Output mong đợi:

- cloud backend stack sống độc lập;
- `bronze/silver/gold` jobs chạy được trên cloud.

## Phase C — Nối Vision local vào cloud

1. Đổi `PULSAR_SERVICE_URL` của Vision local trỏ tới EC2.
2. Chạy Vision local.
3. Kiểm tra event flow:
   - Vision -> Pulsar
   - Pulsar -> Flink
   - Flink -> Redis / Iceberg

Output mong đợi:

- live page có data;
- Bronze/Silver có row mới từ local Vision.

## Phase D — Demo hardening

1. Add restart policy
2. Add log rotation
3. Add simple healthcheck script
4. Add startup/shutdown checklist
5. Add warm-up checklist trước demo

Output mong đợi:

- có thể bật stack trước buổi demo;
- xác minh nhanh toàn bộ pipeline.

---

## 10. Cấu hình runtime nên ưu tiên

Vì đây là môi trường tiết kiệm chi phí, nên:

- ưu tiên analyst API cache
- bật Iceberg maintenance định kỳ
- tránh query analyst cold path quá thường xuyên
- không để nhiều browser/tab analytics reload liên tục

Rất quan trọng:

- `Phase 1.1 API cache` của lakehouse nên được đưa vào cloud trước;
- nếu không, Trino single-node trên EC2 sẽ rất dễ chậm.

---

## 11. Rủi ro chính

## 11.1. EC2 RAM không đủ

Dấu hiệu:

- container restart
- Trino chậm/OOM
- Flink fail checkpoint

Giảm rủi ro:

- bắt đầu với 16GB nếu muốn tiết kiệm;
- nâng 32GB nếu analyst query nặng;
- giảm concurrency và giới hạn memory config.

## 11.2. Vision local -> cloud network không ổn định

Dấu hiệu:

- Vision publish timeout
- backlog tăng
- metadata lag tăng

Giảm rủi ro:

- test bằng video file trước;
- ưu tiên đường truyền ổn định khi demo;
- có mode fallback demo recorded.

## 11.3. Credits cạn nhanh hơn dự tính

Nguyên nhân:

- quên tắt EC2
- để public IP tồn tại lâu
- để stack chạy cả ngày mà không dùng

Giảm rủi ro:

- bật/tắt theo phiên làm việc;
- theo dõi Cost Explorer / Billing;
- giữ 1 checklist shutdown sau mỗi buổi dev/demo.

---

## 12. Khuyến nghị chốt

Phương án nên chọn ngay bây giờ:

- `Vision local`
- `1 EC2` cho toàn bộ backend cloud
- ưu tiên `16GB RAM` nếu muốn vào nhanh, `32GB RAM` nếu muốn demo analyst ổn định hơn
- dùng `docker compose`
- chỉ bật khi dev/demo

Đây là phương án **khả thi về ngân sách**, **đủ tốt cho đồ án**, và **ít rủi ro triển khai nhất**.

---

## 13. Công việc nên làm sau tài liệu này

1. Tạo checklist `cloud bootstrap`.
2. Tạo `.env.cloud.example`.
3. Tạo `docker-compose.cloud.yml` hoặc profile cloud.
4. Tạo script verify:
   - container status
   - Flink jobs
   - Trino query
   - Redis keys
   - API health
5. Quay lại tiếp tục task `lakehouse Phase 1`.

