# 02 — CameraWorker: Internal Pipeline (1 camera)

## Pipeline tổng thể trong 1 worker

```mermaid
flowchart TB
    subgraph Worker["CameraWorker Process (1 camera)"]
        direction TB

        subgraph Thread1["Thread: RTSPReader"]
            Read["cv2.VideoCapture.read()"]
            Queue["FrameQueue\n(max_size=2)"]
            Read -->|"frame"| Queue
            Read -->|"queue full?"| Drop["Drop oldest frame\n(drop_count++)"]
            Drop -.-> Queue
        end

        subgraph MainThread["Main Thread: Pipeline"]
            Dequeue["queue.get()"]
            Detect["YOLO Detector\nperson detection"]
            Track["BoTSORT Tracker\ntrack_id assignment"]
            Build["build DetectionFrameEvent"]

            Dequeue --> Detect --> Track --> Build
        end

        Queue -->|"latest frame"| Dequeue

        subgraph AsyncOut["Async Output (non-blocking)"]
            PulsarPub["PulsarEmitter\npublish async + retry"]
            FrameSave["FrameSampler\nsave JPEG 1fps"]
            TrackEmit["TrackLifecycleManager\nstart/sample/end"]

            Build --> PulsarPub
            Build --> FrameSave
            Build --> TrackEmit
        end

        PulsarPub --> Pulsar["Apache Pulsar"]
        FrameSave --> S3["S3 / AWS S3"]
        TrackEmit --> PG["PostgreSQL\n(Phase 2 target)"]
    end

    style Thread1 fill:#1a1a2e,stroke:#f39c12,color:#fff
    style MainThread fill:#16213e,stroke:#0f3460,color:#fff
    style AsyncOut fill:#0d1b2a,stroke:#27ae60,color:#fff
```

## Sequence: 1 frame qua pipeline

```mermaid
sequenceDiagram
    participant R as RTSPReader (thread)
    participant Q as FrameQueue
    participant PL as Pipeline (main thread)
    participant Y as YOLO Detector
    participant T as BoTSORT Tracker
    participant P as DetectionPublisher
    participant FS as FrameSampler

    R->>R: ret, frame = cap.read()
    R->>Q: queue.put(frame)
    Note over R,Q: nếu queue.full() → drop frame cũ nhất

    PL->>Q: frame = queue.get()
    PL->>Y: yolo.predict(frame, classes=[0])
    Y-->>PL: List[Detection] (bbox, conf, cls)
    Note over PL: filter class=person, conf>=0.4

    PL->>T: tracker.update(detections)
    T-->>PL: List[TrackedObject] (bbox + track_id)
    Note over PL: gán track_id, bbox, centroid

    PL->>PL: build DetectionFrameEvent
    Note over PL: frame_index, capture_ts, camera_id,<br/>detections[...], image_size

    par Async publish (không block pipeline)
        PL->>P: emitter.emit_frame(event)
        P-->>P: json.dumps → pulsar.producer.send_async()
    and Async frame save (mỗi 1 giây)
        alt frame_index % fps_target == 0
            PL->>FS: sampler.save(frame, frame_index)
            FS-->>FS: ThreadPoolExecutor.submit(upload_jpg)
        end
    end

    Note over PL: tiếp tục frame tiếp theo (không chờ upload)
```

## Frame queue & dropping strategy

```mermaid
flowchart TB
    Reader["RTSPReader.read()"] --> Q{Queue size?}

    Q -->|"size < 2"| Put["queue.put(new_frame)"]
    Q -->|"size == 2 (full)"| DropOld["queue.get() → drop\nqueue.put(new_frame)"]

    Put --> Counter["total_read++"]
    DropOld --> Counter2["total_read++\ndrop_count++"]

    Counter --> Pipeline["Pipeline xử lý"]
    Counter2 --> Pipeline

    style DropOld fill:#e74c3c,color:#fff
    style Put fill:#27ae60,color:#fff
```

> **Nguyên tắc:** frame mới quan trọng hơn xử lý đủ mọi frame. Khi inference chậm hơn FPS camera, drop frame cũ để giữ realtime.
> 
> **FrameQueue phải dùng `queue.Queue(maxsize=2)`** (Python thread-safe). RTSPReader thread ghi, Pipeline main thread đọc.

## DetectionFrameEvent schema hiện tại → target

| Field | Hiện tại (Phase 1) | Target (Phase 2) |
|-------|-------------------|-----------------|
| `schema_version` | `"1.0"` (string) | `"1.0"` → `"2.0"` khi thêm field |
| `pipeline_run_id` | `uuid4().hex` | giữ nguyên |
| `source` | `{store_id, camera_id, stream_id}` | → **flatten**: `store_id`, `camera_id` top-level |
| `event_id` | **thiếu** | → thêm: `f"{camera_id}-{frame_index:09d}-{capture_ts}"` |
| `frame_index` | `int` (tăng dần) | giữ nguyên |
| `capture_ts` | ISO-8601 | giữ nguyên, thêm timezone `Z` |
| `image_size` | `{width, height}` | giữ nguyên |
| `detections[]` | `[{det_id, class, bbox, centroid, track_id}]` | → thêm `confidence`, `centroid_norm` |
| `runtime` | `{model_name, tracker_type}` | giữ nguyên, thêm `model_version` |
| `frame_ref` | **thiếu** | → thêm: `{saved: bool, uri: "s3://..."}` |
