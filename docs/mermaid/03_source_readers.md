# 03 — Source Readers: RTSP vs Video File

## Hai loại reader — cùng interface, khác behavior

```mermaid
flowchart TB
    subgraph Factory["SourceReaderFactory"]
        Config{camera.source_type?}
        Config -->|"rtsp"| RTSP["RTSPReader\n(reconnect logic)"]
        Config -->|"video_file"| Video["VideoFileReader\n(play once / loop)"]
    end

    subgraph RTSPReader["RTSPReader (Thread)"]
        direction TB
        RConnect["cv2.VideoCapture(rtsp_url)\n+ buffer_size=1"]
        RRead["cap.read()"]
        RCheck{"ret == True?"}
        RQueue["queue.put(frame)"]
        RReconnect["Reconnect loop\n+ exponential backoff"]

        RConnect --> RRead --> RCheck
        RCheck -->|"OK"| RQueue --> RRead
        RCheck -->|"fail"| RReconnect --> RConnect
    end

    subgraph VideoFileReader["VideoFileReader"]
        direction TB
        VOpen["cv2.VideoCapture(file_path)"]
        VRead["cap.read()"]
        VCheck{"ret == True?"}
        VQueue["queue.put(frame)"]
        VEnd["End of file\n→ loop or stop"]

        VOpen --> VRead --> VCheck
        VCheck -->|"OK"| VQueue --> VRead
        VCheck -->|"EOF"| VEnd
        VEnd -->|"loop=true"| VOpen
        VEnd -->|"loop=false"| VStop["worker.exit()"]
    end

    style RTSPReader fill:#1a1a2e,stroke:#e74c3c,color:#fff
    style VideoFileReader fill:#1a1a2e,stroke:#3498db,color:#fff
```

## RTSP: Reconnect flow chi tiết

```mermaid
sequenceDiagram
    participant R as RTSPReader
    participant Cam as RTSP Camera
    participant Q as FrameQueue
    participant M as Metrics

    R->>Cam: cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    R->>Cam: cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    Note over R: buffer nhỏ để tránh latency tích tụ

    loop Read loop (thread chạy liên tục)
        R->>Cam: ret, frame = cap.read()
        alt ret == True
            R->>Q: queue.put(frame)
            R->>M: total_read++
        else ret == False
            Note over R: camera disconnect hoặc network lỗi
            R->>M: disconnect_count++
            R->>R: enter reconnect loop
            loop Reconnect with backoff
                Note over R: delay = min(2^(attempt-1), 30s)
                R->>R: sleep(delay)
                R->>R: cap.release()
                R->>Cam: cap = cv2.VideoCapture(rtsp_url)
                R->>Cam: ret, _ = cap.read()
                alt ret == True
                    Note over R: reconnected!
                    R->>M: reconnect_success++
                    R->>Q: queue.put(frame)
                else ret == False
                    Note over R: attempt++, thử lại
                end
            end
        end
    end
```

## So sánh RTSP vs Video File

| Khía cạnh | RTSPReader | VideoFileReader |
|-----------|-----------|-----------------|
| **Nguồn** | `rtsp://ip:port/stream` | `data/videos/sample.mp4` |
| **Buffer** | `CV_CAP_PROP_BUFFERSIZE = 1` | Không cần giới hạn |
| **Reconnect** | Có — exponential backoff 1→30s | Không cần |
| **FPS control** | Theo camera FPS tự nhiên | Dùng `cv2.CAP_PROP_FPS` hoặc sleep để giả lập FPS |
| **End-of-stream** | Không có (stream vô hạn) | Có — loop hoặc exit |
| **Frame drop** | Có thể xảy ra nếu inference chậm | Hiếm khi cần (có thể giả lập FPS) |
| **SIGTERM** | `cap.release()`, close thread | `cap.release()`, cleanup |
| **Dùng trong demo** | Cần camera thật hoặc RTSP server | Dùng video file có sẵn |
| **Dùng trong production** | Camera siêu thị thật | Dùng cho backfill / replay |

## FPS control — Video file giả lập realtime

```mermaid
flowchart LR
    Frame["cap.read()"] --> Calc{"realtime mode?"}
    Calc -->|"yes"| Sleep["due_time = t0 + seq/fps\nif due > now: sleep(due - now)"]
    Calc -->|"no"| NoSleep["xử lý nhanh nhất có thể"]
    Sleep --> Queue["queue.put(frame)"]
    NoSleep --> Queue
```

> **Demo:** `realtime=True` cho video file để giả lập camera thật.  
> **Backfill:** `realtime=False` để xử lý nhanh nhất có thể.
