# 00 — Vision Service: Tổng quan

## Kiến trúc tổng thể Vision → Pulsar → S3

```mermaid
flowchart TB
    subgraph Sources["📹 Input Sources"]
        RTSP["RTSP Camera\n(real device)"]
        VideoFile["Video File\n(.mp4, local)"]
    end

    subgraph VisionService["🎯 Vision Edge Service"]
        direction TB
        CM["CameraManager\n(Process cha - orchestrator)"]

        subgraph Workers["Worker Pool (OS Processes)"]
            CW1["CameraWorker\ncam_01"]
            CW2["CameraWorker\ncam_02"]
            CWN["CameraWorker\ncam_N"]
        end

        CM -->|"spawn"| CW1
        CM -->|"spawn"| CW2
        CM -->|"spawn"| CWN
    end

    subgraph Outputs["📤 Outputs"]
        Pulsar["Apache Pulsar\ndetection frame events"]
        S3["S3 / MinIO\nsampled frames (1fps)"]
        Metrics["Prometheus\nfps, health, lag"]
    end

    RTSP -->|"RTSP stream"| CW1
    VideoFile -->|"file path"| CW2
    CW1 -->|"DetectionFrameEvent"| Pulsar
    CW1 -->|"JPEG frame"| S3
    CW1 -->|"health metrics"| Metrics
    CW2 -->|"DetectionFrameEvent"| Pulsar
    CW2 -->|"JPEG frame"| S3
    CW2 -->|"health metrics"| Metrics

    style CM fill:#1a1a2e,stroke:#e94560,color:#fff
    style CW1 fill:#16213e,stroke:#0f3460,color:#fff
    style CW2 fill:#16213e,stroke:#0f3460,color:#fff
    style CWN fill:#16213e,stroke:#0f3460,color:#fff
```

## Luồng dữ liệu tổng quát (1 camera)

```mermaid
sequenceDiagram
    participant CM as CameraManager
    participant CW as CameraWorker (OS process)
    participant Reader as RTSPReader (thread)
    participant Detector as YOLO Detector
    participant Tracker as BoTSORT Tracker
    participant Pub as DetectionPublisher
    participant Pulsar as Apache Pulsar
    participant FS as FrameSampler
    participant S3 as S3/MinIO

    CM->>CW: spawn worker cho cam_01

    loop Frame loop (30 FPS target)
        Reader->>Reader: read() frame từ source
        Reader-->>CW: frame (BGR numpy)
        CW->>Detector: frame
        Detector-->>CW: List[Detection]
        CW->>Tracker: detections
        Tracker-->>CW: List[TrackedObject] (bbox + track_id)
        CW->>CW: build DetectionFrameEvent
        CW->>Pub: event
        Pub->>Pulsar: publish async (JSON)
        Note over CW,FS: mỗi 1 giây
        CW->>FS: frame JPEG
        FS->>S3: upload async
    end

    CM->>CW: health check (định kỳ 10s)
    CW-->>CM: alive + fps + error count
```

## Các thành phần chính

| Thành phần | Kiểu | Trách nhiệm |
|-----------|------|-------------|
| **CameraManager** | Process chính | Load config, spawn/restart worker, health check, graceful shutdown |
| **CameraWorker** | OS Process (1/camera) | Pipeline: read → detect → track → publish. Cô lập crash |
| **RTSPReader** | Thread trong worker | Đọc frame từ RTSP/video file, buffer queue, reconnect |
| **YOLO Detector** | Object | Inference person detection, confidence filter |
| **BoTSORT Tracker** | Object | Gán track_id, tracking lifecycle |
| **DetectionPublisher** | Object | Publish event JSON lên Pulsar (async, retry) |
| **FrameSampler** | Object | Lưu frame mẫu 1fps vào S3/MinIO (async upload) |
