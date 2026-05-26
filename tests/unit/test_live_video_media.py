from __future__ import annotations

import asyncio
import base64

import pytest
from aiortc import RTCPeerConnection
from fastapi import HTTPException

from rva_api.api.media import live_video
from rva_api.api.media import live_webrtc


JPEG_1X1 = (
    b"/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////"
    b"////////////////////////////////////////////////////////2wBDAf////"
    b"//////////////////////////////////////////////////////////////wAARCA"
    b"ABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAA"
    b"AAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9"
    b"oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/xAAUEQ"
    b"EAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAA"
    b"A/9oACAEBAAY/Al//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2g"
    b"AMAwEAAgADAAAAEP/EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EA"
    b"BQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EABQQAQAAAAAAAAAAAAAAA"
    b"AAAABD/2gAIAQEAAT8QH//Z"
)


def test_frame_path_uses_configured_media_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("RVA_LIVE_MEDIA_DIR", str(tmp_path))

    assert live_video._frame_path("cam_01") == tmp_path / "cam_01.jpg"


def test_frame_path_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("RVA_LIVE_MEDIA_DIR", str(tmp_path))

    with pytest.raises(HTTPException) as exc_info:
        live_video._frame_path("../cam_01")

    assert exc_info.value.status_code == 400


def test_mjpeg_frames_yields_jpeg_part(monkeypatch, tmp_path):
    frame_path = tmp_path / "cam_01.jpg"
    frame_path.write_bytes(b"jpeg-bytes")
    monkeypatch.setenv("RVA_LIVE_MEDIA_POLL_INTERVAL_SEC", "0.02")

    stream = live_video._mjpeg_frames(frame_path)
    try:
        part = next(stream)
    finally:
        stream.close()

    assert part.startswith(b"--frame\r\n")
    assert b"Content-Type: image/jpeg\r\n" in part
    assert b"Content-Length: 10\r\n" in part
    assert part.endswith(b"jpeg-bytes\r\n")


def test_webrtc_fps_env_is_clamped(monkeypatch):
    monkeypatch.setenv("RVA_WEBRTC_VIDEO_FPS", "120")

    assert live_webrtc._webrtc_fps() == 30.0


def test_webrtc_dependency_guard_raises_503(monkeypatch):
    monkeypatch.setattr(live_webrtc, "_WEBRTC_IMPORT_ERROR", ImportError("missing"))

    with pytest.raises(HTTPException) as exc_info:
        live_webrtc._ensure_webrtc_available()

    assert exc_info.value.status_code == 503


def test_webrtc_offer_endpoint_returns_answer(monkeypatch, tmp_path):
    monkeypatch.setenv("RVA_LIVE_MEDIA_DIR", str(tmp_path))
    (tmp_path / "cam_01.jpg").write_bytes(base64.b64decode(JPEG_1X1))

    async def run_offer() -> None:
        client_pc = RTCPeerConnection()
        client_pc.addTransceiver("video", direction="recvonly")
        offer = await client_pc.createOffer()
        await client_pc.setLocalDescription(offer)

        try:
            answer = await live_webrtc.create_webrtc_offer(
                "cam_01",
                live_webrtc.WebRTCOffer(
                    sdp=client_pc.localDescription.sdp,
                    type=client_pc.localDescription.type,
                ),
            )
            assert answer.type == "answer"
            assert answer.transport == "webrtc"
            assert "m=video" in answer.sdp
        finally:
            await client_pc.close()
            await live_webrtc.close_peer_connections()

    asyncio.run(run_offer())
