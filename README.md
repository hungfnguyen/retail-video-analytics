# Retail Video Analytics

Real-time streaming lakehouse platform for retail video analytics.

The system processes **metadata extracted from video streams** and separates two workloads:

* **Realtime operational analytics** using Redis.
* **Historical analytics** using Apache Iceberg on AWS S3 and Trino.

The project focuses on end-to-end streaming data engineering, including event-time processing, stateful stream processing, Medallion architecture, realtime serving, and analytical workloads.

## Demo

[Project UI & Demo Videos](https://drive.google.com/drive/u/0/folders/1NBOTVdMPl49KKEQuQbC6C4BTmg5h032I)

### Architecture
![Retail Video Analytics Architecture](docs/images/architecture.png)

## Key Features

* Multi-camera detection and tracking with YOLO11 and ByteTrack.
* Apache Pulsar for event ingestion.
* Apache Flink for event-time and stateful stream processing.
* Redis for low-latency realtime state.
* Medallion Lakehouse: Bronze → Silver → Gold.
* Apache Iceberg tables stored on AWS S3.
* Trino for historical analytical queries.
* FastAPI backend and React dashboard.
* Queue, zone, heatmap, dwell-time, and alert analytics.
* Docker Compose deployment on AWS EC2.

## Data Flow

```text
Camera
  ↓
Vision Processing
  ↓
Pulsar
  ↓
Flink
  ├──→ Redis → Realtime API / Dashboard
  │
  └──→ Bronze → Silver → Gold → Iceberg/S3 → Trino → Analytics
```

## Tech Stack

| Layer             | Technology              |
| ----------------- | ----------------------- |
| Vision            | YOLO11, ByteTrack       |
| Messaging         | Apache Pulsar           |
| Stream Processing | Apache Flink            |
| Realtime Serving  | Redis                   |
| Lakehouse         | Apache Iceberg          |
| Storage           | AWS S3                  |
| Query Engine      | Trino                   |
| Backend           | FastAPI                 |
| Frontend          | React                   |
| Infrastructure    | Docker Compose, AWS EC2 |

## Run

```bash
uv sync --all-packages

cd frontend
npm install
cd ..

docker compose up -d --build
```

Start Vision:

```bash
uv run --package rva-vision python services/vision/main.py
```

Start API:

```bash
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000
```

Start frontend:

```bash
cd frontend
npm run dev
```

Open:

```text
http://localhost:5173
```

## Documentation

See [`docs/README.md`](docs/README.md) for detailed architecture, runtime services, verification commands, and implementation notes.
