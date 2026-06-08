# Alert Pipeline Design

> Design analysis for the Pipeline Alert System in the Retail Video Analytics
> platform. Written before implementation to scope components, technology
> choices, performance impact, and UI before any code is committed.

---

## 1. TL;DR — Most of the heavy lifting already exists

The expensive, hard part of an alert system — **capturing video evidence at the
moment an incident happens and persisting it to object storage** — is **already
built** in the Vision service:

| Component | File | Status |
|---|---|---|
| `AlertClipExtractor` (pre/post ring buffer → mp4 → S3) | `services/vision/emit/clip_extractor.py` | ✅ exists |
| `FrameSampler` (periodic JPEG snapshots → S3) | `services/vision/emit/frame_sampler.py` | ✅ exists |
| Density trigger (`detections > alert_density_threshold`) | `services/vision/worker.py:485` | ✅ exists |
| `clip_created` event emitted to Pulsar `media-events` topic | `services/vision/emit/pulsar_emitter.py:221` | ✅ exists |
| S3 client + presign capability (boto3) | `packages/storage/src/storage/s3_client.py` | ✅ exists |

**The missing 30% is the alert *event* path, not the video path:**

1. **No consumer** for the `media-events` topic — `clip_created` events are
   published to Pulsar but nothing reads them. The mp4 lands in S3 and the alert
   metadata is lost.
2. `alerts: []` is hardcoded in `services/api/src/rva_api/api/v1/live.py:876`.
3. `AlertList.tsx` is a presentational shell with no clip review, no
   acknowledge/resolve.
4. Trigger logic is thin: only `density_high` (raw detection count). The richer
   realtime signals we already compute — queue occupancy, `wait_ms`, line
   crossings, FPS — are not wired to alerts.
5. No endpoint to hand the browser a playable S3 clip URL.

So the work is: **build the alert event pipeline that connects existing clip
storage to the dashboard, and add a few more triggers.**

---

## 2. Answering the design questions

### Q1. How will alerts work in this architecture?

An alert is a **typed incident record** with three layers of data:

```text
1. The fact   — what/where/when/severity      (always present, cheap)
2. A snapshot — one JPEG at trigger time       (cheap, already on disk/S3)
3. A clip     — pre/post mp4 of the incident   (optional, already built)
```

Alerts come from **two sources**, evaluated where the data already lives:

```text
 SOURCE A — Clip-backed "incident" alerts (video evidence)
 ─────────────────────────────────────────────────────────
 Vision worker  ──(trigger)──►  AlertClipExtractor
   detects condition            ├─ mp4 ─► S3  clips/{date}/{store}/{cam}/{id}.mp4
   (e.g. density_high)          └─ clip_created event ─► Pulsar media-events

 SOURCE B — State-threshold "condition" alerts (no clip required)
 ───────────────────────────────────────────────────────────────
 RealtimeMetricsJob already writes realtime state to Redis:
   queue:live:{cam}:{zone}   (current_count, avg_wait_ms, max_wait_ms)
   stats:count:{cam}, line:hist:{cam}:{minute}
 An Alert Evaluator reads these on a tick and emits condition alerts.
```

Both converge into one **alert store in Redis**, which the API reads:

```text
 media-events ─►┐
                ├─► Alert Service ─► Redis alert store ─► FastAPI ─► React
 Redis state ──►┘                       │
                                        └─(optional)─► Iceberg gold_alerts (history)
```

### Q2. What components does it consist of?

| # | Component | Where it runs | New or existing |
|---|---|---|---|
| 1 | Trigger detectors (density, queue, wait, lag) | Vision worker + Alert Evaluator | partly exists |
| 2 | Clip/snapshot capture → S3 | Vision (`AlertClipExtractor`) | ✅ exists |
| 3 | `clip_created` event on `media-events` | Vision emitter | ✅ exists |
| 4 | **Alert Service** (consume `media-events` + evaluate Redis thresholds → write alert store) | new lightweight Python process/thread | **new** |
| 5 | **Alert store** (Redis: recent index + per-alert hash) | Redis | **new** |
| 6 | **Alert API** (list, presigned clip URL, acknowledge) | FastAPI | **new** |
| 7 | **Alert UI** (list + detail modal with player) | React | **new** (shell exists) |
| 8 | Alert history table `gold_alerts` (optional) | Flink/Trino + Iceberg | **future** |

### Q3. Is the alert feature for reviewing the image/video at the moment it fired?

**Yes — that is exactly the value proposition, and the capture half is done.**
When an alert fires, the user can:

- see a **snapshot** (the trigger-frame JPEG) inline in the alert list;
- open a **clip** — a short mp4 of `pre_buffer_sec` before + `post_buffer_sec`
  after the trigger (default 5s + 5s), played in the browser.

The `AlertClipExtractor` already encodes this clip and uploads it to
`s3://{bucket}/clips/{date}/{store}/{camera}/{alert_id}.mp4`. What is missing is
serving that object back to the browser (Q4).

### Q4. What technology?

| Concern | Technology | Why |
|---|---|---|
| Event transport | **Pulsar** `media-events` topic | already produced by Vision |
| Threshold evaluation | **Python evaluator reading Redis** | cheap, reversible; Redis already holds realtime state. (Flink CEP is the production-scale alternative — but Flink is memory-constrained here, see §4) |
| Hot alert store | **Redis** (sorted set index + hash per alert, TTL ~24h) | same store the dashboard already reads; one round-trip via pipeline |
| Video persistence | **S3** (already used) | clips already uploaded by Vision |
| Browser playback | **S3 presigned GET URL** + HTML5 `<video>` | boto3 `generate_presigned_url`; clip streams from S3 directly, bypassing the API |
| History (optional) | **Iceberg `gold_alerts` + Trino** | consistent with existing Gold tables |
| Serving | **FastAPI** | existing BFF |
| UI | **React + existing components** | `AlertList.tsx` shell already present |

### Q5. Do we need a dedicated S3 video-upload pipeline?

**No — it already exists.** `AlertClipExtractor._encode_upload_clip()` builds the
mp4 with `cv2.VideoWriter` and calls `s3.put_object(...)`. It runs on a
background `ThreadPoolExecutor`, so the upload does **not** block the Vision hot
loop. The only thing currently gating it is configuration:

```yaml
# configs/cameras.yaml  (currently all false)
media_upload_enabled: false      # master switch for any S3 media
frame_sampling_enabled: false    # periodic snapshots
alert_clip_enabled:    false     # alert mp4 clips
alert_density_threshold: 10
```

To activate the existing pipeline, these become `true`. No new upload code is
required — only the **consumer** that turns the resulting `clip_created` event
into a user-visible alert.

### Q6. Performance / resource impact?

This is the part to be careful about, given prior GPU crashes and the Flink OOM.
Cost is broken down by where it runs:

| Cost center | Runs on | Impact | Notes |
|---|---|---|---|
| **`clip_extractor.feed()` per frame** — full-frame `cv2.imencode` JPEG **every frame** | **Vision hot loop** | ⚠️ **Highest** — ~8–15 ms/frame at 1280px on CPU, directly steals from the ~9.4 FPS budget | This is the one real risk. See mitigations below. |
| Ring buffer RAM (`pre_buffer_sec * fps` JPEGs) | Vision RAM | 🟢 ~15–25 MB/camera at 5 s × 25 fps | Modest |
| Clip encode + S3 upload on trigger | **Background thread** | 🟢 does **not** block hot loop; ~1–3 s of one core per clip; `cooldown_sec=30` caps frequency | Already threaded |
| S3 bandwidth per clip | Network | 🟢 ~1–5 MB per alert at low alert rates | Negligible |
| Alert Evaluator (read Redis on tick) | Separate process | 🟢 a few keys every N s via pipeline, <1 ms | Trivial |
| `media-events` consumer | Separate process | 🟢 low event volume | Trivial |
| API reading alert store per poll | FastAPI | 🟢 one Redis pipeline round-trip | Consistent with the live-dashboard perf fix already applied |
| Clip playback | **Browser ↔ S3 directly** | 🟢 no API load; on-demand only when a modal opens | Presigned URL streams from S3 |

**Conclusion:** every part except one is background, on-demand, or cheap. The
**only** meaningful hot-path cost is the per-frame JPEG encode inside
`feed()`. Mitigations:

1. **Keep `alert_clip_enabled=false` by default**, enable it only for the demo /
   evaluation runs. Condition alerts (Source B) need no per-frame encode at all.
2. **Reduce clip fidelity**: lower `clip_jpeg_quality`, or feed the ring buffer
   every 2nd–3rd frame (clip at ~8–12 fps is fine for evidence).
3. **Snapshot-only alerts**: for most condition alerts, a single JPEG (already
   produced by `FrameSampler` or the live-frame writer) is enough — skip the mp4
   entirely and only record a clip for high-severity incidents.

The alert **event** pipeline (Sources B, components 4–7) has negligible resource
cost and can run continuously. The clip **capture** (Source A) is the only
toggle to manage for performance.

### Q7. What does the alert feature look like on the UI?

Two surfaces: the existing **list panel** on the Live page, and a new
**detail modal** with the player.

```text
 LIVE PAGE — Alerts panel (replaces empty AlertList)
 ┌─────────────────────────────────────────────┐
 │ New alerts                         View all  │
 │ ┌─────────────────────────────────────────┐ │
 │ │ ▣  Queue overcrowded — checkout_queue_02 │ │  ← thumbnail (snapshot)
 │ │    8 people, avg wait 3m 12s   • 12s ago │ │     + title + description
 │ │                                  [HIGH]  │ │     + severity badge
 │ ├─────────────────────────────────────────┤ │
 │ │ ▣  High density — cam_01                  │ │
 │ │    14 detections in frame      • 1m ago  │ │
 │ │                                [MEDIUM]  │ │
 │ └─────────────────────────────────────────┘ │
 └─────────────────────────────────────────────┘
        │ click a row
        ▼
 ALERT DETAIL MODAL
 ┌─────────────────────────────────────────────┐
 │ Queue overcrowded — checkout_queue_02  [×]  │
 │ ┌─────────────────────────────────────────┐ │
 │ │   ▶  mp4 clip (presigned S3 URL)         │ │  ← HTML5 <video controls>
 │ │      pre 5s ──[trigger]── post 5s        │ │
 │ └─────────────────────────────────────────┘ │
 │ Camera: cam_01   Zone: checkout_queue_02    │
 │ Severity: HIGH   When: 2026-06-07 22:41:03  │
 │ Count: 8   Avg wait: 3m 12s                 │
 │                                             │
 │           [ Acknowledge ]   [ Resolve ]     │
 └─────────────────────────────────────────────┘
```

UI behaviours:

- severity color: high = red, medium = orange, low = amber (already in
  `AlertList.tsx`);
- relative timestamps ("12s ago"), newest first;
- thumbnail = snapshot JPEG (presigned) or the live snapshot endpoint;
- clip plays only when the modal is open (lazy, no background cost);
- acknowledge/resolve call the API and update the alert `status`;
- optional toast/badge when a new `high` alert arrives.

---

## 3. Proposed data contracts

### Alert record (Redis hash `alert:item:{alert_id}`)

```jsonc
{
  "alert_id":     "cam_01_10432_density_high",
  "camera_id":    "cam_01",
  "store_id":     "store_001",
  "alert_type":   "density_high | queue_overcrowded | long_wait | pipeline_lag",
  "severity":     "low | medium | high",
  "title":        "Queue overcrowded — checkout_queue_02",
  "description":  "8 people, avg wait 3m 12s",
  "zone":         "checkout_queue_02",
  "track_id":     null,
  "event_ts":     "2026-06-07T22:41:03Z",
  "status":       "new | acknowledged | resolved",
  "snapshot_key": "frames/2026-06-07/.../10432.jpg",   // optional
  "clip_s3_key":  "clips/2026-06-07/store_001/cam_01/cam_01_10432_density_high.mp4" // optional
}
```

### Redis layout

| Key | Type | Purpose | TTL |
|---|---|---|---|
| `alert:live:{camera_id}` | ZSET (score = event_ts_ms) | recent alert ids per camera, trimmed to last N | 24h |
| `alert:item:{alert_id}` | HASH | full alert record | 24h |

### API surface (new)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/live/{camera_id}/dashboard` | `alerts: []` → real recent alerts (read from Redis) |
| `GET /api/v1/alerts?camera_id=&status=` | list / filter alerts |
| `GET /api/v1/alerts/{alert_id}/clip` | 302 → S3 presigned mp4 URL (expires ~5 min) |
| `GET /api/v1/alerts/{alert_id}/snapshot` | 302 → S3 presigned JPEG URL |
| `POST /api/v1/alerts/{alert_id}/ack` | set status = acknowledged/resolved |

---

## 4. Why a Python evaluator instead of Flink CEP

Flink is the "correct" production home for complex event processing (CEP
patterns, windowed thresholds, exactly-once). But in **this** environment:

- the TaskManager is already memory-constrained (recent OOM, raised to 3072m,
  `parallelism.default=1`); adding a job costs slots and RAM;
- the alert rules here are simple thresholds over state Redis already holds;
- a separate Python evaluator is **reversible** (start/stop without touching the
  Flink cluster) and demo-friendly.

For the thesis, document this as a deliberate trade-off: *"a lightweight
evaluator covers the MVP; Flink CEP is the scale-out path when rules grow
stateful or multi-event."*

---

## 5. Phased implementation plan

**Phase 1 — Condition alerts, no clips (fastest visible result)**
- Alert Evaluator process: read `queue:live:*`, `stats:count:*` on a tick.
- Rules: `queue_overcrowded` (count ≥ N), `long_wait` (max_wait_ms > T),
  `pipeline_lag` (frame latency / FPS).
- Write to Redis alert store.
- API: `live.py` reads alert store; new `alerts.py` router (list + ack).
- UI: wire `AlertList.tsx` to real data; relative time + severity.
- **No Vision change, no S3, no perf risk.**

**Phase 2 — Clip-backed incident alerts**
- `media-events` consumer (fold into Alert Service): on `clip_created`, write an
  alert with `clip_s3_key`.
- Enable `media_upload_enabled` + `alert_clip_enabled` for demo runs.
- API: presigned `clip`/`snapshot` endpoints.
- UI: detail modal with HTML5 `<video>`.

**Phase 3 — History & polish (optional)**
- `gold_alerts` Iceberg table from `media-events` (Flink) for retention beyond
  Redis TTL; Trino-backed alert history on the Analytics page.
- Toast/badge for new high-severity alerts.

---

## 6. Open decisions (need confirmation before coding)

1. **Where does the Alert Service run?** Options: (a) a thread inside the API
   process, (b) a standalone Python process in tmux/compose, (c) a Flink job.
   Recommendation: **(b)** standalone — isolated, restartable, no API coupling.
2. **Clips on by default or demo-only?** Recommendation: **demo-only**
   (`alert_clip_enabled=true` only for evaluation) to protect Vision FPS.
3. **Threshold values** for `queue_overcrowded`, `long_wait`, `pipeline_lag` —
   pick defaults now, make them config in `cameras.yaml`.
4. **Redis-only or also Iceberg history** for the thesis scope?

---

## 7. Status snapshot

```text
Clip capture → S3            ✅ exists (AlertClipExtractor, gated by config)
clip_created → Pulsar        ✅ exists (media-events topic)
S3 presign capability        ✅ exists (boto3 client)
media-events consumer        ❌ missing  ← core gap
Threshold evaluator          ❌ missing  (only density_high in Vision)
Redis alert store            ❌ missing
Alert API (list/clip/ack)    ❌ missing
Alert UI (list/detail/player)❌ missing  (AlertList shell exists)
gold_alerts history          ❌ future
```
