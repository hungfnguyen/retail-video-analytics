import uuid
import logging
import signal
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict

from track.tracker_factory import create_tracker
from track.track_memory import TrackMemory, TrackMemoryConfig
from emit.pulsar_emitter import PulsarEmitter
from emit.s3_client import S3ClientConfig, create_s3_client
from emit.frame_sampler import FrameSampler
from emit.clip_extractor import AlertClipExtractor
from media.live_frame_publisher import LiveFramePublisher, create_live_frame_publisher
from reader import VideoFileReader
from utils.visualizer import Visualizer

logger = logging.getLogger(__name__)

# Global để signal handler tiếp cận được
_emitter: PulsarEmitter | None = None
_reader: VideoFileReader | None = None


def _shutdown(signum, frame):
    """Signal handler: set running=False để cleanup."""
    logger.info("Received signal %s, shutting down worker...", signum)
    if _reader:
        _reader._running = False


def _publish_completed_media_events(
    emitter: PulsarEmitter | None,
    frame_sampler: FrameSampler | None,
    clip_extractor: AlertClipExtractor | None,
) -> None:
    if not emitter:
        return

    if frame_sampler:
        for result in frame_sampler.drain_completed():
            emitter.emit_media_event(asdict(result), frame_index=result.frame_index)

    if clip_extractor:
        for result in clip_extractor.drain_completed():
            emitter.emit_media_event(
                asdict(result), frame_index=result.trigger_frame_index
            )


def _create_track_memory(global_cfg: dict[str, Any]) -> TrackMemory:
    return TrackMemory(
        TrackMemoryConfig(
            enabled=bool(global_cfg.get("track_memory_enabled", True)),
            lost_ttl_ms=int(global_cfg.get("track_lost_ttl_ms", 1000)),
            lost_ttl_frames=int(global_cfg.get("track_lost_ttl_frames", 15)),
            min_hits=int(global_cfg.get("track_min_hits", 1)),
            smooth_alpha=float(global_cfg.get("track_smooth_alpha", 0.65)),
            publish_predicted=bool(global_cfg.get("track_publish_predicted", True)),
            count_predicted=bool(global_cfg.get("track_count_predicted", True)),
            predicted_conf_decay=float(
                global_cfg.get("track_predicted_conf_decay", 0.85)
            ),
            min_predicted_conf=float(global_cfg.get("track_min_predicted_conf", 0.20)),
            reid_iou_threshold=float(global_cfg.get("track_reid_iou_threshold", 0.15)),
            reid_center_distance_px=float(
                global_cfg.get("track_reid_center_distance_px", 120.0)
            ),
        )
    )


def _track_to_detection(
    *,
    frame_index: int,
    object_index: int,
    obj: dict[str, Any],
    width: int,
    height: int,
) -> dict[str, Any]:
    x1, y1, x2, y2 = map(float, obj["bbox"])
    w_box = x2 - x1
    h_box = y2 - y1
    cx = x1 + w_box / 2.0
    cy = y1 + h_box / 2.0

    return {
        "det_id": f"{frame_index}-{object_index}",
        "class": obj.get("label", "person"),
        "class_id": int(obj.get("cls", 0)),
        "conf": float(obj.get("conf", 0.0)),
        "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "bbox_norm": {
            "x": x1 / width,
            "y": y1 / height,
            "w": w_box / width,
            "h": h_box / height,
        },
        "centroid": {"x": int(cx), "y": int(cy)},
        "centroid_norm": {"x": cx / width, "y": cy / height},
        "track_id": None if obj.get("id", -1) < 0 else int(obj["id"]),
        "track_state": str(obj.get("track_state", "matched")),
        "measurement_source": str(obj.get("measurement_source", "full_body")),
        "missed_frames": int(obj.get("missed_frames", 0)),
        "is_predicted": bool(obj.get("is_predicted", False)),
    }


def run_worker(camera_cfg: Dict[str, Any], global_cfg: Dict[str, Any]) -> None:
    """CameraWorker: chạy pipeline cho 1 camera trong process riêng.

    Args:
        camera_cfg: config của 1 camera (camera_id, store_id, source_uri, fps_target, ...)
        global_cfg: config chung (model_name, tracker_type, conf_thres, class_filter, pulsar_*)
    """
    global _emitter, _reader

    pipeline_run_id = uuid.uuid4().hex[:12]
    camera_id = camera_cfg["camera_id"]
    store_id = camera_cfg["store_id"]

    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [cam={camera_id}] %(levelname)s %(message)s",
    )

    logger.info("Worker starting: run=%s store=%s", pipeline_run_id, store_id)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # 1. Load model + tracker TRƯỚC (có thể mất vài giây)
    logger.info("Loading model: %s ...", global_cfg["model_name"])
    tracker = create_tracker(
        global_cfg["tracker_type"],
        global_cfg["model_name"],
        conf_thres=global_cfg["conf_thres"],
    )
    logger.info("Model loaded successfully")

    # 2. Connect Pulsar
    try:
        _emitter = PulsarEmitter(
            global_cfg["pulsar_service_url"],
            global_cfg["pulsar_topic"],
            media_topic=global_cfg.get("pulsar_media_topic")
            if global_cfg.get("media_upload_enabled")
            else None,
        )
    except Exception as e:
        logger.error("Cannot connect to Pulsar: %s", e)
        return

    # 3. Start VideoFileReader thread (SAU KHI model + Pulsar sẵn sàng)
    source_uri = camera_cfg["source_uri"]
    fps_target = camera_cfg.get("fps_target", 25)
    queue_size = global_cfg.get("frame_queue_size", 2)

    _reader = VideoFileReader(
        video_path=source_uri,
        fps_target=fps_target,
        queue_size=queue_size,
        realtime=True,
        loop=True,
    )
    _reader.start()
    logger.info("Pipeline loop starting")

    source_info = {
        "store_id": store_id,
        "camera_id": camera_id,
        "stream_id": f"{camera_id}_stream",
    }
    class_filter = global_cfg.get("class_filter", [0])
    live_frame_publisher: LiveFramePublisher | None = create_live_frame_publisher(
        camera_id,
        global_cfg,
    )
    visualizer = Visualizer() if live_frame_publisher else None
    track_memory = _create_track_memory(global_cfg)
    logger.info(
        "TrackMemory enabled=%s lost_ttl=%dms/%d frames predicted=%s",
        track_memory.config.enabled,
        track_memory.config.lost_ttl_ms,
        track_memory.config.lost_ttl_frames,
        track_memory.config.publish_predicted,
    )
    frame_sampler: FrameSampler | None = None
    clip_extractor: AlertClipExtractor | None = None
    if global_cfg.get("media_upload_enabled"):
        s3_client = create_s3_client(
            S3ClientConfig(
                endpoint_url=global_cfg.get("s3_endpoint"),
                region_name=global_cfg.get("s3_region", "us-east-1"),
                bucket=global_cfg.get("s3_bucket", "warehouse"),
                access_key=global_cfg.get("s3_access_key"),
                secret_key=global_cfg.get("s3_secret_key"),
                path_style=global_cfg.get("s3_path_style", True),
            )
        )
        if s3_client is None:
            logger.warning("Media upload requested but S3 client is unavailable")
        else:
            if global_cfg.get("frame_sampling_enabled", True):
                frame_sampler = FrameSampler(
                    s3_client=s3_client,
                    bucket=global_cfg.get("s3_bucket", "warehouse"),
                    store_id=store_id,
                    camera_id=camera_id,
                    interval_sec=global_cfg.get("frame_sample_interval_sec", 1.0),
                    jpeg_quality=global_cfg.get("frame_jpeg_quality", 85),
                    max_workers=global_cfg.get("frame_upload_workers", 2),
                    inflight_limit=global_cfg.get("frame_upload_inflight_limit", 8),
                )
                logger.info(
                    "FrameSampler enabled: bucket=%s interval=%.2fs",
                    global_cfg.get("s3_bucket", "warehouse"),
                    global_cfg.get("frame_sample_interval_sec", 1.0),
                )

            if global_cfg.get("alert_clip_enabled", False):
                clip_extractor = AlertClipExtractor(
                    s3_client=s3_client,
                    bucket=global_cfg.get("s3_bucket", "warehouse"),
                    store_id=store_id,
                    camera_id=camera_id,
                    pre_buffer_sec=global_cfg.get("alert_pre_buffer_sec", 5),
                    post_buffer_sec=global_cfg.get("alert_post_buffer_sec", 5),
                    fps=fps_target,
                    jpeg_quality=global_cfg.get("clip_jpeg_quality", 80),
                    cooldown_sec=global_cfg.get("alert_cooldown_sec", 30),
                    max_workers=global_cfg.get("clip_upload_workers", 1),
                )
                logger.info(
                    "AlertClipExtractor enabled: threshold=%d pre=%ds post=%ds",
                    global_cfg.get("alert_density_threshold", 10),
                    global_cfg.get("alert_pre_buffer_sec", 5),
                    global_cfg.get("alert_post_buffer_sec", 5),
                )

    # 4. Pipeline loop — per-frame tracking via model.track(persist=True)
    frame_index = 0
    last_processed_monotonic = 0.0
    try:
        while _reader._running:
            try:
                frame = _reader.queue.get(timeout=1.0)
            except Exception:
                continue  # timeout, check _running and retry

            loop_started = time.perf_counter()
            processed_interval_ms = (
                max(0, int((loop_started - last_processed_monotonic) * 1000))
                if last_processed_monotonic > 0
                else 0
            )
            processing_fps = (
                round(1000.0 / processed_interval_ms, 2)
                if processed_interval_ms > 0
                else 0.0
            )
            last_processed_monotonic = loop_started

            frame_index += 1
            capture_ts = datetime.now(timezone.utc)
            capture_ts_iso = capture_ts.isoformat()
            height, width = frame.shape[:2]

            # Per-frame tracking: Ultralytics persist=True giữ tracker state giữa các lần gọi
            inference_started = time.perf_counter()
            results = tracker.model.track(
                source=frame,
                persist=True,
                classes=class_filter,
                conf=tracker.track_conf,
                device=tracker.device,
                tracker=tracker.tracker_yaml,
                verbose=False,
            )
            inference_ms = max(0, int((time.perf_counter() - inference_started) * 1000))

            postprocess_started = time.perf_counter()
            raw_objects = []
            for r in results:
                raw_objects.extend(tracker._extract_objects(r))

            stable_tracks = track_memory.update(
                raw_objects,
                frame_index=frame_index,
                timestamp_ms=int(capture_ts.timestamp() * 1000),
            )
            track_summary = track_memory.summary(stable_tracks)
            detections = [
                _track_to_detection(
                    frame_index=frame_index,
                    object_index=j,
                    obj=obj,
                    width=width,
                    height=height,
                )
                for j, obj in enumerate(stable_tracks)
            ]
            postprocess_ms = max(0, int((time.perf_counter() - postprocess_started) * 1000))

            if live_frame_publisher and visualizer:
                try:
                    draw_started = time.perf_counter()
                    annotated_frame = visualizer.draw_tracks(frame.copy(), stable_tracks)
                    draw_ms = max(0, int((time.perf_counter() - draw_started) * 1000))
                    live_frame_publisher.publish(
                        annotated_frame,
                        frame_index=frame_index,
                        capture_ts=capture_ts,
                        detections_count=len(detections),
                        extra_metrics={
                            "processing_fps": processing_fps,
                            "processed_interval_ms": processed_interval_ms,
                            "inference_ms": inference_ms,
                            "postprocess_ms": postprocess_ms,
                            "draw_ms": draw_ms,
                            "reader_queue_size": _reader.queue.qsize() if _reader else 0,
                            "reader_drop_count": _reader.drop_count if _reader else 0,
                            "raw_tracks_count": len(raw_objects),
                            "tracked_objects_count": track_summary["stable_tracks_count"],
                            **track_summary,
                        },
                    )
                except Exception:
                    logger.exception(
                        "Live media publish failed for frame %d", frame_index
                    )

            _emitter.emit_frame(
                pipeline_run_id=pipeline_run_id,
                source=source_info,
                frame_index=frame_index,
                capture_ts_iso=capture_ts_iso,
                image_size={"width": width, "height": height},
                detections=detections,
                runtime={
                    "model_name": global_cfg["model_name"],
                    "tracker_type": global_cfg["tracker_type"],
                },
            )

            if frame_sampler:
                frame_sampler.maybe_save(
                    frame=frame,
                    frame_index=frame_index,
                    capture_ts=capture_ts,
                    pipeline_run_id=pipeline_run_id,
                    source=source_info,
                    image_size={"width": width, "height": height},
                )

            if clip_extractor:
                clip_extractor.feed(frame, frame_index, capture_ts)
                if len(detections) > global_cfg.get("alert_density_threshold", 10):
                    clip_extractor.trigger(
                        alert_type="density_high",
                        trigger_frame_index=frame_index,
                        trigger_ts=capture_ts,
                        pipeline_run_id=pipeline_run_id,
                        source=source_info,
                    )

            _publish_completed_media_events(_emitter, frame_sampler, clip_extractor)

    except Exception:
        logger.exception("Unexpected error in worker pipeline")
    finally:
        logger.info("Worker cleaning up (processed %d frames)...", frame_index)
        if _reader:
            _reader.stop()
        if _emitter:
            try:
                if frame_sampler:
                    for result in frame_sampler.shutdown():
                        _emitter.emit_media_event(
                            asdict(result), frame_index=result.frame_index
                        )
                if clip_extractor:
                    for result in clip_extractor.shutdown():
                        _emitter.emit_media_event(
                            asdict(result), frame_index=result.trigger_frame_index
                        )
                _emitter.close()
            except Exception:
                pass
        logger.info("Worker stopped")
