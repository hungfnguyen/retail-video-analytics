# 08 — Serving DAG Latency: Analysis & Remediation Backlog

**Date:** 2026-06-15
**Status:** Analysis only — remediation deferred (implement later)
**Scope:** `gold_serving_*` Airflow DAGs (traffic, zone, heatmap, dwell, queue, alert, executive) that run Flink **batch** jobs via `services/flink-jobs/python/submit_batch_job.py`.

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

### 2.3 Iceberg source-parallelism inference blow-up — FIXED 2026-06-15
- Iceberg's Flink source infers scan parallelism = split count (cap 100), **independent** of the adaptive batch scheduler.
- Streaming jobs commit a small file every 30s → fact tables (e.g. `gold_queue_sessions`) accumulate ~100 tiny files → batch scan inferred **parallelism=100** on a **16-slot** cluster.
- Result: slot-request waves + `slot.request.timeout=120000` (2 min) stalls, and the `gold_serving_queue` batch job **FAILED** outright.
- **Fix applied:** `table.exec.iceberg.infer-source-parallelism: false` in `infrastructure/flink/conf/flink-conf.yaml` (forces scan to honour `parallelism.default=1`). Requires cluster restart to take effect.
- Note: this is the Iceberg-specific complement to the already-present `execution.batch.adaptive.auto-parallelism.enabled: false` (which alone did NOT cover Iceberg's own inference).

### 2.4 Remote AWS S3 latency (ap-southeast-2)
- Storage is real AWS S3 (`s3.ap-southeast-2.amazonaws.com`), not local MinIO.
- Every manifest list, parquet read, and snapshot commit is an **HTTPS round-trip over the internet**.
- Small-files proliferation (from 30s streaming commits) multiplies the number of round-trips per scan/commit.

---

## 3. Remediation backlog (deferred — implement later)

Ordered by expected impact / effort. None of these are SQL tuning — optimizing the serving SQL will NOT help, because compute is not the bottleneck.

| # | Action | Targets | Effort | Notes |
|---|--------|---------|--------|-------|
| R1 | **Keep `infer-source-parallelism: false`** (done) + verify after restart | §2.3 | done | Confirm queue DAG no longer fails; each batch job runs p=1. |
| R2 | **Remove or shard the global batch lock** so independent domains run in parallel | §2.1 | M | Per-domain lock, or per-target-table lock. Beware concurrent writes to the *same* serving table (keep lock per table, not global). |
| R3 | **Small-file compaction** on streaming fact tables (Iceberg `rewrite_data_files`) on a schedule | §2.4, §2.3 | M | Fewer files → fewer S3 round-trips → faster scans + smaller inferred parallelism. |
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
After the next cluster restart (which loads the `infer-source-parallelism` fix), re-trigger `gold_serving_{traffic,zone,heatmap,dwell,queue}` → `gold_serving_executive` → `gold_quality_checks`. The queue DAG should now succeed and each batch job should schedule a single subtask. R2–R6 remain as the backlog to make DAGs genuinely fast.
