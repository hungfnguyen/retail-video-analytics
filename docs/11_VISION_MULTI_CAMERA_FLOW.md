# Vision Module — Multi-camera Processing Flow

## 1. Tổng quan

Vision module là entry point của hệ thống. Nó đọc video từ nhiều camera (RTSP hoặc video file), chạy YOLO detection + BoTSORT tracking, rồi publish kết quả lên Pulsar. Mỗi camera chạy trong **OS process riêng** để đảm bảo crash isolation.

```
Input                          Vision Module                       Output
──────                         ──────────────                      ──────
RTSP cam_01 ──┐          ┌── CameraWorker(cam_01) ──┐          ┌─ Pulsar
               │          │                          │          │
Video cam_02 ──┼──────────┼── CameraWorker(cam_02) ──┼──────────┼─ S3
               │          │                          │          │
RTSP cam_03 ──┘          └── CameraWorker(cam_03) ──┘          └─ PostgreSQL
```

## 2. Startup flow

### 2.1 CameraManager khởi động

```text
main.py chạy
  │
  ▼
CameraManager.__init__()
  │
  ├── 1. Load configs/cameras.yaml
  │      ├── cam_01: source_type=rtsp,    uri=rtsp://10.0.0.10:554/stream1
  │      ├── cam_02: source_type=video,   uri=data/videos/sample.mp4
  │      └── cam_03: source_type=rtsp,    uri=rtsp://10.0.0.11:554/stream1
  │
  ├── 2. Filter enabled=true
  │
  ├── 3. Với mỗi camera → spawn worker process
  │      CameraManager.spawn(cam_01) → PID 1001
  │      CameraManager.spawn(cam_02) → PID 1002
  │      CameraManager.spawn(cam_03) → PID 1003
  │
  └── 4. Enter health check loop (interval 10s)
```

### 2.2 CameraWorker khởi động

```text
CameraWorker.__init__(camera_config)
  │
  ├── 1. Tạo SourceReader dựa trên source_type
  │      if source_type == "rtsp":
  │          reader = RTSPReader(uri, buffer_size=1)
  │      elif source_type == "video_file":
  │          reader = VideoFileReader(path, realtime=True, loop=True)
  │
  ├── 2. Load YOLO model
  │      model = YOLO("detect/models/yolo11l.pt")
  │      model.to("cuda:0" if torch.cuda.is_available() else "cpu")
  │
  ├── 3. Khởi tạo BoTSORT tracker
  │      tracker = BoTSORT(model, conf_thres=0.4)
  │
  ├── 4. Khởi tạo output sinks
  │      pulsar = PulsarEmitter(url, topic)
  │      sampler = FrameSampler(s3_client, interval_sec=1)
  │      track_mgr = TrackLifecycleManager(postgres_client)
  │
  └── 5. Start pipeline loop
```

## 3. SourceReader — RTSP vs Video File

Cả 2 loại reader có cùng interface nhưng behavior khác nhau:

```python
class SourceReader(ABC):
    def start(self) -> None: ...       # Start reading thread
    def stop(self) -> None: ...        # Graceful shutdown
    @property
    def frame_queue(self) -> Queue: ... # queue.Queue(maxsize=2)
```

### 3.1 RTSPReader

```
┌──────────────────────────────────────────┐
│ Thread: RTSPReader                       │
│                                          │
│  cap = cv2.VideoCapture(rtsp_url,        │
│         cv2.CAP_FFMPEG)                  │
│  cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)     │
│                                          │
│  while running:                          │
│    ret, frame = cap.read()               │
│    if ret:                               │
│      queue.put(frame)   # thread-safe    │
│    else:                                 │
│      reconnect()        # blocking       │
└──────────────────────────────────────────┘

Đặc điểm:
  - Buffer nhỏ (1 frame) để tránh latency tích tụ
  - Reconnect tự động với exponential backoff 1→30s  
  - Không có end-of-stream (camera chạy vô hạn)
  - Frame rate theo camera tự nhiên
```

### 3.2 VideoFileReader

```
┌──────────────────────────────────────────┐
│ Thread: VideoFileReader                  │
│                                          │
│  cap = cv2.VideoCapture(file_path)       │
│  fps = cap.get(cv2.CAP_PROP_FPS)         │
│  t0 = time.perf_counter()                │
│                                          │
│  while running:                          │
│    ret, frame = cap.read()               │
│    if ret:                               │
│      if realtime_mode:                   │
│        due = t0 + seq/fps                │
│        if due > now: sleep(due - now)    │ ← giả lập FPS
│      queue.put(frame)                    │
│    else:  # EOF                          │
│      if loop:                            │
│        cap.set(cv2.CAP_PROP_POS_FRAMES,0)│ ← phát lại từ đầu
│        pipeline_run_id = uuid4()         │ ← run_id mới
│      else:                               │
│        break  → worker.exit()            │
└──────────────────────────────────────────┘

Đặc điểm:
  - Có thể giả lập realtime (sleep theo FPS) hoặc chạy max speed
  - Loop tự động khi hết video (demo)
  - Hoặc exit khi hết (backfill one-shot)
```

### 3.3 FrameQueue — Thread-safe

```python
import queue

# CameraWorker khởi tạo
frame_queue = queue.Queue(maxsize=2)

# RTSPReader thread (producer)
def read_loop():
    while running:
        frame = cap.read()
        if frame_queue.full():
            frame_queue.get()   # drop oldest
            drop_count += 1
        frame_queue.put(frame)  # add newest
        total_read += 1

# Pipeline main thread (consumer)  
def pipeline_loop():
    while running:
        frame = frame_queue.get()  # block nếu queue rỗng
        process_frame(frame)
```

> `queue.Queue` là thread-safe. Không dùng `list` thông thường vì 2 thread truy cập đồng thời sẽ gây race condition.

## 4. Pipeline — xử lý 1 frame

### 4.1 Detect: YOLO Inference

```
Input:  frame (BGR numpy array, 1920x1080)
Output: List[Detection]

model.predict(frame, conf=0.25, classes=[0])
  │
  ▼
Raw results từ YOLO:
┌──────┬───────┬──────────┬─────────────────┐
│ cls  │ conf  │ bbox     │ label           │
├──────┼───────┼──────────┼─────────────────┤
│ 0    │ 0.87  │ [x1,y1..]│ person ✅        │
│ 0    │ 0.22  │ [x1,y1..]│ person ❌ (conf) │  ← lọc bởi conf < 0.25
│ 2    │ 0.91  │ [x1,y1..]│ car ❌ (filter)  │  ← lọc bởi class != 0
│ 0    │ 0.95  │ [x1,y1..]│ person ✅        │
│ 0    │ 0.41  │ [x1,y1..]│ person ✅        │
└──────┴───────┴──────────┴─────────────────┘

After filter: 3 person detections
```

### 4.2 Track: BoTSORT

```
Input:  List[Detection] (3 detections)
Output: List[TrackedObject] (có track_id)

Tracker duy trì internal state:
┌──────────┬──────────────┬─────────┬──────────────────┐
│ track_id │ last_seen_ts │ status  │ n_frames_missed  │
├──────────┼──────────────┼─────────┼──────────────────┤
│ 41       │ 10:30:00.00  │ active  │ 0                │
│ 42       │ 10:30:00.08  │ active  │ 0                │
│ 43       │ 10:29:30.50  │ lost    │ 60 (> 30s timeout)│
└──────────┴──────────────┴─────────┴──────────────────┘

Kết quả matching:
  Detection A (conf=0.87) → IOU match track_41 → track_id=41
  Detection B (conf=0.95) → IOU match track_42 → track_id=42  
  Detection C (conf=0.41) → conf < 0.4 → FILTERED (Silver threshold)

  Track 43 → timeout 30s → emit track_end event

Output: 2 tracked objects (track_id=41, track_id=42)
```

### 4.3 Build: DetectionFrameEvent

```json
{
  "schema_version": "1.0",
  "pipeline_run_id": "abc123def456",
  "source": {
    "store_id": "store_001",
    "camera_id": "cam_01",
    "stream_id": "stream_01"
  },
  "frame_index": 1502,
  "capture_ts": "2026-05-09T10:30:00.123Z",
  "image_size": {"width": 1920, "height": 1080},
  "detections": [
    {
      "det_id": "1502-0",
      "class": "person",
      "class_id": 0,
      "conf": 0.87,
      "bbox": {"x1": 100, "y1": 200, "x2": 300, "y2": 620},
      "centroid": {"x": 200, "y": 410},
      "track_id": 41
    },
    {
      "det_id": "1502-1",
      "class": "person",
      "class_id": 0,
      "conf": 0.95,
      "bbox": {"x1": 500, "y1": 150, "x2": 650, "y2": 580},
      "centroid": {"x": 575, "y": 365},
      "track_id": 42
    }
  ],
  "runtime": {
    "model_name": "yolo11l",
    "tracker_type": "botsort"
  }
}
```

### 4.4 Publish: Pulsar + S3 + PostgreSQL

```
Build xong event
  │
  ├── PulsarEmitter.emit_frame(event)
  │     └── producer.send_async(payload)
  │           ├── OK → done
  │           └── FAIL → background retry (3 lần, backoff 0.5→1→2s)
  │                      Pipeline chính KHÔNG chờ
  │
  ├── FrameSampler.save(frame, frame_index)
  │     └── if frame_index % fps_target == 0:       ← mỗi 1 giây
  │           ThreadPoolExecutor.submit(upload_jpg)  ← async, không block
  │           key = "frames/{date}/{store}/{cam}/{hour}/{ts}_{idx}.jpg"
  │
  └── TrackLifecycleManager.update(tracked_objects)
        ├── track mới xuất hiện → INSERT track_start
        ├── track đang active → UPDATE position_sample (1s interval)
        └── track timeout >30s → INSERT track_end
```

## 5. Failure handling

### 5.1 Camera disconnect (RTSP)

```
Frame N:   cap.read() → ret=True ✅
Frame N+1: cap.read() → ret=False ❌

RTSPReader:
  disconnect_count++
  log WARNING: "cam_01: connection lost, reconnecting..."

  while not reconnected:
    delay = min(2^(attempt-1), 30)
    sleep(delay)
    cap.release()
    cap = VideoCapture(rtsp_url)
    ret, _ = cap.read()
  
  reconnect_success++
  log INFO: "cam_01: reconnected after N attempts (Xs)"

Impact:
  - FrameQueue rỗng → pipeline.get() block
  - KHÔNG crash, KHÔNG gửi dữ liệu rác
  - Camera khác vẫn chạy bình thường
  - Reconnect xong → pipeline tự resume
```

### 5.2 Worker crash

```
CameraWorker (PID 1001) crash do GPU OOM / segfault

CameraManager health check (10s interval):
  is_alive(PID 1001)? → False ❌
  
  log ERROR: "Worker cam_01 dead, restarting..."
  restart_count[cam_01]++
  backoff = min(2^(restart_count-1), 30)
  sleep(backoff)
  spawn CameraWorker(cam_01) → PID 1004
  
  log INFO: "Worker cam_01 restarted (pid=1004)"

Impact:
  - cam_02, cam_03 không bị ảnh hưởng
  - Tracker state bị reset (track_id bắt đầu lại từ 1)
  - pipeline_run_id mới
```

### 5.3 Pulsar unavailable

```
Pipeline xử lý xong frame → publisher.send_async() → timeout

DetectionPublisher:
  enter buffer mode (max 100 events)
  buffer[0] = event_42
  buffer[1] = event_43
  ...
  buffer[99] = event_141
  
  buffer đầy → event mới đến → drop OLDEST frame (giữ 100 mới nhất)
  
  background thread retry:
    attempt 1: sleep(0.5s) → send(buffer[0]) → FAIL
    attempt 2: sleep(1.0s) → send(buffer[0]) → FAIL
    attempt 3: sleep(2.0s) → send(buffer[0]) → FAIL
    → exhausted → log ERROR + metric failed_publish_total++
  
  Pulsar trở lại:
    drain buffer (batch 10 events/lần)
    → resume normal mode

Impact:
  - Pipeline chính vẫn chạy (không block)
  - Mất event nếu buffer đầy + Pulsar down quá lâu
  - S3 upload + track lifecycle vẫn hoạt động (độc lập với Pulsar)
```

### 5.4 S3 upload fail

```
FrameSampler.submit(upload_jpg)

ThreadPoolExecutor thread:
  s3.put_object(key, jpg_data) → timeout / connection error
  
  upload_fail_count++
  log WARNING: "Frame 500 upload failed, skipping"
  
  Không retry (frame sample là optional)
  Metadata đã publish lên Pulsar (pipeline chính không bị ảnh hưởng)
```

## 6. Health check & monitoring

```
CameraManager health loop (every 10s):

for each worker:
  if not is_alive(pid):
    restart worker
  
  metrics:
    fps_observed = frames_processed / (now - last_check)
    queue_size = frame_queue.qsize()
    drop_rate = drop_count / total_read
    
    if fps_observed < fps_target * 0.5:
      emit camera_fps_degraded alert
    
    if not is_alive(pid):
      emit camera_offline alert

emit to Prometheus:
  rva_vision_fps{camera="cam_01"} 24.8
  rva_vision_fps{camera="cam_02"} 29.9
  rva_vision_drop_count{camera="cam_01"} 42
  rva_vision_publish_latency_ms{camera="cam_01"} 15
  rva_vision_inference_latency_ms{camera="cam_01"} 85
```

## 7. Graceful shutdown

```
SIGTERM / SIGINT (Ctrl+C / docker stop)

CameraManager:
  1. signal_handler nhận SIGTERM
  2. for each worker:
       worker.terminate()          # gửi SIGTERM tới child process
       worker.join(timeout=10s)    # đợi worker cleanup
       if still alive:
         worker.kill()             # force kill sau timeout
  
  3. Close shared resources:
     - Pulsar client close
     - S3 client close
     - PostgreSQL pool close
  
  4. Flush logs
  5. Exit 0

CameraWorker (nhận SIGTERM từ cha):
  1. running = False               # dừng read loop
  2. Flush frame buffer            # gửi nốt event đang pending
  3. Close tracker (flush track_end events)
  4. Close sinks (Pulsar, S3, PG)
  5. Exit 0
```

## 8. Performance estimates

| Scale | CPU | RAM | GPU | FPS per camera |
|-------|-----|-----|-----|----------------|
| 1 camera | 2-4 cores | 4-8 GB | Optional | 25-30 |
| 2-3 cameras | 8 cores | 16-30 GB | NVIDIA T4 | 20-25 |
| 4-6 cameras | 16 cores | 30-60 GB | T4/A10 | 15-20 |

## 9. Configuration

```yaml
# configs/cameras.yaml
cameras:
  - camera_id: cam_01
    store_id: store_001
    name: Entrance
    source_type: rtsp
    source_uri: rtsp://10.0.0.10:554/stream1
    enabled: true
    fps_target: 25

  - camera_id: cam_02
    store_id: store_001
    name: Aisle 3
    source_type: video_file
    source_uri: data/videos/sample.mp4
    enabled: true
    fps_target: 30

settings:
  health_check_interval_sec: 10
  frame_queue_size: 2
  reconnect_delay_initial_sec: 1
  reconnect_delay_max_sec: 30
  worker_graceful_shutdown_sec: 10
  model_name: yolo11l.pt
  tracker_type: botsort
  conf_thres: 0.25
  class_filter: [0]
```

## 10. Key design decisions

| Decision | Reason |
|----------|--------|
| 1 camera = 1 OS process | Crash isolation, Python GIL không block camera khác |
| RTSPReader = thread riêng | I/O không block inference |
| FrameQueue maxsize=2 | Giữ latency thấp, drop frame cũ giữ frame mới |
| `queue.Queue` (thread-safe) | 2 thread truy cập đồng thời |
| Publish async + background retry | Pipeline không chờ network |
| Frame upload qua ThreadPoolExecutor | Upload chậm không block pipeline |
| Buffer bounded (100 events) | Tránh OOM khi Pulsar down |
| Drop oldest khi buffer full | Realtime: frame mới quan trọng hơn cũ |
| Tracker state reset khi crash | Chấp nhận track_id thay đổi, không cố gắng restore |
| Video file loop mode | Demo chạy liên tục không cần camera thật |
