# Retail Video Analytics — Documentation Index

## Overview

Retail Video Analytics (RVA) is an end-to-end streaming pipeline for real-time people detection, tracking, and density analysis in retail store environments.

### Design: Heatmap-First, No Zones

| Feature | Status | Description |
|---------|--------|-------------|
| **Heatmap Overlay** | Primary | Density visualization directly on video frames |
| **Bounding Boxes** | Primary | Track IDs displayed per detection (P:137, P:200, ...) |
| **Zone Analytics** | Removed | Not needed — heatmap provides full spatial information |

---

## Document Structure

```
docs/
├── README.md                          # This file — documentation index
├── 01_ARCHITECTURE_ANALYSIS.md        # System architecture overview
├── 02_ARCHITECTURE_IMPROVED.md        # Dual-Path architecture (Fast + Slow path)
├── 03_DATABASE_SCHEMA.md              # PostgreSQL & Redis schema (heatmap-first, no zones)
├── 04_VISUALIZATION_REQUIREMENTS.md   # UI & dashboard specifications
├── 05_ACTION_PLAN.md                  # Implementation guide by phase
├── 06_TECH_COMPARISON.md              # Technology decisions and rationale
├── 07_VISION_MODULE_CHANGES.md        # Vision module: FrameSaver & TrackLifecycle
└── 08_PROJECT_STRUCTURE.md            # Monorepo layout & uv workspace
```

---

## Architecture Summary

### Dual-Path Architecture

```
Camera → YOLO11 + BoTSORT
    │
    ├──────────────────────┬──────────────────────┐
    │                      │                      │
    ▼                      ▼                      ▼
Pulsar                  GCS                PostgreSQL
(metadata,            (keyframes,           (track events:
 30 FPS)               1 frame/sec)          start/end/sample)
    │
    ├─────────────────────────┐
    │                         │
    ▼                         ▼
FAST PATH                SLOW PATH
Flink CEP                Flink Batch
(< 1 second)             (90-120 seconds)
    │                         │
    ▼                         ▼
Redis                      Iceberg
(heatmap:live,            (Bronze→Silver→Gold)
 alerts, stats)               │
    │                         ▼
    │                       Trino
    │                         │
    └──────────┬──────────────┘
               │
               ▼
         Streamlit (primary)    +    Grafana (KPI analytics)
         - Live heatmap overlay       - Historical trends
         - Track replay               - Daily summaries
         - Alert panel                - System health
```

### Visualization: Heatmap Overlay on Video

```
┌──────────────────────────────────────────────────────────┐
│                 VIDEO FRAME + HEATMAP                    │
│  ┌────────────────────────────────────────────────────┐  │
│  │                                                    │  │
│  │    ██████████              ███████████████        │  │
│  │   ████HOT█████  P:137    █████████HOT█████ P:200  │  │
│  │    ██████████              ███████████████        │  │
│  │                                                    │  │
│  │          ┌─────┐                                   │  │
│  │          │P:62 │  ← Bounding box + Track ID       │  │
│  │          └─────┘                                   │  │
│  │                                                    │  │
│  └────────────────────────────────────────────────────┘  │
│   Cold ════════════════════════════════════════ Hot      │
└──────────────────────────────────────────────────────────┘
```

---

## Reading Guide

### Recommended order for developers:

1. `01_ARCHITECTURE_ANALYSIS.md` — System architecture and data flow
2. `02_ARCHITECTURE_IMPROVED.md` — Dual-Path design details
3. `07_VISION_MODULE_CHANGES.md` — Vision module components
4. `03_DATABASE_SCHEMA.md` — PostgreSQL & Redis schema
5. `04_VISUALIZATION_REQUIREMENTS.md` — UI specifications
6. `05_ACTION_PLAN.md` — Implementation steps
7. `06_TECH_COMPARISON.md` — Technology decision rationale

---

## Latency Summary

| Path | Latency | Use Case |
|------|---------|----------|
| **Fast Path** | < 1 second | Live heatmap, density alerts |
| **Slow Path** | 90-120 seconds | Historical charts, Grafana dashboards |
| **Frame lookup** | < 2 seconds | View frame at alert time |

---

## Services & Ports

| Service | Port | Purpose |
|---------|------|---------|
| Streamlit | 8501 | Primary dashboard |
| Grafana | 3000 | Analytics dashboard |
| Backend (FastAPI) | 8000 | REST API + WebSocket |
| Flink UI | 8081 | Pipeline monitoring |
| Pulsar Admin | 8084 | Message broker UI |
| GCS Console | cloud | Object storage (console.cloud.google.com) |
| Trino | 8083 | SQL query engine |
