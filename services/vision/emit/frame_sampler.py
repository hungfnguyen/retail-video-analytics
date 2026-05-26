import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import cv2

from core.time_utils import ensure_utc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SampledFrameResult:
    schema_version: str
    event_type: str
    pipeline_run_id: str
    source: dict[str, Any]
    frame_index: int
    capture_ts: str
    upload_ts: str
    image_size: dict[str, int]
    bucket: str
    s3_key: str
    s3_uri: str
    content_type: str
    byte_size: int
    jpeg_quality: int


class FrameSampler:
    """Best-effort sampled JPEG uploader for visual verification."""

    def __init__(
        self,
        *,
        s3_client: Any,
        bucket: str,
        store_id: str,
        camera_id: str,
        interval_sec: float = 1.0,
        jpeg_quality: int = 85,
        max_workers: int = 2,
        inflight_limit: int | None = None,
    ):
        self.s3 = s3_client
        self.bucket = bucket
        self.store_id = store_id
        self.camera_id = camera_id
        self.interval_sec = max(0.1, float(interval_sec))
        self.jpeg_quality = int(jpeg_quality)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="frame-uploader")
        self._futures: list[Future[SampledFrameResult]] = []
        self._last_sample_ts: datetime | None = None
        self._inflight_limit = inflight_limit or max_workers * 4

        self.total_submitted = 0
        self.total_uploaded = 0
        self.total_failed = 0
        self.total_skipped_backlog = 0

    def maybe_save(
        self,
        *,
        frame: Any,
        frame_index: int,
        capture_ts: datetime,
        pipeline_run_id: str,
        source: dict[str, Any],
        image_size: dict[str, int],
    ) -> str | None:
        """Submit a sampled frame upload when the time interval elapsed."""
        if not self._should_sample(capture_ts):
            return None

        active = sum(1 for f in self._futures if not f.done())
        if active >= self._inflight_limit:
            self.total_skipped_backlog += 1
            logger.warning("Skipping sampled frame %d due to S3 upload backlog", frame_index)
            return None

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            self.total_failed += 1
            logger.warning("JPEG encode failed for frame %d", frame_index)
            return None

        key = self._build_key(capture_ts, frame_index)
        body = buf.tobytes()
        future = self._executor.submit(
            self._upload,
            key=key,
            body=body,
            pipeline_run_id=pipeline_run_id,
            source=source,
            frame_index=frame_index,
            capture_ts=capture_ts,
            image_size=image_size,
        )
        self._futures.append(future)
        self._last_sample_ts = capture_ts
        self.total_submitted += 1

        if len(self._futures) > self._inflight_limit * 4:
            self.drain_completed()

        return key

    def drain_completed(self) -> list[SampledFrameResult]:
        """Return completed upload results and remove completed futures."""
        completed: list[SampledFrameResult] = []
        pending: list[Future[SampledFrameResult]] = []

        for future in self._futures:
            if not future.done():
                pending.append(future)
                continue
            try:
                result = future.result()
            except Exception:
                self.total_failed += 1
                logger.exception("Sampled frame upload failed")
            else:
                self.total_uploaded += 1
                completed.append(result)

        self._futures = pending
        return completed

    def shutdown(self) -> list[SampledFrameResult]:
        self._executor.shutdown(wait=True)
        return self.drain_completed()

    def _should_sample(self, capture_ts: datetime) -> bool:
        if self._last_sample_ts is None:
            return True
        return (capture_ts - self._last_sample_ts).total_seconds() >= self.interval_sec

    def _build_key(self, ts: datetime, frame_index: int) -> str:
        ts = ensure_utc(ts)
        return (
            f"frames/{ts:%Y-%m-%d}/{self.store_id}/{self.camera_id}/"
            f"{ts:%H}h/{ts:%H%M%S}_{frame_index:09d}.jpg"
        )

    def _upload(
        self,
        *,
        key: str,
        body: bytes,
        pipeline_run_id: str,
        source: dict[str, Any],
        frame_index: int,
        capture_ts: datetime,
        image_size: dict[str, int],
    ) -> SampledFrameResult:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="image/jpeg",
        )
        upload_ts = datetime.now(timezone.utc)
        return SampledFrameResult(
            schema_version="1.0",
            event_type="sampled_frame_created",
            pipeline_run_id=pipeline_run_id,
            source=source,
            frame_index=frame_index,
            capture_ts=ensure_utc(capture_ts).isoformat(),
            upload_ts=upload_ts.isoformat(),
            image_size=image_size,
            bucket=self.bucket,
            s3_key=key,
            s3_uri=f"s3://{self.bucket}/{key}",
            content_type="image/jpeg",
            byte_size=len(body),
            jpeg_quality=self.jpeg_quality,
        )


