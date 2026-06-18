# 08 — Serving DAG Latency: Analysis & Remediation Backlog

**Date:** 2026-06-15 (updated 2026-06-16)
**Status:** Root cause CONFIRMED via live incident (§2.5/§6). `infer-source-parallelism` fixed; **merge-on-read delete compaction is the real blocker and still needs implementing for ALL upsert fact tables.**
**Scope:** `gold_serving_*` Airflow DAGs (traffic, zone, heatmap, dwell, queue, alert, executive) that run Flink **batch** jobs via `services/flink-jobs/python/submit_batch_job.py`.

> **TL;DR (2026-06-16):** The `gold_serving_queue` stall was NOT mainly small data files or parallelism — it was **merge-on-read position-delete files** accumulating on the **upsert** table `gold_queue_sessions`. The Flink batch reader hung in `BaseDeleteLoader.loadPositionDeletes` applying those deletes over remote S3. Append-only sources (silver/bronze) are immune. **Every upsert fact table read by a batch/Trino reader has this problem** and needs periodic compaction — see §2.5, §6, and R3.

---

## 1. Symptom

Each `gold_serving_*` DAG takes **tens of minutes** to succeed, even though the underlying data is tiny (single store, a few days, ~400K silver rows). Intuition was: "Flink processes data fast → DAGs should be fast." That intuition holds for **streaming** (warm, long-running jobs with high throughput) but **not** for these DAGs.

**Key insight:** the DAG wall-clock is dominated by **overhead**, not by Flink data computation. Actual compute per task is on the order of seconds; the rest is waiting.

---

## 2. Root causes (ranked by impact)

### 2.1 Global file lock serializes ALL batch jobs
- `submit_batch_job.py` acquires a single lock file `/tmp/rva-flink-batch.lock` before submitting.
- Effect: **only one batch job runs cluster-wide at a time.** Every domain/task queues behind the others.
- Evidence (Airflow log, `gold_serving_queue / refresh_queue_hourly`):
  ```
  15:38:18 Running command ... --domain queue_hourly ...
  15:40:51 waiting_for_lock domain=queue_hourly lock=/tmp/rva-flink-batch.lock
  15:40:51 acquired_lock   domain=queue_hourly
  ```
  ~2.5 min spent purely waiting for the lock before any work began.

### 2.2 Per-job cold-start overhead, repeated every task
Each serving task is a **fresh Flink batch job**. Fixed cost paid every single time:
- Upload / load the ~1.4 MB fat jar into the JobManager.
- Build the job graph; create the Iceberg REST catalog + DB/table handles.
- Plan splits, request slots, deploy subtasks.
- This bootstrap (tens of seconds → minutes) dwarfs the negligible compute. DAGs with multiple tasks (hourly + daily) pay it once per task, sequentially (compounded by §2.1).

### 2.3 Iceberg source-parallelism inference blow-up — FIXED 2026-06-15 (necessary, not sufficient)
- Iceberg's Flink source infers scan parallelism = split count (cap 100), **independent** of the adaptive batch scheduler.
- Streaming jobs commit a small file every 30s → fact tables (e.g. `gold_queue_sessions`) accumulate ~100 tiny files → batch scan inferred **parallelism=100** on a **16-slot** cluster.
- Result: slot-request waves + `slot.request.timeout=120000` (2 min) stalls.
- **Fix applied:** `table.exec.iceberg.infer-source-parallelism: false` in `infrastructure/flink/conf/flink-conf.yaml` (forces scan to honour `parallelism.default=1`). Loaded after cluster restart, verified (queue source ran at p=1).
- **But this alone did NOT fix queue** — after the fix the queue job ran at p=1 yet still hung 20 min and FAILED. The real cause is §2.5.

### 2.4 Remote AWS S3 latency (ap-southeast-2)
- Storage is real AWS S3 (`s3.ap-southeast-2.amazonaws.com`), not local MinIO.
- Every manifest list, parquet read, and snapshot commit is an **HTTPS round-trip over the internet**.
- This is the *multiplier* that turns §2.5 (many delete files to load) from "slow" into "stalls past timeout".

### 2.5 ⭐ Merge-on-read delete-file accumulation on UPSERT tables — THE real blocker (confirmed 2026-06-16)
- All 7 Gold fact tables are written with `write.upsert.enabled=true` (format-v2, merge-on-read). Each streaming commit (every 30s, `overwrite` op) writes new data files **plus position-delete files**.
- A **batch (or Trino) reader** of such a table must, per data file, **load and apply all applicable delete files** (`DeleteFilter.applyPosDeletes`). Over remote S3 with hundreds of accumulated delete files this is pathologically slow and stalled the reader.
- **Live evidence (queue_hourly, 2026-06-16):** TaskManager thread dump of the hung legacy source thread:
  ```
  iceberg.data.BaseDeleteLoader.loadPositionDeletes
  → iceberg.data.DeleteFilter.applyPosDeletes → DeleteFilter.filter
  → iceberg.flink.source.RowDataFileScanTaskReader.open   (stuck in Tasks.waitFor retry loop)
  ```
  `gold_queue_sessions` had **242 snapshots / 208 `overwrite` commits** for ~742 live rows. Source read 0 records in 20 min → job FAILED.
- **Why only queue first:** `silver_detections_v2` (read by traffic/zone/heatmap) is **append-only** (no delete files) → reads fine. Queue/alerts/track-summary are upsert. Queue hit it first because it had the most accumulated commits.
- **Fix that worked:** `ALTER TABLE rva.gold_queue_sessions EXECUTE optimize` (Trino) merged 208 files → **1 data file, 0 delete files** (~249s). Re-running queue_hourly against the clean snapshot **FINISHED in ~60s** (was 20-min timeout). Note: the first re-run still hung because it had pinned a *pre-compaction* snapshot; cancel + re-run against the clean snapshot was required.
- **Catch:** streaming keeps committing `overwrite` every 30s → delete files **re-accumulate continuously**. A one-off compaction is not enough; it must be **scheduled**.

#### Scope — which tables need this (ALL upsert fact tables, not just queue)
| Table | Mode | Batch/Trino read? | Needs scheduled compaction |
|---|---|---|---|
| `gold_queue_sessions` | upsert | yes (queue_hourly/daily) | ✅ **high** (confirmed failure) |
| `gold_alerts` | upsert | yes (alert serving + executive) | ✅ **high** (will stall like queue) |
| `gold_track_summary_v2` | upsert | yes (dwell_daily) | ✅ **high** (will stall like queue) |
| `gold_alert_events` | upsert | via Trino/API | ✅ medium |
| `gold_camera_hourly_metrics` | upsert | via Trino/API | ✅ medium |
| `gold_camera_daily_metrics` | upsert | via Trino/API | ✅ medium |
| `gold_camera_daily_dwell` | upsert | via Trino/API | ✅ medium |
| `silver_detections_v2`, `silver_detection_parse_errors`, `bronze_raw` | append | — | ❌ not affected |

---

## 3. Remediation backlog (deferred — implement later)

Ordered by expected impact / effort. None of these are SQL tuning — optimizing the serving SQL will NOT help, because compute is not the bottleneck.

| # | Action | Targets | Effort | Notes |
|---|--------|---------|--------|-------|
| R1 | **Keep `infer-source-parallelism: false`** (done) + verify after restart | §2.3 | done | Confirm queue DAG no longer fails; each batch job runs p=1. |
| R2 | **Remove or shard the global batch lock** so independent domains run in parallel | §2.1 | M | Per-domain lock, or per-target-table lock. Beware concurrent writes to the *same* serving table (keep lock per table, not global). |
| **R3** ⭐ | **Scheduled compaction of ALL upsert fact tables** — `ALTER TABLE x EXECUTE optimize` (merges data files **and** position-deletes) + `expire_snapshots` + `remove_orphan_files`, on a cron. Covers the 7 Gold upsert tables in §2.5; skip append-only silver/bronze. | §2.5, §2.4 | M | **Highest priority** — without it, every upsert-table batch read re-stalls as deletes re-accumulate. Implement as the missing `services/gold_serving/maintenance.py` + an Airflow `gold_maintenance` DAG. Must serialize with streaming writers (commit-conflict retry) and the batch lock. Verify: `$files` shows few data files + 0 delete files after run. |
| R4 | **Local MinIO for dev** instead of remote AWS S3 | §2.4 | M | Biggest latency cut for dev; biggest infra change. Keep AWS for prod only. |
| R5 | **Warm session cluster / reuse** instead of cold batch submit per task | §2.2 | L | E.g. a long-lived SQL gateway or pre-warmed job; avoids jar load + catalog init per task. |
| R6 | **Batch domains into fewer jobs** (one StatementSet covering multiple targets) | §2.2, §2.1 | M | Amortizes bootstrap across targets; fewer lock acquisitions. |

---

## 4. What is NOT the problem
- Not the serving SQL logic / joins (data volume tiny).
- Not Flink streaming throughput (those jobs are healthy).
- Not the partition refactor (2026-06-14/15) — the 7 fact tables are now correctly identity-partitioned; this latency issue is pre-existing and orthogonal. See `07_FACT_TABLE_PARTITION_ANALYSIS_2026-06-14.md`.

---

## 5. Immediate next step (already actionable)
Before re-triggering any upsert-sourced domain (`queue`, `alert`, `dwell`), **compact its source table first** (`ALTER TABLE rva.<table> EXECUTE optimize`), then submit the batch job against the resulting clean snapshot. Append-only domains (`traffic`, `zone`, `heatmap`) need no compaction. Then `gold_serving_executive` → `gold_quality_checks`. R2–R6 remain the backlog; **R3 is now top priority** because the fix is manual/one-off until the maintenance DAG exists.

---

## 6. Incident log — `gold_serving_queue` (2026-06-15 → 06-16)

1. After partition rebuild + restart, `gold_serving_queue` DAG failed; `queue_hourly` Flink batch job FAILED in ~361 ms with source inferred parallelism=100 on 16 slots (§2.3).
2. Applied `infer-source-parallelism: false` + restart → queue source now p=1, but the job **ran 20 min then FAILED** with source reading 0 records (no SourceCoordinator because Iceberg here uses the *legacy* source, not FLIP-27 — a red herring).
3. Suspected small-files; `gold_queue_sessions` had 242 snapshots / 208 data files / ~742 live rows. Ran `EXECUTE optimize` → 1 data file, 0 delete files (~249 s); Trino `count(*)` (which had hung) returned instantly.
4. Re-ran queue_hourly — **still hung**, because that run pinned a *pre-compaction* snapshot full of delete files. TM thread dump pinpointed the true cause: `BaseDeleteLoader.loadPositionDeletes` / `DeleteFilter.applyPosDeletes` (§2.5) — merge-on-read on the upsert table.
5. Cancelled the stuck job; current snapshot was clean (1 data file, 0 deletes); re-submitted → **FINISHED in ~60 s**, audit `ok`, `gold_serving_queue_hourly` = 36 rows.

**Lessons:** (a) the real cost is merge-on-read delete application on upsert tables, not data-file count alone; (b) compaction must precede the read **and** the read must pin a post-compaction snapshot; (c) because streaming re-accumulates deletes every 30 s, compaction must be scheduled (R3); (d) the same fix applies to `gold_alerts` and `gold_track_summary_v2` before their serving domains are run.
