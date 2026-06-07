import uuid
import logging
import signal
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict

from detect.supervision_yolo_detector import SupervisionYoloDetector
from inference.shared_yolo import SharedInferenceClient
from emit.pulsar_emitter import PulsarEmitter
from emit.s3_client import S3ClientConfig, create_s3_client
from emit.frame_sampler import FrameSampler
from emit.clip_extractor import AlertClipExtractor
from features.detections import (
    add_global_track_ids,
    detections_to_track_objects,
    track_to_detection,
)
from features.runtime_versions import package_version
from media.live_frame_publisher import LiveFramePublisher, create_live_frame_publisher
from reader import VideoFileReader
from track.roboflow_tracker import create_detections_smoother, create_supervision_tracker
from track.track_memory import TrackMemory, TrackMemoryConfig
from utils.visualizer import Visualizer
from zones.zone_manager import RetailZoneRuntime

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


def _frame_from_packet(packet: Any) -> tuple[Any, int | None, float | None, int, int]:
    """Return frame and reader diagnostics from a FramePacket or legacy ndarray."""
    if hasattr(packet, "frame"):
        return (
            packet.frame,
            int(getattr(packet, "source_frame_index", 0)),
            float(getattr(packet, "source_fps", 0.0)),
            int(getattr(packet, "dropped_before_enqueue", 0)),
            int(getattr(packet, "total_dropped", 0)),
        )
    return packet, None, None, 0, 0


def run_worker(
    camera_cfg: Dict[str, Any],
    global_cfg: Dict[str, Any],
    shared_inference_request_queue: Any | None = None,
    shared_inference_response_queue: Any | None = None,
) -> None:
    """CameraWorker: chạy pipeline cho 1 camera trong process riêng."""
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

    class_filter = global_cfg.get("class_filter", [0])

    # 1. Load tracker state once per camera worker. YOLO can run either inside
    # this process or in the manager-owned shared inference process.
    logger.info(
        "Loading rebuilt Vision pipeline: model=%s tracker=%s shared_inference=%s",
        global_cfg["model_name"],
        global_cfg["tracker_type"],
        bool(global_cfg.get("shared_inference_enabled", False)),
    )
    use_shared_inference = (
        bool(global_cfg.get("shared_inference_enabled", False))
        and shared_inference_request_queue is not None
        and shared_inference_response_queue is not None
    )
    if use_shared_inference:
        detector = SharedInferenceClient(
            camera_id=camera_id,
            request_queue=shared_inference_request_queue,
            response_queue=shared_inference_response_queue,
            timeout_sec=float(global_cfg.get("shared_inference_timeout_sec", 30.0)),
        )
    else:
        detector = SupervisionYoloDetector(
            global_cfg["model_name"],
            conf_thres=float(global_cfg.get("conf_thres", 0.15)),
            class_filter=class_filter,
            iou=float(global_cfg.get("detector_iou", 0.70)),
            imgsz=global_cfg.get("detector_imgsz", 1280),
            half=bool(global_cfg.get("detector_half", True)),
        )
    tracker = create_supervision_tracker(global_cfg["tracker_type"], global_cfg)
    effective_tracker_type = getattr(tracker, "tracker_type", global_cfg["tracker_type"])
    smoother = create_detections_smoother(global_cfg)
    logger.info("Rebuilt Vision pipeline loaded successfully: effective_tracker=%s", effective_tracker_type)

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

    # 3. Start VideoFileReader thread after model + Pulsar are ready.
    source_uri = camera_cfg["source_uri"]
    fps_target = camera_cfg.get("fps_target", 25)
    frame_policy = global_cfg.get("frame_policy") or {}
    queue_size = int(frame_policy.get("max_queue_size", global_cfg.get("frame_queue_size", 2)))

    _reader = VideoFileReader(
        video_path=source_uri,
        fps_target=fps_target,
        queue_size=queue_size,
        realtime=True,
        loop=True,
    )
    _reader.start()
    logger.info(
        "Pipeline loop starting: frame_policy=%s queue_size=%d",
        frame_policy.get("mode", "tracking_safe"),
        queue_size,
    )

    source_info = {
        "store_id": store_id,
        "camera_id": camera_id,
        "stream_id": f"{camera_id}_stream",
    }
    live_frame_publisher: LiveFramePublisher | None = create_live_frame_publisher(
        camera_id,
        global_cfg,
    )
    visualizer = Visualizer() if live_frame_publisher else None
    track_memory = _create_track_memory(global_cfg)
    zone_runtime = RetailZoneRuntime.from_config_path(
        global_cfg.get("zones_config_path"), store_id, camera_id
    )
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

    frame_index = 0
    last_processed_monotonic = 0.0
    last_source_frame_index: int | None = None
    last_reader_drop_count = 0
    previous_track_ids: set[int] = set()
    queue_entered_ms_by_track: dict[int, int] = {}
    schema_version = str(global_cfg.get("event_schema_version", "1.0"))
    publish_vision_facts = bool(global_cfg.get("publish_vision_facts", True))

    try:
        while _reader._running:
            try:
                packet = _reader.queue.get(timeout=1.0)
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

            frame, source_frame_index, source_fps, dropped_before_enqueue, total_dropped = _frame_from_packet(packet)
            frame_index += 1
            capture_ts = datetime.now(timezone.utc)
            capture_ts_iso = capture_ts.isoformat()
            height, width = frame.shape[:2]

            reader_drop_delta = max(0, total_dropped - last_reader_drop_count)
            last_reader_drop_count = max(last_reader_drop_count, total_dropped)
            source_gap = 0
            if source_frame_index is not None and last_source_frame_index is not None:
                source_gap = max(0, source_frame_index - last_source_frame_index - 1)
            if source_frame_index is not None:
                last_source_frame_index = source_frame_index
            dropped_frames_since_last = max(
                int(dropped_before_enqueue), int(reader_drop_delta), int(source_gap)
            )

            inference_started = time.perf_counter()
            raw_detections = detector.predict(frame)
            inference_ms = max(0, int((time.perf_counter() - inference_started) * 1000))

            tracking_started = time.perf_counter()
            tracked_detections = tracker.update(raw_detections)
            tracked_detections = smoother.update(tracked_detections)
            tracking_ms = max(0, int((time.perf_counter() - tracking_started) * 1000))

            postprocess_started = time.perf_counter()
            raw_objects = detections_to_track_objects(tracked_detections, detector.names)
            stable_tracks = track_memory.update(
                raw_objects,
                frame_index=frame_index,
                timestamp_ms=int(capture_ts.timestamp() * 1000),
            )
            add_global_track_ids(stable_tracks, camera_id)

            zone_started = time.perf_counter()
            zone_assignments, zone_counts = zone_runtime.assign(stable_tracks, width, height)
            queue_track_ids_this_frame: set[int] = set()
            current_ts_ms = int(capture_ts.timestamp() * 1000)
            for track, zones in zip(stable_tracks, zone_assignments):
                primary_zone = next((zone for zone in zones if zone.get("is_primary")), None)
                if primary_zone:
                    track["primary_zone_id"] = primary_zone.get("zone_id")
                    track["primary_zone_type"] = primary_zone.get("zone_type")
                track_id = track.get("id")
                if (
                    isinstance(track_id, int)
                    and primary_zone
                    and primary_zone.get("zone_type") == "queue"
                ):
                    queue_track_ids_this_frame.add(track_id)
                    entered_ms = queue_entered_ms_by_track.setdefault(track_id, current_ts_ms)
                    wait_ms = max(0, current_ts_ms - entered_ms)
                    track["queue_wait_ms"] = wait_ms
                    track["queue_wait_seconds"] = wait_ms // 1000
                else:
                    track.pop("queue_wait_ms", None)
                    track.pop("queue_wait_seconds", None)
                    if isinstance(track_id, int):
                        queue_entered_ms_by_track.pop(track_id, None)
            # Roll up per-track wait_ms into zone_counts so Flink/Redis gets aggregate stats
            zone_wait_ms_by_id: dict[str, list[int]] = {}
            for track in stable_tracks:
                if track.get("primary_zone_type") == "queue":
                    zid = track.get("primary_zone_id")
                    wms = track.get("queue_wait_ms", 0)
                    if zid:
                        zone_wait_ms_by_id.setdefault(zid, []).append(wms)
            for zc in zone_counts:
                if zc.get("zone_type") == "queue":
                    waits = zone_wait_ms_by_id.get(zc["zone_id"], [])
                    zc["avg_wait_ms"] = int(sum(waits) / len(waits)) if waits else 0
                    zc["max_wait_ms"] = max(waits) if waits else 0

            queue_entered_ms_by_track = {
                track_id: entered_ms
                for track_id, entered_ms in queue_entered_ms_by_track.items()
                if track_id in queue_track_ids_this_frame
            }
            line_crossings = zone_runtime.trigger_lines(stable_tracks, width, height)
            zone_ms = max(0, int((time.perf_counter() - zone_started) * 1000))

            track_summary = track_memory.summary(stable_tracks)
            current_track_ids = {
                int(track["id"])
                for track in stable_tracks
                if isinstance(track.get("id"), int) and track.get("id", -1) >= 0
            }
            new_track_ids = sorted(current_track_ids - previous_track_ids)
            lost_track_ids = sorted(previous_track_ids - current_track_ids)
            previous_track_ids = current_track_ids

            detections = [
                track_to_detection(
                    frame_index=frame_index,
                    object_index=j,
                    obj=obj,
                    width=width,
                    height=height,
                    zones=zone_assignments[j] if j < len(zone_assignments) else [],
                )
                for j, obj in enumerate(stable_tracks)
            ]
            postprocess_ms = max(0, int((time.perf_counter() - postprocess_started) * 1000))

            frame_metrics = {
                "people_count": len(detections),
                "raw_detection_count": len(raw_detections),
                "tracked_detection_count": len(raw_objects),
                "stable_track_count": track_summary["stable_tracks_count"],
                "dropped_frames_since_last": dropped_frames_since_last,
                "reader_drop_count": _reader.drop_count if _reader else 0,
                "source_fps": source_fps or fps_target,
                "effective_fps": processing_fps,
                "processed_interval_ms": processed_interval_ms,
                "inference_ms": inference_ms,
                "tracking_ms": tracking_ms,
                "postprocess_ms": postprocess_ms,
                "zone_ms": zone_ms,
                "new_track_ids": new_track_ids,
                "lost_track_ids": lost_track_ids,
                "line_crossing_count": len(line_crossings),
                **track_summary,
            }

            if live_frame_publisher and visualizer:
                try:
                    draw_started = time.perf_counter()
                    annotated_frame = visualizer.draw_tracks(frame.copy(), stable_tracks)
                    annotated_frame = zone_runtime.draw_overlays(
                        annotated_frame, width, height, zone_counts
                    )
                    draw_ms = max(0, int((time.perf_counter() - draw_started) * 1000))
                    live_frame_publisher.publish(
                        annotated_frame,
                        frame_index=frame_index,
                        capture_ts=capture_ts,
                        detections_count=len(detections),
                        extra_metrics={
                            **frame_metrics,
                            "draw_ms": draw_ms,
                            "reader_queue_size": _reader.queue.qsize() if _reader else 0,
                            "raw_tracks_count": len(raw_objects),
                            "zone_counts": zone_counts,
                            "line_crossings": line_crossings,
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
                    "tracker_type": effective_tracker_type,
                    "conf_thres": float(global_cfg.get("conf_thres", 0.15)),
                    "class_filter": class_filter,
                    "detector_type": detector.detector_type,
                    "shared_inference_enabled": use_shared_inference,
                    "supervision_version": package_version("supervision"),
                    "trackers_version": package_version("trackers"),
                    "zone_config_version": zone_runtime.version,
                    "track_id_semantics": "stable_v1_track_memory",
                },
                source_uri=source_uri,
                schema_version=schema_version,
                event_type="detection_frame" if publish_vision_facts else None,
                source_frame_index=source_frame_index if publish_vision_facts else None,
                ingest_ts=datetime.now(timezone.utc).isoformat() if publish_vision_facts else None,
                frame_metrics=frame_metrics if publish_vision_facts else None,
                zone_counts=zone_counts if publish_vision_facts else None,
                line_crossings=line_crossings if publish_vision_facts else None,
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
