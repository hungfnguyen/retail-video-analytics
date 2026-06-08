from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from rva_api.api.v1.live import (
    _active_track_count,
    _get_redis_client,
    _media_latency_ms,
    _load_camera_config,
    _media_status,
    _pipeline_health,
    _read_media_metadata,
    _safe_float,
    _safe_int,
)
from rva_api.schemas.system import SystemDashboardData

router = APIRouter(prefix="/system", tags=["system"])

FLOW_STEPS = [
    ("pulsar", "Vision Edge"),
    ("pulsar", "Apache Pulsar"),
    ("flink", "Apache Flink"),
    ("redis", "Iceberg / Redis"),
    ("fastapi", "FastAPI BFF"),
    ("fastapi", "UI Web SPA"),
]


def _default_logs_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "logs").exists():
            return parent / "logs"
    return Path("logs")


def _read_json(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _live_snapshot(camera_id: str) -> tuple[dict[str, Any], int, int, str]:
    try:
        client = _get_redis_client()
        frame = _read_json(client.get(f"live:frame:{camera_id}"))
        count = _safe_int(client.get(f"stats:count:{camera_id}"))
        active_tracks = _active_track_count(client, camera_id)
        return frame, count, active_tracks, "ok"
    except Exception:
        return {}, 0, 0, "down"


def _throughput_points(
    now: datetime,
    frame: dict[str, Any],
    media_metadata: dict[str, Any],
    current_count: int,
    active_tracks: int,
) -> list[dict[str, Any]]:
    media_status = _media_status(media_metadata, _media_latency_ms(media_metadata))
    if not frame and media_status == "missing":
        return []

    detections = frame.get("detections", [])
    detection_count = len(detections) if isinstance(detections, list) else 0
    events = max(current_count, active_tracks, detection_count)
    frames = _safe_float(media_metadata.get("processing_fps")) or _safe_float(
        media_metadata.get("publish_fps")
    )

    return [{"time": now.strftime("%H:%M"), "events": events, "frames": frames}]


def _lag_points(
    now: datetime, media_metadata: dict[str, Any], api_latency_ms: int
) -> list[dict[str, Any]]:
    media_latency_ms = _media_latency_ms(media_metadata)
    if media_latency_ms is None:
        return []

    return [
        {
            "time": now.strftime("%H:%M"),
            "backlog": _safe_int(media_metadata.get("reader_queue_size")),
            "lag": media_latency_ms,
            "api": api_latency_ms,
        }
    ]


def _gpu_free_ratio(media_metadata: dict[str, Any]) -> float:
    gpu_memory = media_metadata.get("gpu_memory")
    if not isinstance(gpu_memory, dict):
        return 0.0
    return _safe_float(gpu_memory.get("free_ratio"))


def _zone_count_total(media_metadata: dict[str, Any]) -> int:
    zone_counts = media_metadata.get("zone_counts")
    if not isinstance(zone_counts, list):
        return 0
    return sum(
        _safe_int(zone.get("count"))
        for zone in zone_counts
        if isinstance(zone, dict)
    )


def _vision_runtime_rows(cameras: list[dict[str, Any]], fallback_camera_id: str) -> list[dict[str, Any]]:
    candidates = cameras or [{"camera_id": fallback_camera_id, "name": fallback_camera_id}]
    rows: list[dict[str, Any]] = []
    for camera in candidates:
        camera_id = str(camera.get("camera_id") or "")
        if not camera_id:
            continue
        metadata = _read_media_metadata(camera_id)
        rows.append(
            {
                "camera_id": camera_id,
                "camera_name": str(camera.get("name") or camera_id),
                "processing_fps": _safe_float(metadata.get("processing_fps")),
                "detector_fps_target": _safe_float(metadata.get("detector_fps_target")),
                "inference_ms": _safe_int(metadata.get("inference_ms")),
                "tracking_ms": _safe_int(metadata.get("tracking_ms")),
                "zone_ms": _safe_int(metadata.get("zone_ms")),
                "reader_queue_size": _safe_int(metadata.get("reader_queue_size")),
                "reader_drop_count": _safe_int(metadata.get("reader_drop_count")),
                "dropped_frames_since_last": _safe_int(metadata.get("dropped_frames_since_last")),
                "gpu_free_ratio": _gpu_free_ratio(metadata),
                "gpu_guard_skipped": _safe_int(metadata.get("gpu_guard_skipped")),
                "stable_track_count": _safe_int(metadata.get("stable_track_count")),
                "predicted_tracks_count": _safe_int(metadata.get("predicted_tracks_count")),
                "id_switch_suspect_count": _safe_int(metadata.get("id_switch_suspect_count")),
                "zone_count_total": _zone_count_total(metadata),
            }
        )
    return rows


def _container_rows(services: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "name": str(service["service"]),
            "status": str(service["status"]).title(),
            "cpu": "n/a",
            "memory": "n/a",
            "uptime": "n/a",
        }
        for service in services
    ]


def _parse_log_line(service: str, line: str) -> dict[str, str] | None:
    message = line.strip()
    if not message:
        return None

    level = "INFO"
    upper_message = message.upper()
    if "ERROR" in upper_message:
        level = "ERROR"
    elif "WARN" in upper_message:
        level = "WARN"

    return {
        "time": "",
        "level": level,
        "service": service,
        "message": message[-220:],
    }


def _tail_lines(path: Path, max_bytes: int = 16_384) -> list[str]:
    try:
        with path.open("rb") as file:
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(max(0, size - max_bytes))
            raw = file.read()
    except OSError:
        return []
    return raw.decode("utf-8", errors="ignore").splitlines()


def _recent_logs(limit: int = 6) -> list[dict[str, str]]:
    logs_dir = Path(os.getenv("RVA_LOGS_DIR", str(_default_logs_dir())))
    if not logs_dir.exists():
        return []

    files = [
        path
        for path in logs_dir.rglob("*")
        if path.is_file() and path.stat().st_size > 0
    ]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    entries: list[dict[str, str]] = []
    for path in files[:8]:
        service = path.relative_to(logs_dir).parts[0] if path.parts else "system"
        for line in reversed(_tail_lines(path)[-20:]):
            entry = _parse_log_line(service, line)
            if entry is not None:
                entries.append(entry)
            if len(entries) >= limit:
                return entries
    return entries


def _flow(services: list[dict[str, Any]]) -> list[dict[str, str]]:
    status_by_service = {
        str(service["service"]): str(service["status"]) for service in services
    }
    return [
        {"name": name, "status": status_by_service.get(service, "warning")}
        for service, name in FLOW_STEPS
    ]


@router.get("/dashboard", response_model=SystemDashboardData)
def get_system_dashboard(camera_id: str = "cam_01") -> SystemDashboardData:
    now = datetime.now(timezone.utc)
    frame, current_count, active_tracks, redis_status = _live_snapshot(camera_id)
    media_metadata = _read_media_metadata(camera_id)
    cameras = _load_camera_config()
    services = _pipeline_health(
        now, 0, "stable" if frame else "warning", redis_status=redis_status
    )
    fastapi_health = next(
        service for service in services if service["service"] == "fastapi"
    )

    data = {
        "generated_at": now.isoformat(),
        "pipeline_health": services,
        "throughput": _throughput_points(
            now, frame, media_metadata, current_count, active_tracks
        ),
        "lag": _lag_points(now, media_metadata, _safe_int(fastapi_health["latency_ms"])),
        "vision_runtime": _vision_runtime_rows(cameras, camera_id),
        "containers": _container_rows(services),
        "logs": _recent_logs(),
        "flow": _flow(services),
    }
    return SystemDashboardData.model_validate(data)
