from __future__ import annotations

import os
import re
import time
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

router = APIRouter(prefix="/media/live", tags=["media"])

BOUNDARY = "frame"
CAMERA_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def _default_media_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "configs" / "cameras.yaml").exists():
            return parent / "runtime" / "live_frames"
    return Path("runtime/live_frames")


def _media_dir() -> Path:
    configured = os.getenv("RVA_LIVE_MEDIA_DIR") or os.getenv("LIVE_MEDIA_DIR")
    return Path(configured) if configured else _default_media_dir()


def _frame_path(camera_id: str) -> Path:
    if not CAMERA_ID_PATTERN.fullmatch(camera_id):
        raise HTTPException(status_code=400, detail="Invalid camera_id")
    return _media_dir() / f"{camera_id}.jpg"


def _wait_for_frame(path: Path) -> Path:
    timeout_sec = float(os.getenv("RVA_LIVE_MEDIA_START_TIMEOUT_SEC", "2.0"))
    deadline = time.monotonic() + max(timeout_sec, 0.0)
    while time.monotonic() <= deadline:
        if path.exists():
            return path
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


@router.get("/{camera_id}/snapshot.jpg")
def get_live_snapshot(camera_id: str) -> FileResponse:
    path = _wait_for_frame(_frame_path(camera_id))
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{camera_id}/stream")
def get_live_stream(camera_id: str) -> StreamingResponse:
    path = _wait_for_frame(_frame_path(camera_id))
    return StreamingResponse(
        _mjpeg_frames(path),
        media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
        headers={"Cache-Control": "no-store"},
    )
