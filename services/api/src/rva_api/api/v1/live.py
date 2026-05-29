from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from core.settings import load_yaml_config
from rva_api.schemas.live import LiveDashboardData
from storage import RedisClientConfig, create_redis_client

router = APIRouter(prefix="/live", tags=["live"])

GRID_W = 64
GRID_H = 48
ZONE_ROWS = ["A1", "A2", "B1", "B2", "C1", "C2"]
ZONE_COLS = 7
HEATMAP_TOP_N = 80
STALE_FRAME_MS = 10_000
MEDIA_STALE_MS = 3_000
METADATA_FRESH_MS = 1_500
METADATA_STALE_MS = 5_000
HEALTH_CHECK_TIMEOUT_SECONDS = 0.1

_redis_client: Any | None = None


def _redis_config() -> RedisClientConfig:
    return RedisClientConfig(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD") or None,
        db=int(os.getenv("REDIS_DB", "0")),
    )


def _get_redis_client() -> Any:
    global _redis_client

    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None

    _redis_client = create_redis_client(_redis_config())
    if _redis_client is None:
        raise HTTPException(
            status_code=503, detail="Redis realtime state is unavailable"
        )
    return _redis_client


def _load_camera_config() -> list[dict[str, Any]]:
    config_path = Path(os.getenv("RVA_CAMERA_CONFIG", "configs/cameras.yaml"))
    config = load_yaml_config(config_path)
    cameras = config.get("cameras", [])
    if not isinstance(cameras, list):
        return []
    return [
        camera
        for camera in cameras
        if isinstance(camera, dict) and camera.get("enabled", True)
    ]


def _camera_status(frame: dict[str, Any] | None, latency_ms: int | None) -> str:
    if frame is None:
        return "warning"
    if latency_ms is None or latency_ms > STALE_FRAME_MS:
        return "warning"
    return "online"


def _build_store(
    frame: dict[str, Any] | None, cameras: list[dict[str, Any]], camera_id: str
) -> dict[str, str]:
    store_id = str((frame or {}).get("store_id") or "")
    if not store_id:
        matched = next(
            (camera for camera in cameras if camera.get("camera_id") == camera_id), None
        )
        store_id = str((matched or {}).get("store_id") or "store_001")
    return {
        "store_id": store_id,
        "name": store_id.replace("_", " ").title(),
        "location": "",
    }


def _build_cameras(
    cameras: list[dict[str, Any]],
    selected_camera_id: str,
    selected_frame: dict[str, Any] | None,
    selected_latency_ms: int | None,
) -> list[dict[str, Any]]:
    if not cameras:
        return [
            {
                "camera_id": selected_camera_id,
                "store_id": str((selected_frame or {}).get("store_id") or "store_001"),
                "name": selected_camera_id,
                "zone": selected_camera_id,
                "source_type": "video_file",
                "status": _camera_status(selected_frame, selected_latency_ms),
            }
        ]

    result = []
    for camera in cameras:
        camera_id = str(camera.get("camera_id", ""))
        status = (
            _camera_status(selected_frame, selected_latency_ms)
            if camera_id == selected_camera_id
            else "warning"
        )
        result.append(
            {
                "camera_id": camera_id,
                "store_id": str(camera.get("store_id", "store_001")),
                "name": str(camera.get("name") or camera_id),
                "zone": str(camera.get("zone") or camera.get("name") or camera_id),
                "source_type": str(camera.get("source_type") or "video_file"),
                "status": status,
            }
        )
    return result


def _parse_live_frame(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        frame = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Invalid live frame JSON in Redis")
    if not isinstance(frame, dict):
        raise HTTPException(
            status_code=502, detail="Invalid live frame payload in Redis"
        )
    return frame


def _default_media_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "configs" / "cameras.yaml").exists():
            return parent / "runtime" / "live_frames"
    return Path("runtime/live_frames")


def _media_dir() -> Path:
    configured = os.getenv("RVA_LIVE_MEDIA_DIR") or os.getenv("LIVE_MEDIA_DIR")
    return Path(configured) if configured else _default_media_dir()


def _read_media_metadata(camera_id: str) -> dict[str, Any]:
    metadata_path = _media_dir() / f"{camera_id}.json"
    try:
        raw = metadata_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {}

    try:
        metadata = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _media_latency_ms(metadata: dict[str, Any]) -> int | None:
    updated_at = metadata.get("updated_at_epoch_ms")
    try:
        updated_at_ms = int(updated_at)
    except (TypeError, ValueError):
        return None
    return max(0, int(time.time() * 1000) - updated_at_ms)


def _media_status(metadata: dict[str, Any], media_latency_ms: int | None) -> str:
    if not metadata:
        return "missing"
    if media_latency_ms is None or media_latency_ms > MEDIA_STALE_MS:
        return "warning"
    return "online"


def _metadata_status(frame: dict[str, Any] | None, latency_ms: int | None) -> str:
    if frame is None or latency_ms is None:
        return "missing"
    if latency_ms <= METADATA_FRESH_MS:
        return "fresh"
    if latency_ms <= METADATA_STALE_MS:
        return "lagging"
    return "stale"


def _parse_capture_ts(frame: dict[str, Any] | None) -> datetime | None:
    if frame is None:
        return None
    raw = frame.get("capture_ts")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latency_ms(frame: dict[str, Any] | None, now: datetime) -> int | None:
    capture_ts = _parse_capture_ts(frame)
    if capture_ts is None:
        return None
    return max(0, int((now - capture_ts).total_seconds() * 1000))


def _safe_int(raw: Any, default: int = 0) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _safe_float(raw: Any, default: float = 0.0) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default



def _redis_get(client: Any, key: str, error_detail: str) -> Any:
    try:
        return client.get(key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=error_detail) from exc


def _is_fresh_latency(latency_ms: int | None) -> bool:
    return latency_ms is not None and latency_ms <= STALE_FRAME_MS


def _media_current_count(
    media_metadata: dict[str, Any], media_status: str
) -> int | None:
    if media_status != "online":
        return None

    for key in ("tracked_objects_count", "detections_count"):
        if key in media_metadata:
            return max(0, _safe_int(media_metadata.get(key)))
    return None


def _resolve_current_count(
    client: Any,
    camera_id: str,
    detections: list[dict[str, Any]],
    metadata_latency_ms: int | None,
    media_metadata: dict[str, Any],
    media_status: str,
) -> tuple[int, str]:
    media_count = _media_current_count(media_metadata, media_status)
    if media_count is not None:
        return media_count, "camera_realtime"

    raw_count = _redis_get(
        client,
        f"stats:count:{camera_id}",
        "Cannot read realtime count from Redis",
    )
    if raw_count is not None:
        return _safe_int(raw_count), "redis"

    if _is_fresh_latency(metadata_latency_ms):
        return len(detections), "live_frame_fallback"

    return 0, "missing"


def _active_track_count(client: Any, camera_id: str) -> int:
    try:
        return sum(1 for _ in client.scan_iter(match=f"track:active:{camera_id}:*"))
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Cannot read active tracks from Redis"
        ) from exc


def _read_heatmap(client: Any, camera_id: str) -> list[tuple[int, int, float]]:
    try:
        members = client.zrevrange(
            f"heatmap:live:{camera_id}",
            0,
            HEATMAP_TOP_N - 1,
            withscores=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Cannot read heatmap from Redis"
        ) from exc

    cells: list[tuple[int, int, float]] = []
    for member, score in members:
        if isinstance(member, bytes):
            member = member.decode("utf-8")
        if not isinstance(member, str) or "," not in member:
            continue
        gx_raw, gy_raw = member.split(",", 1)
        gx = max(0, min(GRID_W - 1, _safe_int(gx_raw)))
        gy = max(0, min(GRID_H - 1, _safe_int(gy_raw)))
        cells.append((gx, gy, _safe_float(score)))
    return cells


def _heatmap_points(cells: list[tuple[int, int, float]]) -> list[dict[str, float]]:
    max_score = max((score for _, _, score in cells), default=0.0)
    if max_score <= 0.0:
        return []
    return [
        {
            "x": (gx + 0.5) / GRID_W,
            "y": (gy + 0.5) / GRID_H,
            "intensity": min(1.0, score / max_score),
        }
        for gx, gy, score in cells
    ]


def _zone_heatmap(cells: list[tuple[int, int, float]]) -> list[dict[str, int | str]]:
    zone_scores = {
        (row, col): 0.0 for row in ZONE_ROWS for col in range(1, ZONE_COLS + 1)
    }
    for gx, gy, score in cells:
        row_index = min(len(ZONE_ROWS) - 1, int(gy / (GRID_H / len(ZONE_ROWS))))
        col = min(ZONE_COLS, int(gx / (GRID_W / ZONE_COLS)) + 1)
        zone_scores[(ZONE_ROWS[row_index], col)] += score

    max_score = max(zone_scores.values(), default=0.0)
    result = []
    for row in ZONE_ROWS:
        for col in range(1, ZONE_COLS + 1):
            score = zone_scores[(row, col)]
            value = int(round((score / max_score) * 100)) if max_score > 0 else 0
            result.append({"zone_row": row, "zone_col": col, "value": value})
    return result


def _detections_from_frame(frame: dict[str, Any] | None) -> list[dict[str, Any]]:
    if frame is None:
        return []
    detections = frame.get("detections", [])
    if not isinstance(detections, list):
        return []

    result = []
    for det in detections:
        if not isinstance(det, dict) or det.get("track_id") is None:
            continue
        bbox_norm = det.get("bbox_norm")
        if not isinstance(bbox_norm, dict):
            continue
        result.append(
            {
                "track_id": _safe_int(det.get("track_id")),
                "label": "person",
                "confidence": _safe_float(det.get("confidence")),
                "bbox_norm": {
                    "x": _safe_float(bbox_norm.get("x")),
                    "y": _safe_float(bbox_norm.get("y")),
                    "w": _safe_float(bbox_norm.get("w")),
                    "h": _safe_float(bbox_norm.get("h")),
                },
            }
        )
    return result


def _empty_traffic() -> list[dict[str, int | str]]:
    return []


def _health_endpoint(raw: str) -> tuple[str, int] | None:
    parsed = urlparse(raw)
    if parsed.hostname:
        if parsed.port:
            return parsed.hostname, parsed.port
        if parsed.scheme == "https":
            return parsed.hostname, 443
        if parsed.scheme == "http":
            return parsed.hostname, 80
        if parsed.scheme == "pulsar":
            return parsed.hostname, 6650
        return None

    if ":" not in raw:
        return None

    host, port_raw = raw.rsplit(":", 1)
    try:
        return host, int(port_raw)
    except ValueError:
        return None


def _tcp_health(raw: str) -> tuple[str, int]:
    endpoint = _health_endpoint(raw)
    if endpoint is None:
        return "warning", 0

    start = time.perf_counter()
    try:
        with socket.create_connection(endpoint, timeout=HEALTH_CHECK_TIMEOUT_SECONDS):
            latency_ms = max(0, int((time.perf_counter() - start) * 1000))
            return "ok", latency_ms
    except OSError:
        return "down", 0


def _service_health_entry(
    service: str,
    display_name: str,
    role: str,
    status: str,
    now: datetime,
    latency_ms: int,
) -> dict[str, Any]:
    return {
        "service": service,
        "display_name": display_name,
        "role": role,
        "status": status,
        "last_check_ts": now.isoformat(),
        "latency_ms": latency_ms,
    }


def _pipeline_health(
    now: datetime,
    redis_latency_ms: int,
    frame_status: str,
    redis_status: str = "ok",
) -> list[dict[str, Any]]:
    pulsar_status, pulsar_latency_ms = _tcp_health(
        os.getenv("PULSAR_SERVICE_URL", "pulsar://localhost:6650")
    )
    flink_status, flink_latency_ms = _tcp_health(
        os.getenv("FLINK_REST_URL", "http://localhost:8081")
    )
    minio_status, minio_latency_ms = _tcp_health(
        os.getenv("MINIO_SERVER_URL", "http://localhost:9000")
    )
    trino_status, trino_latency_ms = _tcp_health(
        os.getenv("TRINO_URL", "http://localhost:8083")
    )

    return [
        _service_health_entry(
            "pulsar", "Pulsar", "Event Stream", pulsar_status, now, pulsar_latency_ms
        ),
        _service_health_entry(
            "flink", "Flink", "Stream Processing", flink_status, now, flink_latency_ms
        ),
        _service_health_entry(
            "redis", "Redis", "Realtime State", redis_status, now, redis_latency_ms
        ),
        _service_health_entry(
            "minio", "MinIO", "Object Storage", minio_status, now, minio_latency_ms
        ),
        _service_health_entry(
            "trino", "Trino", "SQL Query Engine", trino_status, now, trino_latency_ms
        ),
        _service_health_entry(
            "fastapi",
            "FastAPI",
            "Serving API",
            "ok" if frame_status == "stable" else "warning",
            now,
            0,
        ),
    ]


@router.get("/{camera_id}/dashboard", response_model=LiveDashboardData)
def get_live_dashboard(camera_id: str) -> LiveDashboardData:
    client = _get_redis_client()
    now = datetime.now(timezone.utc)

    start = time.perf_counter()
    try:
        frame = _parse_live_frame(client.get(f"live:frame:{camera_id}"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Cannot read latest frame from Redis"
        ) from exc

    redis_latency_ms = max(0, int((time.perf_counter() - start) * 1000))
    latency_ms = _latency_ms(frame, now)
    media_metadata = _read_media_metadata(camera_id)
    media_latency_ms = _media_latency_ms(media_metadata)
    media_fps = _safe_float(media_metadata.get("publish_fps"))
    media_status = _media_status(media_metadata, media_latency_ms)
    metadata_status = _metadata_status(frame, latency_ms)
    processing_fps = _safe_float(media_metadata.get("processing_fps"))
    inference_ms = _safe_int(media_metadata.get("inference_ms"))
    postprocess_ms = _safe_int(media_metadata.get("postprocess_ms"))
    draw_ms = _safe_int(media_metadata.get("draw_ms"))
    encode_ms = _safe_int(media_metadata.get("encode_ms"))
    jpeg_size_bytes = _safe_int(media_metadata.get("jpeg_size_bytes"))
    reader_queue_size = _safe_int(media_metadata.get("reader_queue_size"))
    reader_drop_count = _safe_int(media_metadata.get("reader_drop_count"))
    status = "stable" if metadata_status in {"fresh", "lagging"} else "warning"

    active_tracks = _active_track_count(client, camera_id)
    heatmap_cells = _read_heatmap(client, camera_id)
    detections = _detections_from_frame(frame)
    current_count, count_source = _resolve_current_count(
        client, camera_id, detections, latency_ms, media_metadata, media_status
    )
    if count_source == "missing":
        status = "warning"
    cameras = _load_camera_config()
    if cameras and camera_id not in {
        str(camera.get("camera_id")) for camera in cameras
    }:
        raise HTTPException(status_code=404, detail="Camera not found")
    store = _build_store(frame, cameras, camera_id)

    frame_id = _safe_int((frame or {}).get("frame_index"), 0)
    capture_ts = str((frame or {}).get("capture_ts") or "")
    media_capture_ts = str(media_metadata.get("capture_ts") or "")
    media_frame_id = _safe_int(media_metadata.get("frame_index"), 0)
    display_frame_id = (
        media_frame_id if media_status == "online" and media_frame_id > 0 else frame_id
    )
    display_capture_ts = (
        media_capture_ts if media_status == "online" and media_capture_ts else capture_ts
    )
    count_updated_at = display_capture_ts if count_source == "camera_realtime" else capture_ts
    image_size = (
        (frame or {}).get("image_size")
        if isinstance((frame or {}).get("image_size"), dict)
        else {}
    )

    data = {
        "store": store,
        "cameras": _build_cameras(cameras, camera_id, frame, latency_ms),
        "selected_camera_id": camera_id,
        "frame": {
            "camera_id": camera_id,
            "frame_id": display_frame_id,
            "capture_ts": display_capture_ts,
            "image_url": (
                f"/media/live/{camera_id}/stream"
                if frame is not None or media_status != "missing"
                else ""
            ),
            "image_size": {
                "width": _safe_int(image_size.get("width"), 0),
                "height": _safe_int(image_size.get("height"), 0),
            },
            "fps": media_fps,
            "latency_ms": latency_ms or 0,
            "media_fps": media_fps,
            "media_latency_ms": media_latency_ms or 0,
            "metadata_latency_ms": latency_ms or 0,
            "metadata_status": metadata_status,
            "media_status": media_status,
            "processing_fps": processing_fps,
            "inference_ms": inference_ms,
            "postprocess_ms": postprocess_ms,
            "draw_ms": draw_ms,
            "encode_ms": encode_ms,
            "jpeg_size_bytes": jpeg_size_bytes,
            "reader_queue_size": reader_queue_size,
            "reader_drop_count": reader_drop_count,
            "detections": detections,
            "heatmap_points": _heatmap_points(heatmap_cells),
        },
        "stats": {
            "camera_id": camera_id,
            "current_count": current_count,
            "count_source": count_source,
            "active_tracks": active_tracks,
            "fps": media_fps,
            "latency_ms": latency_ms or 0,
            "media_fps": media_fps,
            "media_latency_ms": media_latency_ms or 0,
            "metadata_latency_ms": latency_ms or 0,
            "metadata_status": metadata_status,
            "count_change_percent": 0,
            "tracks_change_percent": 0,
            "status": status,
            "updated_at": count_updated_at or now.isoformat(),
        },
        "alerts": [],
        "traffic": _empty_traffic(),
        "traffic_summary": {
            "total_in": 0,
            "total_out": 0,
            "current_total": current_count,
            "peak_count": current_count,
            "peak_time": now.strftime("%H:%M"),
        },
        "zone_heatmap": _zone_heatmap(heatmap_cells),
        "pipeline_health": _pipeline_health(now, redis_latency_ms, status),
    }
    return LiveDashboardData.model_validate(data)
