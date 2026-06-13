# Execution Rules For Lakehouse Phases

Mục đích của file này là chặn việc triển khai phase theo kiểu phình scope, verify vô tận, hoặc over-engineering vượt quá nhu cầu thật của project.

## 1. Nguyên tắc gốc

Mỗi phase phải có:

- mục tiêu ngắn, đo được
- điểm dừng rõ ràng
- output kiểm chứng tối thiểu
- giới hạn thời gian thực hiện

Nếu thiếu một trong bốn điều này thì **không được bắt đầu code**.

## 2. Rule về scope

Một phase chỉ được giải quyết **một lớp vấn đề chính**.

Ví dụ:

- `Phase cache` thì chỉ xử lý cache
- `Phase maintenance` thì chỉ xử lý optimize / cleanup / Airflow task wiring
- `Phase mart routing` thì chỉ xử lý query routing

Không được gộp trong một phase các việc kiểu:

- thiết kế mart
- viết refresh runner
- viết maintenance
- repoint API
- verify performance
- verify correctness

Nếu cần hơn 2 thay đổi lớn thì phải tách phase.

## 3. Rule về thời gian

Ngưỡng cứng:

- quá `30 phút` mà chưa ra kết quả rõ ràng: phải báo lại
- quá `45 phút` mà còn đang mở rộng scope: phải dừng
- quá `60 phút`: không được tiếp tục tự đào sâu, phải chốt trạng thái và xin quyết định mới

## 4. Rule về stop condition

Phải dừng ngay và báo người dùng nếu gặp một trong các dấu hiệu sau:

- đang phải thay đổi kiến trúc thay vì hoàn thành task ban đầu
- verify bắt đầu thành chuỗi retry dài
- một thay đổi kéo theo hơn 3 file logic mới và hơn 1 loại runtime mới
- kết quả thực tế bắt đầu mâu thuẫn với giả định thiết kế ban đầu
- cần benchmark / backfill / refresh nhiều lần mới biết đúng sai

Đây là dấu hiệu phase đã vượt scope.

## 5. Rule về verification

Verification cho mỗi phase chỉ được có tối đa 3 mức:

1. unit test hoặc lint
2. một lần chạy runtime thật
3. một lần kiểm tra output chính

Không được lặp đi lặp lại nhiều vòng verify chỉ để cố tối ưu thêm, trừ khi phase đó được định nghĩa rõ là phase benchmark hoặc tuning.

## 6. Rule về over-engineering

Nếu có hai hướng:

- hướng đơn giản giải quyết được nhu cầu hiện tại
- hướng đẹp kiến trúc hơn nhưng cần thêm nhiều abstraction, refresh logic, maintenance, hoặc audit

thì mặc định chọn **hướng đơn giản**.

Chỉ được chọn hướng phức tạp hơn khi có ít nhất một điều kiện:

- user yêu cầu rõ
- số liệu thực tế chứng minh hướng đơn giản không đủ
- phase đó là phase kiến trúc đã được chốt trước

## 7. Rule về escalation với user

Phải dừng và hỏi lại user trước khi đi tiếp nếu:

- chuẩn bị tạo một subsystem mới
- chuẩn bị thêm một thư mục service hoặc runner mới
- chuẩn bị thay đổi từ `fix` sang `redesign`
- chuẩn bị biến một phase thành nhiều phase con

Message cần nói rõ:

- mình đang định mở rộng sang đâu
- vì sao task hiện tại không còn nhỏ nữa
- nếu đi tiếp thì sẽ tốn thêm gì

## 8. Rule về deliverable

Khi kết thúc một phase, chỉ cần chốt 4 thứ:

1. đã làm gì
2. verify gì
3. còn risk gì
4. bước tiếp theo nhỏ nhất là gì

Không được biến phase report thành một thiết kế mới nếu user chưa yêu cầu.

## 9. Rule áp dụng riêng cho project này

Với repo `retail-video-analytics`, mặc định ưu tiên theo thứ tự:

1. correctness của live / analyst output
2. runtime ổn định
3. cache / routing / query simplification
4. maintenance tối thiểu
5. kiến trúc mart / orchestration nâng cao

Điều này có nghĩa là:

- nếu cache đủ cứu dashboard thì không nhảy ngay vào mart phức tạp
- nếu query routing đủ để giảm latency thì không vội thêm orchestration mới
- nếu một metric approximate làm số lệch nhiều thì không được cố ép productionize nó chỉ vì kiến trúc đẹp

## 10. Cách dùng file này

Trước mỗi phase mới, phải trả lời ngắn 5 câu:

1. phase này giải quyết đúng một vấn đề gì
2. output đo được là gì
3. tối đa làm trong bao lâu
4. stop condition là gì
5. nếu fail thì fallback đơn giản hơn là gì

Nếu không trả lời rõ được 5 câu này thì chưa bắt đầu phase.
