# 05 — Failure Handling & Recovery

## Failure scenarios overview

```mermaid
flowchart TB
    subgraph Scenarios["Failure Scenarios"]
        S1["Camera disconnect\n(RTSP timeout)"]
        S2["Worker crash\n(inference OOM / segfault)"]
        S3["Pulsar unavailable\n(broker down / network)"]
        S4["S3 upload fail\n(timeout / quota)"]
        S5["GPU OOM\n(model quá nặng)"]
        S6["FPS degradation\n(inference quá chậm)"]
    end

    S1 -->|"RTSPReader reconnects"| R1["Recovery: auto-reconnect"]
    S2 -->|"CameraManager detects"| R2["Recovery: restart worker"]
    S3 -->|"Publisher retries"| R3["Recovery: buffer + retry"]
    S4 -->|"Skip frame + log"| R4["Degrade: skip upload"]
    S5 -->|"Worker exits"| R5["Recovery: manager restarts"]
    S6 -->|"Health metric"| R6["Alert: camera_offline alert"]

    style S1 fill:#f39c12,color:#000
    style S2 fill:#e74c3c,color:#fff
    style S3 fill:#e74c3c,color:#fff
    style S4 fill:#f39c12,color:#000
    style S5 fill:#e74c3c,color:#fff
    style S6 fill:#f39c12,color:#000
```

## Scenario 1: Camera disconnect → reconnect

```mermaid
sequenceDiagram
    participant R as RTSPReader
    participant Cam as Camera
    participant M as Metrics

    Note over R,Cam: đang chạy bình thường

    R->>Cam: ret, frame = cap.read()
    Cam-->>R: ❌ ret=False (timeout / cable unplugged)

    R->>M: disconnect_count++
    Note over R: log WARNING

    loop Reconnect loop
        Note over R: delay = min(2^(N-1), 30s)
        R->>R: sleep(delay)
        R->>R: cap.release()
        R->>Cam: cap = cv2.VideoCapture(rtsp_url)
        R->>Cam: ret, _ = cap.read()
        alt reconnected
            R->>M: reconnect_success++
            Note over R: log INFO: "Reconnected after N attempts"
        else still down
            Note over R: attempt++, tiếp tục loop
        end
    end
```

## Scenario 2: Worker crash → restart

```mermaid
sequenceDiagram
    participant CM as CameraManager
    participant CW as CameraWorker (pid=1001)
    participant New as CameraWorker (pid=1004)

    Note over CM,CW: đang chạy bình thường

    CW-->>CW: GPU OOM / segfault / unhandled exception
    Note over CW: process exits with code != 0

    loop Health check (10s interval)
        CM->>CW: is_alive()?
        CW-->>CM: False ❌
    end

    Note over CM: log ERROR: "Worker cam_01 dead, restarting..."
    CM->>CM: restart_count[cam_01]++
    Note over CM: backoff = min(2^(restart_count-1), 30)

    CM->>CM: sleep(backoff)
    CM->>New: spawn new CameraWorker(cam_01)
    New-->>CM: started, pid=1004
    Note over CM: log INFO: "Worker cam_01 restarted (pid=1004)"

    Note over New: bắt đầu lại từ frame_index=1<br/>pipeline_run_id mới<br/>tracker state reset
```

## Scenario 3: Pulsar unavailable → buffer + degrade

```mermaid
sequenceDiagram
    participant PL as Pipeline
    participant Pub as DetectionPublisher
    participant Pulsar as Pulsar Broker

    Note over PL,Pulsar: đang publish bình thường

    PL->>Pub: emitter.emit_frame(event_42)
    Pub->>Pulsar: producer.send(payload)
    Pulsar-->>Pub: ❌ TimeoutException

    Note over Pub: enter buffer mode
    Pub->>Pub: buffer[0] = event_42

    PL->>Pub: emitter.emit_frame(event_43)
    Pub->>Pub: buffer[1] = event_43

    Note over PL,Pulsar: ... buffer fills up ...

    PL->>Pub: emitter.emit_frame(event_143)
    Note over Pub: buffer size = 100 (full!)
    Pub->>Pub: drop event cũ nhất (giữ 100 frame mới nhất)
    Pub->>Pub: drop_count++
    Pub->>Pub: enqueue event_143

    Note over Pulsar: ... broker comes back ...

    Pub->>Pulsar: producer.send(buffer[0]) → OK ✅
    Note over Pub: drain buffer (gửi batch 10 events/lần)
    Pub->>Pub: resume normal mode
```

## Scenario 4: S3 upload fail → skip

```mermaid
sequenceDiagram
    participant PL as Pipeline (main thread)
    participant FS as FrameSampler
    participant S3 as S3 / MinIO

    PL->>FS: sampler.save(frame_jpg, frame_index=500)
    FS->>FS: ThreadPoolExecutor.submit(upload)
    Note over PL: pipeline tiếp tục frame 501 (không chờ)

    FS->>S3: put_object("frames/.../cam_01_500.jpg")
    S3-->>FS: ❌ timeout / connection error

    FS->>FS: upload_fail_count++
    FS->>FS: log WARNING
    Note over FS: skip frame này, không retry
    Note over FS: metadata đã publish lên Pulsar rồi
    Note over FS: frame sample là optional, không block pipeline
```

## Summary: Failure matrix

| Scenario | Detection | Recovery | Data loss? | Pipeline continues? |
|----------|----------|----------|------------|---------------------|
| Camera disconnect | `cap.read() == False` | Auto-reconnect (backoff 1→30s) | Mất frame trong thời gian disconnect | ✅ Camera khác vẫn chạy |
| Worker crash | `is_alive() == False` | CameraManager restart | Mất state tracker (reset track_id) | ✅ Camera khác vẫn chạy |
| Pulsar unavailable | `send() exception` | Buffer bounded + retry 3x | Mất event nếu buffer full | ✅ Pipeline chính vẫn chạy |
| S3 upload fail | `put_object() timeout` | Skip frame (optional data) | Mất sampled frame đó | ✅ Không ảnh hưởng |
| GPU OOM | `torch.cuda.OutOfMemoryError` | Worker exit → manager restart | Mất tracker state | ✅ Camera khác vẫn chạy |
| FPS degradation | `fps_observed < fps_target` | Alert camera health | Không mất data | ✅ Pipeline chậm lại |

> **Nguyên tắc cốt lõi:**
> 1. **Isolation**: 1 camera crash không ảnh hưởng camera khác (OS process isolation).
> 2. **Degrade gracefully**: nếu sink phụ (S3) lỗi, pipeline chính vẫn chạy.
> 3. **Bounded memory**: buffer có giới hạn, không tích lũy vô hạn.
> 4. **Observability**: mọi failure đều emit metric hoặc log để debug.
