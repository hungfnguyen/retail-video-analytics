from __future__ import annotations

import pytest
from fastapi import HTTPException

from rva_api.api.media import live_video


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
