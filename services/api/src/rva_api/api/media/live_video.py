from __future__ import annotations

import os
import re
import time
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from storage import RedisClientConfig, create_redis_client

router = APIRouter(prefix="/media/live", tags=["media"])

BOUNDARY = "frame"
CAMERA_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_live_media_redis_client = None


def _camera_id(camera_id: str) -> str:
    if not CAMERA_ID_PATTERN.fullmatch(camera_id):
        raise HTTPException(status_code=400, detail="Invalid camera_id")
    return camera_id


def _live_media_transport() -> str:
    return str(
        os.getenv("RVA_LIVE_MEDIA_TRANSPORT")
        or os.getenv("LIVE_MEDIA_TRANSPORT")
        or "file"
    ).strip().lower()


def _live_media_redis_prefix() -> str:
    return str(
        os.getenv("RVA_LIVE_MEDIA_REDIS_PREFIX")
        or os.getenv("LIVE_MEDIA_REDIS_PREFIX")
        or "live:frame"
    )


def _live_media_redis_config() -> RedisClientConfig:
    return RedisClientConfig(
        host=str(
            os.getenv("RVA_LIVE_REDIS_HOST")
            or os.getenv("LIVE_REDIS_HOST")
            or os.getenv("REDIS_HOST", "localhost")
        ),
        port=int(
            os.getenv("RVA_LIVE_REDIS_PORT")
            or os.getenv("LIVE_REDIS_PORT")
            or os.getenv("REDIS_HOST_PORT")
            or os.getenv("REDIS_PORT", "16379")
        ),
        password=os.getenv("RVA_LIVE_REDIS_PASSWORD")
        or os.getenv("LIVE_REDIS_PASSWORD")
        or os.getenv("REDIS_PASSWORD")
        or None,
        db=int(
            os.getenv("RVA_LIVE_REDIS_DB")
            or os.getenv("LIVE_REDIS_DB")
            or os.getenv("REDIS_DB", "0")
        ),
        decode_responses=False,
    )


def _get_live_media_redis_client():
    global _live_media_redis_client
    if _live_media_redis_client is not None:
        return _live_media_redis_client
    _live_media_redis_client = create_redis_client(_live_media_redis_config())
    if _live_media_redis_client is None:
        raise HTTPException(status_code=503, detail="Live media Redis is unavailable")
    return _live_media_redis_client


def _frame_bytes_key(camera_id: str) -> str:
    return f"{_live_media_redis_prefix()}:bytes:{_camera_id(camera_id)}"


def _frame_metadata_key(camera_id: str) -> str:
    return f"{_live_media_redis_prefix()}:meta:{_camera_id(camera_id)}"


def _default_media_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "configs" / "cameras.yaml").exists():
            return parent / "runtime" / "live_frames"
    return Path("runtime/live_frames")


def _media_dir() -> Path:
    configured = os.getenv("RVA_LIVE_MEDIA_DIR") or os.getenv("LIVE_MEDIA_DIR")
    return Path(configured) if configured else _default_media_dir()


def _frame_path(camera_id: str) -> Path:
    return _media_dir() / f"{_camera_id(camera_id)}.jpg"


def _wait_for_frame(path: Path) -> Path:
    timeout_sec = float(os.getenv("RVA_LIVE_MEDIA_START_TIMEOUT_SEC", "2.0"))
    deadline = time.monotonic() + max(timeout_sec, 0.0)
    while time.monotonic() <= deadline:
        if path.exists():
            return path
        time.sleep(0.05)
    raise HTTPException(status_code=404, detail="Live video frame not available")


def _wait_for_frame_bytes(camera_id: str) -> bytes:
    client = _get_live_media_redis_client()
    timeout_sec = float(os.getenv("RVA_LIVE_MEDIA_START_TIMEOUT_SEC", "2.0"))
    deadline = time.monotonic() + max(timeout_sec, 0.0)
    key = _frame_bytes_key(camera_id)
    while time.monotonic() <= deadline:
        payload = client.get(key)
        if payload:
            return payload
        time.sleep(0.05)
    raise HTTPException(status_code=404, detail="Live video frame not available")


def _mjpeg_frames(path: Path) -> Iterator[bytes]:
    last_mtime_ns = -1
    poll_interval_sec = float(os.getenv("RVA_LIVE_MEDIA_POLL_INTERVAL_SEC", "0.1"))

    while True:
        try:
            stat = path.stat()
            if stat.st_mtime_ns != last_mtime_ns:
                frame = path.read_bytes()
                last_mtime_ns = stat.st_mtime_ns
                yield (
                    (
                        f"--{BOUNDARY}\r\n"
                        "Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(frame)}\r\n"
                        "\r\n"
                    ).encode("ascii")
                    + frame
                    + b"\r\n"
                )
        except FileNotFoundError:
            pass

        time.sleep(max(poll_interval_sec, 0.02))


def _mjpeg_frames_redis(camera_id: str) -> Iterator[bytes]:
    client = _get_live_media_redis_client()
    metadata_key = _frame_metadata_key(camera_id)
    frame_key = _frame_bytes_key(camera_id)
    last_metadata = None
    poll_interval_sec = float(os.getenv("RVA_LIVE_MEDIA_POLL_INTERVAL_SEC", "0.1"))

    while True:
        metadata = client.get(metadata_key)
        if metadata and metadata != last_metadata:
            frame = client.get(frame_key)
            if frame:
                last_metadata = metadata
                yield (
                    (
                        f"--{BOUNDARY}\r\n"
                        "Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(frame)}\r\n"
                        "\r\n"
                    ).encode("ascii")
                    + frame
                    + b"\r\n"
                )
        time.sleep(max(poll_interval_sec, 0.02))


@router.get("/{camera_id}/snapshot.jpg")
def get_live_snapshot(camera_id: str) -> Response:
    if _live_media_transport() == "redis":
        frame = _wait_for_frame_bytes(camera_id)
        return Response(
            content=frame,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )
    path = _wait_for_frame(_frame_path(camera_id))
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{camera_id}/stream")
def get_live_stream(camera_id: str) -> StreamingResponse:
    if _live_media_transport() == "redis":
        _camera_id(camera_id)
        _wait_for_frame_bytes(camera_id)
        return StreamingResponse(
            _mjpeg_frames_redis(camera_id),
            media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
            headers={"Cache-Control": "no-store"},
        )
    path = _wait_for_frame(_frame_path(camera_id))
    return StreamingResponse(
        _mjpeg_frames(path),
        media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
        headers={"Cache-Control": "no-store"},
    )
