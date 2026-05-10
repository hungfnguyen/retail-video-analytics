# Refactor Strategy: Giữ E2E Tiểu Luận, Sau Đó Upgrade Đồ Án

## 1. Bối Cảnh

Repo hiện tại vẫn là codebase của tiểu luận chuyên ngành. Pipeline đang chạy theo hướng:

```text
Vision AI
  -> Pulsar
  -> Flink Bronze/Silver/Gold
  -> Iceberg on MinIO
  -> Trino
  -> Grafana
```

Bộ tài liệu mới trong `docs/00` đến `docs/09` mô tả kiến trúc mục tiêu cho đồ án tốt nghiệp Data Engineering. Kiến trúc mục tiêu lớn hơn code hiện tại vì có thêm realtime serving path, operational storage, API, Streamlit, data quality, evaluation và multi-camera processing.

Vì vậy không nên vừa refactor structure vừa đổi kiến trúc nghiệp vụ trong cùng một bước.

## 2. Chiến Lược Hai Pha

### Phase 1: Refactor Structure, Giữ Behavior Cũ

Mục tiêu của phase 1 là chuyển codebase hiện tại sang cấu trúc sạch hơn, phù hợp để phát triển đồ án tốt nghiệp về sau, nhưng vẫn giữ E2E demo tiểu luận chuyên ngành chạy được.

Nguyên tắc:

- Không đổi business logic chính.
- Không đổi event payload hiện tại nếu chưa cần.
- Không đổi tên Pulsar topic.
- Không đổi tên bảng Iceberg đang được Grafana query.
- Không thêm Redis/PostgreSQL/FastAPI/Streamlit trong cùng bước refactor nếu chưa cần.
- Sau refactor, demo cũ vẫn phải chạy end-to-end.

Pipeline cần giữ:

```text
Vision -> Pulsar -> Flink -> Iceberg/MinIO -> Trino -> Grafana
```

Các contract cần giữ:

| Thành phần | Giữ nguyên trong Phase 1 |
|---|---|
| Pulsar topic | `persistent://retail/metadata/events` |
| Bronze table | `lakehouse.rva.bronze_raw` |
| Silver table | `lakehouse.rva.silver_detections` |
| Gold table | `lakehouse.rva.gold_track_summary` |
| Dashboard | Grafana query qua Trino |
| Vision input | Video file hoặc camera source hiện tại |

### Phase 2: Upgrade Lên Kiến Trúc Đồ Án Tốt Nghiệp

Sau khi structure mới ổn định và demo cũ vẫn chạy, mới bắt đầu upgrade từng phần theo kiến trúc đồ án tốt nghiệp.

Các nâng cấp chính:

- Chuẩn hóa event contract và thêm `event_id`.
- Thêm data quality validation, DLQ và quality metrics.
- Thêm Redis realtime path cho live count, heatmap, alerts.
- Thêm PostgreSQL cho operational metadata, track lifecycle, alert history.
- Thêm FastAPI serving layer.
- Thêm Streamlit live dashboard.
- Thêm sampled frame storage.
- Thêm multi-camera `CameraManager` và `CameraWorker`.
- Thêm test suite và evaluation scripts.

## 3. Lý Do Không Upgrade Ngay

Nếu đổi structure, đổi event schema, đổi storage, thêm realtime path và thêm dashboard mới cùng lúc, rủi ro rất cao:

- Khó biết lỗi đến từ refactor hay feature mới.
- Flink jobs dễ vỡ vì schema/table path thay đổi.
- Grafana query có thể mất data.
- Demo cũ bị hỏng trong khi feature mới chưa hoàn thành.
- Không có baseline để so sánh correctness.

Do đó phase 1 phải là một refactor có kiểm soát: đổi cách tổ chức code, nhưng giữ hành vi hệ thống.

## 4. Structure Mục Tiêu Cho Phase 1

Structure đề xuất:

```text
retail-video-analytics/
├── services/
│   ├── vision/              # move từ vision/
│   └── flink-jobs/          # move từ flink-jobs/java/
├── infrastructure/
│   ├── pulsar/
│   ├── flink/
│   ├── minio/
│   ├── trino/
│   └── grafana/
├── scripts/
│   └── replay_jsonl_to_pulsar.py
├── configs/
│   └── .env.example
├── docs/
├── notebooks/
├── docker-compose.yml
├── setup.txt
└── README.md
```

Giai đoạn sau có thể tiếp tục tiến đến monorepo đầy đủ:

```text
packages/
  rva-core/
  rva-messaging/
  rva-storage/

services/
  vision/
  flink-jobs/
  api/
  streamlit/
```

Nhưng trong phase 1 chưa bắt buộc tạo package nếu code chưa dùng đến.

## 5. Những Việc Nên Làm Trong Phase 1

1. Move code theo structure mới.
2. Cập nhật import path cho Vision.
3. Cập nhật Dockerfile và Docker Compose path.
4. Cập nhật script submit Flink job.
5. Cập nhật README root theo structure mới.
6. Giữ wrapper hoặc command tương thích nếu cần.
7. Thêm smoke test tối thiểu cho E2E cũ.
8. Dọn `.dockerignore`, `.gitignore`, `.env.example`.
9. Không xóa logic cũ cho đến khi demo mới chạy lại.

## 6. Những Việc Không Làm Trong Phase 1

- Không đổi topic sang namespace mới.
- Không đổi payload schema chính.
- Không đổi toàn bộ Flink job logic.
- Không thêm Redis realtime path.
- Không thêm PostgreSQL schema mới.
- Không thêm API/Streamlit.
- Không migrate MinIO sang GCS.
- Không tuyên bố unique visitors nếu vẫn chỉ có `track_id`.

## 7. Definition Of Done Cho Phase 1

Phase 1 hoàn thành khi:

- `docker compose up -d --build` khởi động infrastructure.
- Pulsar topic được tạo thành công.
- Vision service publish được metadata vào Pulsar.
- Bronze job ghi được vào `bronze_raw`.
- Silver job ghi được vào `silver_detections`.
- Gold job ghi được vào `gold_track_summary`.
- Trino query được các bảng trên.
- Grafana dashboard hiện dữ liệu như trước refactor.
- README mô tả đúng command mới.

## 8. Kiểm Tra Sau Refactor

Checklist:

```text
[ ] Docker Compose build thành công
[ ] Pulsar healthy
[ ] MinIO bucket warehouse tồn tại
[ ] Iceberg REST healthy
[ ] Flink JobManager và TaskManager healthy
[ ] Bronze job RUNNING
[ ] Silver job RUNNING
[ ] GoldTrackSummary job RUNNING
[ ] Vision chạy và gửi frame metadata
[ ] Trino SELECT COUNT(*) từ bronze/silver/gold chạy được
[ ] Grafana dashboard load được
```

## 9. Hướng Upgrade Sau Phase 1

Sau khi phase 1 ổn định, upgrade theo thứ tự:

1. Thêm `event_id` và chuẩn hóa event contract.
2. Thêm validation và DLQ trong Flink.
3. Thêm Gold minute/hour/heatmap tables.
4. Thêm Redis realtime state.
5. Thêm PostgreSQL operational metadata.
6. Thêm FastAPI serving layer.
7. Thêm Streamlit live monitor.
8. Thêm sampled frame storage.
9. Thêm multi-camera processing.
10. Thêm evaluation scripts và report metrics.

## 10. Kết Luận

Chiến lược đúng là:

```text
Refactor first, preserve old E2E demo.
Upgrade architecture second, one capability at a time.
```

Cách này giúp repo có nền móng sạch hơn mà không làm mất pipeline đã chạy được từ tiểu luận chuyên ngành.
