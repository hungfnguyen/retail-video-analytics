from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/live", tags=["live-media"])


def _api_base_url() -> str:
    return os.getenv("PUBLIC_API_BASE_URL", "http://localhost:8000").rstrip("/")


def _live_frame_dir() -> Path:
    return Path(os.getenv("LIVE_FRAME_OUTPUT_DIR", "data/live_frames"))


def live_frame_stream_url(camera_id: str) -> str:
    return f"{_api_base_url()}/api/v1/live/{camera_id}/stream.mjpg"


def live_frame_latency_ms(camera_id: str, now: datetime) -> int | None:
    frame_path = _live_frame_dir() / f"{camera_id}.jpg"
    if not frame_path.exists():
        return None

    return max(0, int((now.timestamp() - frame_path.stat().st_mtime) * 1000))


@router.get("/{camera_id}/stream.mjpg")
def stream_live_frame(camera_id: str) -> StreamingResponse:
    frame_path = _live_frame_dir() / f"{camera_id}.jpg"

    def generate():
        last_mtime = 0.0
        while True:
            if not frame_path.exists():
                time.sleep(0.2)
                continue

            try:
                mtime = frame_path.stat().st_mtime
                if mtime <= last_mtime:
                    time.sleep(0.04)
                    continue

                frame = frame_path.read_bytes()
                last_mtime = mtime
            except OSError:
                time.sleep(0.04)
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-store\r\n\r\n"
                + frame
                + b"\r\n"
            )

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )
