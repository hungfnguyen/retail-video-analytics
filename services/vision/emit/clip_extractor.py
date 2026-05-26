import logging
import os
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

from core.time_utils import ensure_utc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClipCreatedResult:
    schema_version: str
    event_type: str
    pipeline_run_id: str
    alert_id: str
    alert_type: str
    source: dict[str, Any]
    trigger_frame_index: int
    trigger_ts: str
    upload_ts: str
    bucket: str
    clip_s3_key: str
    clip_s3_uri: str
    content_type: str
    clip_duration_sec: float
    frame_count: int
    byte_size: int


class AlertClipExtractor:
    """Best-effort alert clip uploader backed by a small encoded-frame buffer."""

    def __init__(
        self,
        *,
        s3_client: Any,
        bucket: str,
        store_id: str,
        camera_id: str,
        pre_buffer_sec: int = 5,
        post_buffer_sec: int = 5,
        fps: int = 25,
        jpeg_quality: int = 80,
        cooldown_sec: int = 30,
        max_workers: int = 1,
    ):
        self.s3 = s3_client
        self.bucket = bucket
        self.store_id = store_id
        self.camera_id = camera_id
        self.pre_buffer_sec = int(pre_buffer_sec)
        self.post_buffer_sec = int(post_buffer_sec)
        self.fps = max(1, int(fps))
        self.jpeg_quality = int(jpeg_quality)
        self.cooldown_sec = int(cooldown_sec)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="clip-uploader")

        buf_size = max(1, self.pre_buffer_sec * self.fps)
        self._ring: list[bytes | None] = [None] * buf_size
        self._ring_pos = 0

        self._recording: dict[str, Any] | None = None
        self._post_frames: list[bytes] = []
        self._post_remaining = 0
        self._last_trigger_ts: datetime | None = None
        self._futures: list[Future[ClipCreatedResult]] = []

        self.total_triggered = 0
        self.total_uploaded = 0
        self.total_failed = 0

    def feed(self, frame: Any, frame_index: int, capture_ts: datetime) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            logger.warning("Clip buffer JPEG encode failed for frame %d", frame_index)
            return

        body = buf.tobytes()
        self._ring[self._ring_pos % len(self._ring)] = body
        self._ring_pos += 1

        if self._recording is None:
            return

        self._post_frames.append(body)
        self._post_remaining -= 1
        if self._post_remaining <= 0:
            self._submit_clip()

    def trigger(
        self,
        *,
        alert_type: str,
        trigger_frame_index: int,
        trigger_ts: datetime,
        pipeline_run_id: str,
        source: dict[str, Any],
    ) -> str | None:
        if self._recording is not None:
            return None

        trigger_ts = ensure_utc(trigger_ts)
        if self._last_trigger_ts is not None:
            elapsed = (trigger_ts - self._last_trigger_ts).total_seconds()
            if elapsed < self.cooldown_sec:
                return None

        alert_id = f"{self.camera_id}_{trigger_frame_index}_{alert_type}"
        self._recording = {
            "alert_id": alert_id,
            "alert_type": alert_type,
            "trigger_frame_index": trigger_frame_index,
            "trigger_ts": trigger_ts,
            "pipeline_run_id": pipeline_run_id,
            "source": source,
            "pre_frames": self._snapshot_pre_buffer(),
        }
        self._post_frames = []
        self._post_remaining = self.post_buffer_sec * self.fps
        self._last_trigger_ts = trigger_ts
        self.total_triggered += 1
        logger.info("Alert clip triggered: %s", alert_id)
        return alert_id

    def drain_completed(self) -> list[ClipCreatedResult]:
        completed: list[ClipCreatedResult] = []
        pending: list[Future[ClipCreatedResult]] = []

        for future in self._futures:
            if not future.done():
                pending.append(future)
                continue
            try:
                result = future.result()
            except Exception:
                self.total_failed += 1
                logger.exception("Alert clip upload failed")
            else:
                self.total_uploaded += 1
                completed.append(result)

        self._futures = pending
        return completed

    def shutdown(self) -> list[ClipCreatedResult]:
        if self._recording is not None and self._post_frames:
            self._submit_clip()
        self._executor.shutdown(wait=True)
        return self.drain_completed()

    def _snapshot_pre_buffer(self) -> list[bytes]:
        if self._ring_pos < len(self._ring):
            ordered = self._ring[: self._ring_pos]
        else:
            pos = self._ring_pos % len(self._ring)
            ordered = self._ring[pos:] + self._ring[:pos]
        return [frame for frame in ordered if frame is not None]

    def _submit_clip(self) -> None:
        if self._recording is None:
            return

        metadata = self._recording
        frames = metadata["pre_frames"] + self._post_frames
        self._recording = None
        self._post_frames = []
        self._post_remaining = 0

        if not frames:
            logger.warning("Skipping empty alert clip: %s", metadata["alert_id"])
            return

        future = self._executor.submit(self._encode_upload_clip, metadata, frames)
        self._futures.append(future)

    def _encode_upload_clip(self, metadata: dict[str, Any], jpeg_frames: list[bytes]) -> ClipCreatedResult:
        decoded_frames: list[np.ndarray] = []
        for body in jpeg_frames:
            arr = np.frombuffer(body, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None:
                decoded_frames.append(frame)

        if not decoded_frames:
            raise RuntimeError(f"No decodable frames for clip {metadata['alert_id']}")

        height, width = decoded_frames[0].shape[:2]
        fd, tmp_path = tempfile.mkstemp(prefix=f"{metadata['alert_id']}_", suffix=".mp4")
        os.close(fd)

        try:
            writer = cv2.VideoWriter(tmp_path, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (width, height))
            if not writer.isOpened():
                raise RuntimeError(f"Cannot open VideoWriter for {tmp_path}")

            try:
                for frame in decoded_frames:
                    if frame.shape[1] != width or frame.shape[0] != height:
                        frame = cv2.resize(frame, (width, height))
                    writer.write(frame)
            finally:
                writer.release()

            with open(tmp_path, "rb") as f:
                body = f.read()

            key = self._build_clip_key(metadata["trigger_ts"], metadata["alert_id"])
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType="video/mp4",
            )

            upload_ts = datetime.now(timezone.utc)
            frame_count = len(decoded_frames)
            return ClipCreatedResult(
                schema_version="1.0",
                event_type="clip_created",
                pipeline_run_id=metadata["pipeline_run_id"],
                alert_id=metadata["alert_id"],
                alert_type=metadata["alert_type"],
                source=metadata["source"],
                trigger_frame_index=metadata["trigger_frame_index"],
                trigger_ts=metadata["trigger_ts"].isoformat(),
                upload_ts=upload_ts.isoformat(),
                bucket=self.bucket,
                clip_s3_key=key,
                clip_s3_uri=f"s3://{self.bucket}/{key}",
                content_type="video/mp4",
                clip_duration_sec=frame_count / float(self.fps),
                frame_count=frame_count,
                byte_size=len(body),
            )
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                logger.warning("Unable to remove temp clip file: %s", tmp_path)

    def _build_clip_key(self, trigger_ts: datetime, alert_id: str) -> str:
        ts = ensure_utc(trigger_ts)
        return f"clips/{ts:%Y-%m-%d}/{self.store_id}/{self.camera_id}/{alert_id}.mp4"

