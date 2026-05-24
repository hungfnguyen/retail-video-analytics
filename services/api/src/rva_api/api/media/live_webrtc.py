from __future__ import annotations

import asyncio
import logging
import os
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from rva_api.api.media.live_video import _frame_path, _wait_for_frame

logger = logging.getLogger(__name__)

try:
    import numpy as np
    from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
    from av import VideoFrame
    from PIL import Image

    _WEBRTC_IMPORT_ERROR: ImportError | None = None
except ImportError as exc:  # pragma: no cover - depends on deployment image
    np = None  # type: ignore[assignment]
    RTCPeerConnection = None  # type: ignore[assignment]
    RTCSessionDescription = None  # type: ignore[assignment]
    VideoFrame = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]

    class VideoStreamTrack:  # type: ignore[no-redef]
        pass

    _WEBRTC_IMPORT_ERROR = exc


router = APIRouter(prefix="/media/live", tags=["media"])

VIDEO_CLOCK_RATE = 90_000
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720

_peer_connections: set[Any] = set()


class WebRTCOffer(BaseModel):
    sdp: str
    type: Literal["offer"]


class WebRTCAnswer(BaseModel):
    sdp: str
    type: Literal["answer"]
    transport: Literal["webrtc"] = "webrtc"


def _ensure_webrtc_available() -> None:
    if _WEBRTC_IMPORT_ERROR is not None:
        raise HTTPException(
            status_code=503,
            detail=(
                "WebRTC media serving is unavailable. Install the rva-api "
                "WebRTC dependencies and restart the API service."
            ),
        ) from _WEBRTC_IMPORT_ERROR


def _webrtc_fps() -> float:
    raw = os.getenv("RVA_WEBRTC_VIDEO_FPS") or os.getenv("LIVE_WEBRTC_VIDEO_FPS")
    try:
        fps = float(raw) if raw else 15.0
    except ValueError:
        fps = 15.0
    return max(1.0, min(fps, 30.0))


class LatestJpegVideoTrack(VideoStreamTrack):  # type: ignore[misc]
    """WebRTC track backed by the latest annotated JPEG for one camera.

    This keeps the current Vision contract intact: Vision owns detection,
    tracking, and overlay rendering. The API media gateway reads only the
    latest annotated JPEG and emits a paced video track to the browser.
    """

    kind = "video"

    def __init__(self, frame_path: Path, fps: float) -> None:
        super().__init__()
        self.frame_path = frame_path
        self.fps = fps
        self._period_sec = 1.0 / fps
        self._frame_index = 0
        self._next_frame_at: float | None = None
        self._last_mtime_ns = -1
        self._cached_rgb: Any | None = None

    async def recv(self) -> Any:
        await self._pace()

        rgb = await asyncio.to_thread(self._read_latest_rgb)
        frame = VideoFrame.from_ndarray(rgb, format="rgb24")
        frame.pts = int(self._frame_index * VIDEO_CLOCK_RATE / self.fps)
        frame.time_base = Fraction(1, VIDEO_CLOCK_RATE)
        self._frame_index += 1
        return frame

    async def _pace(self) -> None:
        loop = asyncio.get_running_loop()
        now = loop.time()

        if self._next_frame_at is None:
            self._next_frame_at = now
            return

        self._next_frame_at += self._period_sec
        delay = self._next_frame_at - now
        if delay > 0:
            await asyncio.sleep(delay)
        elif delay < -self._period_sec:
            self._next_frame_at = now

    def _read_latest_rgb(self) -> Any:
        try:
            stat = self.frame_path.stat()
        except FileNotFoundError:
            return self._cached_or_blank()

        if self._cached_rgb is not None and stat.st_mtime_ns == self._last_mtime_ns:
            return self._cached_rgb

        try:
            payload = self.frame_path.read_bytes()
            with Image.open(BytesIO(payload)) as image:
                rgb = np.asarray(image.convert("RGB")).copy()
        except Exception:
            logger.exception("Could not decode live JPEG frame: %s", self.frame_path)
            return self._cached_or_blank()

        self._last_mtime_ns = stat.st_mtime_ns
        self._cached_rgb = rgb
        return rgb

    def _cached_or_blank(self) -> Any:
        if self._cached_rgb is not None:
            return self._cached_rgb
        self._cached_rgb = np.zeros((DEFAULT_HEIGHT, DEFAULT_WIDTH, 3), dtype=np.uint8)
        return self._cached_rgb


@router.post("/{camera_id}/webrtc/offer", response_model=WebRTCAnswer)
async def create_webrtc_offer(camera_id: str, offer: WebRTCOffer) -> WebRTCAnswer:
    _ensure_webrtc_available()

    frame_path = _wait_for_frame(_frame_path(camera_id))
    peer_connection = RTCPeerConnection()
    _peer_connections.add(peer_connection)

    @peer_connection.on("connectionstatechange")
    async def on_connectionstatechange() -> None:
        state = peer_connection.connectionState
        if state in {"failed", "closed", "disconnected"}:
            await _close_peer_connection(peer_connection)

    peer_connection.addTrack(LatestJpegVideoTrack(frame_path, fps=_webrtc_fps()))

    try:
        remote_description = RTCSessionDescription(sdp=offer.sdp, type=offer.type)
        await peer_connection.setRemoteDescription(remote_description)
        answer = await peer_connection.createAnswer()
        await peer_connection.setLocalDescription(answer)
    except Exception as exc:
        await _close_peer_connection(peer_connection)
        raise HTTPException(status_code=400, detail="Invalid WebRTC offer") from exc

    local_description = peer_connection.localDescription
    return WebRTCAnswer(
        sdp=local_description.sdp,
        type=local_description.type,
    )


async def _close_peer_connection(peer_connection: Any) -> None:
    if peer_connection in _peer_connections:
        _peer_connections.discard(peer_connection)
    if peer_connection.connectionState != "closed":
        await peer_connection.close()


async def close_peer_connections() -> None:
    if not _peer_connections:
        return

    await asyncio.gather(
        *[
            _close_peer_connection(peer_connection)
            for peer_connection in list(_peer_connections)
        ],
        return_exceptions=True,
    )
