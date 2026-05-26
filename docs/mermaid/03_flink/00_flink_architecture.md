# Flink Architecture — Trong RVA Project

> Cách Flink JobManager, TaskManager, Task Slots, và Parallelism hoạt động trong RVA.
> Tham khảo: https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/flink-architecture/

---

## 1. Flink Cluster trong RVA — Session Mode (Standalone)

```mermaid
graph TB
    subgraph DockerCompose["Docker Compose"]
        JM["flink-jobmanager<br/>container: c5a...<br/>port: 8081 (UI)<br/>memory: 800m"]
        TM["flink-taskmanager<br/>container: 2c7...<br/>memory: 1600m<br/>8 task slots"]
        SUBMIT["flink-job-submitter<br/>chạy submit-jobs.sh<br/>rồi exit (0)"]
    end

    subgraph FlinkInternals["Flink Runtime Internals"]
        RM["ResourceManager<br/>quản lý 8 slots"]
        DISP["Dispatcher<br/>REST API + Web UI"]
        JM4["4 JobMaster instances<br/>mỗi job 1 JobMaster"]

        TS1["Slot 1: Bronze (chain)"]
        TS2["Slot 2: Bronze (chain)"]
        TS3["Slot 3: Silver"]
        TS4["Slot 4: Gold"]
        TS5["Slot 5: RealtimeMetrics"]
        TS6["Slot 6: buffer"]
        TS7["Slot 7: buffer"]
        TS8["Slot 8: buffer"]
    end

    JM --> RM
    JM --> DISP
    DISP --> JM4
    RM --> TS1
    RM --> TS2
    RM --> TS3
    RM --> TS4
    RM --> TS5

    SUBMIT -->|"flink run -d -c ..."| DISP
```

---

## 2. JobManager vs TaskManager — Ai làm gì

```mermaid
sequenceDiagram
    participant C as Client (flink-job-submitter)
    participant JM as JobManager
    participant TM as TaskManager (8 slots)

    C->>JM: POST /jobs (JAR + class name)
    JM->>JM: Dispatcher → tạo JobMaster
    JM->>JM: JobMaster: build JobGraph
    JM->>JM: ResourceManager: request slots

    JM->>TM: allocate slot 1, 2 cho Bronze
    JM->>TM: allocate slot 3 cho Silver
    JM->>TM: allocate slot 4 cho Gold
    JM->>TM: allocate slot 5 cho RealtimeMetrics

    Note over JM,TM: Slots 6-8: buffer

    TM->>TM: slot 1: run Bronze subtask
    TM->>TM: slot 2: run Bronze subtask (parallel)
    TM->>TM: slot 3: run Silver UDTF + INSERT
    TM->>TM: slot 4: run Gold GROUP BY + INSERT
    TM->>TM: slot 5: run Realtime parse→dedup→Redis+DLQ

    Note over JM: JobMaster monitor: checkpoint, restart nếu fail
```

| Component | Trong RVA | Vai trò |
|-----------|-----------|--------|
| **JobManager** | 1 container `flink-jobmanager` (800m) | Điều phối 4 jobs, REST API, Web UI, checkpoint coordinator |
| **TaskManager** | 1 container `flink-taskmanager` (1600m, 8 slots) | Chạy thật sự các task: parse JSON, SQL, ghi Iceberg, ghi Redis |
| **Client** | `flink-job-submitter` (exit 0) | Submit 4 jobs rồi exit, không phải runtime |

---

## 3. Task Slots — Đơn vị cấp phát tài nguyên

```
┌──────────────────────────────────────────────────────┐
│        flink-taskmanager (JVM, 1600m heap)            │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Slot 1   │ │ Slot 2   │ │ Slot 3   │ │ Slot 4   │ │
│  │ Bronze   │ │ Bronze   │ │ Silver   │ │ Gold     │ │
│  │ source→  │ │ source→  │ │ UDTF→    │ │ GROUP→   │ │
│  │ insert   │ │ insert   │ │ insert   │ │ upsert   │ │
│  │ 200m     │ │ 200m     │ │ 200m     │ │ 200m     │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Slot 5   │ │ Slot 6   │ │ Slot 7   │ │ Slot 8   │ │
│  │Realtime  │ │ buffer   │ │ buffer   │ │ buffer   │ │
│  │parse→    │ │ (trống)  │ │ (trống)  │ │ (trống)  │ │
│  │dedup→    │ │          │ │          │ │          │ │
│  │Redis+DLQ │ │          │ │          │ │          │ │
│  │ 200m     │ │ 200m     │ │ 200m     │ │ 200m     │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│                                                      │
│  Mỗi slot: ~200m managed memory                      │
│  Không có CPU isolation giữa các slot                │
└──────────────────────────────────────────────────────┘
```

### Tại sao Bronze cần 2 slots mà Silver chỉ cần 1?

```
Bronze: Source (parallelism=1) → Calc (2) → Correlate (2) → Calc (2) → Iceberg Sink
         1 slot                   2 slots (parallel)                    2 slots shared

Silver: Source (Iceberg scan) → Calc (1) → Correlate UDTF (1) → Calc (1) → Iceberg Sink
         1 slot                                                         1 slot (slot sharing)
```

Bronze `Correlate` operator có **parallelism=2** → cần 2 slot. Silver toàn bộ chain **parallelism=1** → 1 slot đủ nhờ **slot sharing**.

---

## 4. Slot Sharing — Tại sao 1 slot chạy được cả pipeline

```mermaid
graph LR
    subgraph "Slot 3 — 1 slot, 4 operator"
        SRC["Source<br/>Iceberg scan"]
        CALC1["Calc"]
        UDTF["Correlate<br/>ParseDetections"]
        CALC2["Calc"]
        SINK["Sink<br/>Iceberg INSERT"]
    end

    SRC --> CALC1 --> UDTF --> CALC2 --> SINK

    style SRC fill:#e3f2fd
    style CALC1 fill:#e3f2fd
    style UDTF fill:#e3f2fd
    style CALC2 fill:#e3f2fd
    style SINK fill:#e3f2fd
```

Slot sharing = tất cả operator trong cùng 1 job, cùng 1 parallelism index có thể chạy trong cùng 1 slot. Đây là lý do 8 slots chạy được 4 jobs mặc dù mỗi job có 4-5 operator.

**Không có slot sharing:** mỗi operator cần slot riêng → 4 jobs × 4 operators = 16 slots cần.

**Có slot sharing:** chỉ cần `max(parallelism)` slots mỗi job → 4 jobs = 5 slots + buffer = 8 slots.

---

## 5. Session Cluster — Đặc điểm của RVA

RVA dùng **Flink Session Cluster** (standalone mode):

```
docker compose up → Flink cluster khởi động → tồn tại đến khi docker compose down
                         │
                    submit 4 jobs
                         │
                    tất cả jobs chạy đồng thời
                    (không cần khởi động cluster mới cho mỗi job)
```

| Đặc điểm | Ý nghĩa với RVA |
|----------|-----------------|
| Cluster tồn tại lâu dài | Khởi động 1 lần, chạy pipeline liên tục |
| Nhiều jobs cùng cluster | 4 jobs chia sẻ 1 TaskManager |
| ResourceManager không tự scale | Không thể thêm TaskManager tự động → phải cấu hình slots thủ công |
| 1 TM crash = tất cả jobs affected | Nếu TaskManager OOM → 4 jobs cùng chết |
| JobManager fatal = toàn bộ cluster sập | Cần restart docker compose |

---

## 6. Công thức tính slots cho RVA

```
slots ≥ max_parallelism_job1 + max_parallelism_job2 + ... + buffer

Hiện tại:
  Bronze:     parallelism 2 (Correlate operator)
  Silver:     parallelism 1
  Gold:       parallelism 1
  Realtime:   parallelism 1
  Buffer:     3 slots
  ─────────────────────────────────
  Tổng:       8 slots
```

Khi scale:
- **Thêm camera**: không tăng jobs → không cần tăng slots
- **Tăng parallelism** (để xử lý nhanh hơn): tăng slots tương ứng
- **Thêm job mới**: +1 slot/job (parallelism 1) hoặc +P slots (parallelism P)

---

## 7. Standalone Mode Limitation — Không Auto-Scale

```text
Flink Session Cluster (standalone):
  ResourceManager chỉ phân phối slots từ TaskManager CÓ SẴN
  KHÔNG thể tự động khởi động TaskManager mới

So với:
  Flink trên Kubernetes:
    ResourceManager → yêu cầu K8s API → tạo Pod TaskManager mới
    → auto-scale theo workload
```

Với Docker Compose, muốn thêm TaskManager: phải thêm service `flink-taskmanager-2` vào docker-compose.yml thủ công. Cho thesis demo, 1 TaskManager 8 slots là đủ.

---

## 8. Checkpoint & Recovery trong Session Cluster

```mermaid
sequenceDiagram
    participant JM as JobManager
    participant TM as TaskManager
    participant CK as Checkpoint Storage (MinIO)

    loop Mỗi 10s (Realtime) / 30s (Lakehouse)
        JM->>TM: trigger checkpoint
        TM->>TM: snapshot state (ValueState, window, counters)
        TM->>CK: upload snapshot → file:///opt/flink/state/checkpoints
        TM->>JM: checkpoint confirmed
        JM->>JM: commit Iceberg transaction
    end

    Note over JM: Nếu TM crash:
    JM->>JM: restart strategy: fixed-delay
    JM->>TM: re-allocate slots
    TM->>CK: restore state từ checkpoint gần nhất
    TM->>TM: resume từ vị trí đã checkpoint
```

| Setting | Lakehouse | Realtime | Ý nghĩa |
|---------|-----------|----------|--------|
| `execution.checkpointing.interval` | 30s | **10s** | Realtime checkpoint nhanh hơn → ít data loss hơn khi crash |
| `checkpointing.mode` | EXACTLY_ONCE | EXACTLY_ONCE | Iceberg commit atomic; Redis at-least-once |
| `tolerable-failed-checkpoints` | 5 | 5 | Cho phép 5 lần fail liên tiếp trước khi fail job |

---

## 9. Key takeaways

| Khái niệm | Trong RVA |
|-----------|-----------|
| **JobManager** | 1 container (800m), quản lý 4 JobMaster |
| **TaskManager** | 1 container (1600m), 8 slots, chạy tất cả task |
| **Task Slot** | Đơn vị cấp phát managed memory (~200m/slot), không CPU isolation |
| **Slot Sharing** | Cho phép 1 slot chạy toàn bộ pipeline của 1 job |
| **Session Cluster** | Cluster tồn tại lâu dài, nhiều jobs chia sẻ |
| **Standalone Mode** | Không auto-scale TM, phải cấu hình slots thủ công |
| **Parallelism** | Bronze=2 (Correlate), còn lại=1 |
| **Checkpoint** | 10s Realtime, 30s Lakehouse, RocksDB state backend |
