# Thesis Scope

## Goal

The project demonstrates a Data Engineering pipeline for retail video analytics. Computer vision is used to extract structured metadata from camera/video frames. The main engineering focus is ingestion, stream processing, realtime serving, lakehouse storage, SQL analytics, and dashboard delivery.

## Implemented Scope

The current implementation includes:

- Multi-camera video processing from `configs/cameras.yaml`.
- Person detection and tracking with YOLO11 and BoTSORT/ByteTrack.
- Metadata publishing to Apache Pulsar.
- Dual-path Flink processing:
  - realtime path to Redis;
  - lakehouse path to Iceberg tables on AWS S3.
- Dead-letter routing for invalid realtime events.
- Trino queries over Iceberg tables.
- FastAPI live dashboard and media gateway.
- React frontend for Live, Analytics, and System pages.

## Out of Scope for Current Build

The current build does not include:

- Raw full-frame video as analytical storage.
- A separate operational relational database.
- A separate dashboarding service outside the React application.
- A separate metrics scraping platform.
- Person re-identification across stores.
- Model accuracy benchmarking against a labeled dataset.

## Success Criteria

| Area | Criteria |
|---|---|
| Vision | Produces detection events and annotated live frames |
| Messaging | Pulsar receives metadata events per camera |
| Realtime | Redis has current count, active tracks, heatmap, latest frame metadata |
| Lakehouse | Bronze, Silver, and Gold Iceberg tables receive data |
| Query | Trino can query all implemented lakehouse tables |
| Serving | FastAPI returns live dashboard JSON and serves media |
| Frontend | Live dashboard displays realtime video and metrics |
| Storage | AWS S3 contains Iceberg warehouse and optional media objects |
