# 01 — CameraManager: Multi-camera Orchestrator

## Process model

```mermaid
flowchart TB
    subgraph Main["Main Process: CameraManager"]
        direction TB
        LoadConfig["1. Load camera config\n(configs/cameras.yaml)"]
        SpawnWorkers["2. Spawn workers\n(mỗi camera 1 process)"]
        HealthLoop["3. Health check loop\n(interval: 10s)"]

        LoadConfig --> SpawnWorkers --> HealthLoop
        HealthLoop -->|"worker dead?"| Restart["4. Restart worker\n+ exponential backoff"]
        Restart --> HealthLoop
    end

    subgraph WorkerPool["Worker Pool"]
        W1["PID: 1001\nCameraWorker(cam_01)\nRTSP source"]
        W2["PID: 1002\nCameraWorker(cam_02)\nVideo file source"]
        W3["PID: 1003\nCameraWorker(cam_03)\nRTSP source"]
    end

    HealthLoop -.->|"check /health"| W1
    HealthLoop -.->|"check /health"| W2
    HealthLoop -.->|"check /health"| W3

    W1 -.->|"crash / OOM"| HealthLoop

    style Main fill:#1a1a2e,stroke:#e94560,color:#fff
    style W1 fill:#16213e,stroke:#0f3460,color:#fff
    style W2 fill:#16213e,stroke:#0f3460,color:#fff
    style W3 fill:#16213e,stroke:#0f3460,color:#fff
```

## Lifecycle sequence

```mermaid
sequenceDiagram
    participant Main as CameraManager (PID 1000)
    participant CW1 as CameraWorker cam_01 (PID 1001)
    participant CW2 as CameraWorker cam_02 (PID 1002)
    participant Sig as OS Signal (SIGTERM / SIGINT)

    Main->>Main: load configs/cameras.yaml
    Note over Main: cameras: [cam_01 (RTSP), cam_02 (video)]

    Main->>CW1: multiprocessing.Process(target=run_worker, args=(cam_01_config))
    CW1-->>Main: started, PID=1001
    Main->>CW2: multiprocessing.Process(target=run_worker, args=(cam_02_config))
    CW2-->>Main: started, PID=1002

    loop Health check every 10s
        Main->>CW1: is_alive()?
        CW1-->>Main: True, fps=24.8
        Main->>CW2: is_alive()?
        CW2-->>Main: True, fps=29.9
        Note over Main: emit health metrics
    end

    Note over CW1,CW2: ... some time later, cam_01 worker crashes ...

    Main->>CW1: is_alive()?
    CW1-->>Main: False ❌
    Note over Main: backoff = min(2^0, 30s) = 1s
    Main->>Main: sleep 1s
    Main->>CW1: spawn new CameraWorker(cam_01)
    CW1-->>Main: started, PID=1004
    Note over Main: restart_count[cam_01]++

    Sig->>Main: SIGTERM (Ctrl+C / docker stop)
    Main->>CW1: terminate() + join(timeout=10s)
    Main->>CW2: terminate() + join(timeout=10s)
    Note over Main: cleanup: close Pulsar, flush logs
```

## Restart backoff policy

```mermaid
flowchart LR
    Crash["Worker crash"] --> Check{restart_count?}
    Check -->|"0-1 lần"| Delay1["1 giây"]
    Check -->|"2 lần"| Delay2["2 giây"]
    Check -->|"3 lần"| Delay3["4 giây"]
    Check -->|"4+ lần"| DelayN["min(2^(N-1), 30 giây)"]
    Delay1 --> Spawn["Spawn new worker"]
    Delay2 --> Spawn
    Delay3 --> Spawn
    DelayN --> Spawn
    Spawn --> Health["Health check loop"]
```

## Camera config contract

```yaml
# configs/cameras.yaml
cameras:
  - camera_id: cam_01
    store_id: store_001
    name: Entrance
    source_type: rtsp             # "rtsp" | "video_file"
    source_uri: rtsp://10.0.0.10:554/stream1
    enabled: true
    fps_target: 25
    resolution_width: 1920
    resolution_height: 1080

  - camera_id: cam_02
    store_id: store_001
    name: Aisle 3
    source_type: video_file       # "video_file" cho demo
    source_uri: data/videos/sample.mp4
    enabled: true
    fps_target: 30

settings:
  health_check_interval_sec: 10
  frame_queue_size: 2
  reconnect_delay_initial_sec: 1
  reconnect_delay_max_sec: 30
  worker_graceful_shutdown_sec: 10
```
