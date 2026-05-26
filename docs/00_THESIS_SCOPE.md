# Thesis Scope

## 1. Bối cảnh

Camera trong siêu thị tạo ra nguồn dữ liệu giàu thông tin về mật độ khách, luồng di chuyển, thời điểm cao điểm và tình trạng vận hành. Tuy nhiên dữ liệu video thô có kích thước lớn, khó truy vấn trực tiếp và không phù hợp để đưa toàn bộ vào hệ thống phân tích.

Đồ án này tiếp cận bài toán theo hướng Data Engineering: biến video thành các event metadata có schema rõ ràng, đưa vào streaming pipeline, lưu vào lakehouse và phục vụ realtime dashboard lẫn phân tích lịch sử.

## 2. Tên đề tài đề xuất

**Xây dựng hệ thống xử lý dữ liệu streaming từ video camera siêu thị phục vụ phân tích mật độ khách hàng theo thời gian thực và lịch sử.**

Tên tiếng Anh:

**Building a Streaming Data Platform for Retail Video Analytics with Real-time Heatmap and Lakehouse Analytics.**

## 3. Mục tiêu chính

1. Thiết kế và triển khai pipeline thu nhận dữ liệu từ camera hoặc video file.
2. Trích xuất metadata bằng mô hình Computer Vision gồm person detection và tracking.
3. Đẩy detection events vào message broker theo contract có version.
4. Xử lý realtime bằng stream processing để tính live count, heatmap và cảnh báo mật độ.
5. Lưu dữ liệu lịch sử vào lakehouse theo kiến trúc Bronze, Silver, Gold.
6. Cung cấp dashboard realtime và dashboard phân tích lịch sử.
7. Đánh giá hệ thống theo latency, throughput, data quality và khả năng phục hồi lỗi.

## 4. Câu hỏi kỹ thuật của đồ án

| Câu hỏi | Nội dung cần trả lời |
|---|---|
| Q1 | Làm thế nào biến video thành event stream có schema ổn định và truy vết được? |
| Q2 | Làm thế nào tách realtime serving và historical analytics để mỗi nhánh tối ưu đúng mục tiêu? |
| Q3 | Làm thế nào đảm bảo dữ liệu trễ, trùng lặp hoặc lỗi schema không phá vỡ pipeline? |
| Q4 | Làm thế nào tổ chức lakehouse để truy vấn theo camera, thời gian, track và heatmap hiệu quả? |
| Q5 | Làm thế nào đánh giá một data pipeline video analytics ngoài độ chính xác model CV? |

## 5. Phạm vi

### Trong phạm vi

- Đọc video từ file hoặc RTSP camera.
- Detect người bằng YOLO11 hoặc model YOLO tương đương.
- Tracking bằng BoTSORT hoặc tracker tương đương.
- Sinh detection frame event theo schema versioned.
- Ingest vào Apache Pulsar.
- Xử lý streaming bằng Apache Flink.
- Lưu realtime state trong Redis.
- Lưu operational metadata trong PostgreSQL.
- Lưu analytical data trong Apache Iceberg trên object storage.
- Truy vấn bằng Trino.
- Dashboard bằng Streamlit và Grafana.
- Monitoring bằng Prometheus/Grafana.
- Demo chạy được bằng Docker Compose.

### Ngoài phạm vi

- Nhận diện danh tính cá nhân hoặc face recognition.
- Theo dõi khách qua nhiều camera bằng re-identification nâng cao.
- Tối ưu model CV cấp production như TensorRT, Triton hoặc quantization chuyên sâu.
- Xây dựng mobile app.
- Triển khai Kubernetes production.
- Xử lý thanh toán, POS hoặc dữ liệu giao dịch bán hàng.

## 6. Đối tượng người dùng

| Persona | Nhu cầu |
|---|---|
| Quản lý cửa hàng | Xem lượng khách theo giờ, ngày, khu vực đông, thời điểm cao điểm |
| Nhân sự vận hành | Theo dõi live camera, cảnh báo đông bất thường, camera offline |
| Data analyst | Truy vấn dữ liệu lịch sử, so sánh ngày, xuất số liệu |
| Kỹ sư vận hành hệ thống | Theo dõi health, lag, throughput, lỗi pipeline |

## 7. Đầu ra của hệ thống

| Đầu ra | Mô tả |
|---|---|
| Live heatmap | Bản đồ mật độ khách theo từng camera gần realtime |
| Current count | Số người hiện diện theo camera |
| Density alert | Cảnh báo khi mật độ vượt ngưỡng |
| Track lifecycle | Sự kiện track bắt đầu, kết thúc, thời lượng xuất hiện |
| Historical metrics | Tổng lượt track, peak count, heatmap theo phút/giờ/ngày |
| System metrics | FPS, broker lag, Flink checkpoint, Redis/PostgreSQL health |

## 8. Tiêu chí thành công

| Nhóm | Tiêu chí |
|---|---|
| Chức năng | Pipeline chạy end-to-end từ video đến dashboard |
| Realtime | Live metrics cập nhật trong khoảng 1 đến 3 giây ở demo local |
| Lakehouse | Dữ liệu được ghi vào Bronze, Silver, Gold và truy vấn được bằng Trino |
| Data quality | Có validation, deduplication, rule kiểm tra timestamp, bbox, confidence |
| Reliability | Restart service không làm mất hoàn toàn khả năng phục hồi pipeline |
| Observability | Có dashboard hoặc log thể hiện throughput, lag, error rate |
| Thesis quality | Giải thích được trade-off kiến trúc, không chỉ mô tả code |

## 9. Giả định triển khai

- Demo có thể dùng video file thay cho RTSP camera thật.
- Một camera tương ứng một `camera_id` ổn định.
- Detection class chính là `person`.
- Track ID chỉ đảm bảo duy nhất trong phạm vi một camera và một khoảng thời gian chạy tracker.
- Hệ thống không lưu toàn bộ video raw vào lakehouse.
- Sampled frame được lưu để minh họa event, không phải nguồn dữ liệu phân tích chính.

## 10. Định hướng báo cáo tốt nghiệp

Báo cáo nên nhấn mạnh các nội dung Data Engineering sau:

1. Event-driven architecture cho dữ liệu video metadata.
2. Streaming processing với event time, watermark, window, state.
3. Lakehouse design với schema evolution, partitioning, compaction.
4. Serving layer tách realtime state và historical analytics.
5. Data quality và observability.
6. Đánh giá latency, throughput, completeness, duplicate rate và recovery.
