import os
import json
import yaml
from pathlib import Path
from typing import Any, Dict, List
from dotenv import dotenv_values, load_dotenv

# Define base dir (services/vision folder)
BASE_DIR = Path(__file__).resolve().parent.parent

# Project root: 3 levels up from services/vision/config/
PROJECT_ROOT = BASE_DIR.parent.parent

# Load .env file from services/vision directory. Root .env is read selectively
# for shared S3 settings so host-side Vision can use the repository-level AWS config
# without inheriting unrelated Docker-only endpoints.
load_dotenv(BASE_DIR / ".env")
ROOT_ENV = dotenv_values(PROJECT_ROOT / ".env")


class Settings:
    """Single-camera settings from .env (backward compat)."""

    MODEL_NAME = os.getenv("MODEL_NAME", "yolo11l.pt")

    _video_path_raw = os.getenv("VIDEO_PATH", "video/video3.mp4")
    VIDEO_PATH = (
        str(BASE_DIR / _video_path_raw)
        if not Path(_video_path_raw).is_absolute()
        else _video_path_raw
    )

    _out_jsonl_raw = os.getenv("OUT_JSONL", "../../data/metadata/video.jsonl")
    OUT_JSONL = (
        str(BASE_DIR / _out_jsonl_raw)
        if not Path(_out_jsonl_raw).is_absolute()
        else _out_jsonl_raw
    )

    TRACKER_TYPE = os.getenv("TRACKER_TYPE", "botsort")
    CONF_THRES = float(os.getenv("CONF_THRES", "0.25"))

    PULSAR_SERVICE_URL = os.getenv("PULSAR_SERVICE_URL", "pulsar://localhost:6650")
    PULSAR_TOPIC = os.getenv("PULSAR_TOPIC", "persistent://retail/metadata/events")
    PULSAR_MEDIA_TOPIC = os.getenv(
        "PULSAR_MEDIA_TOPIC", "persistent://retail/metadata/media-events"
    )

    _class_filter_str = os.getenv("CLASS_FILTER", "[0]")
    try:
        CLASS_FILTER = json.loads(_class_filter_str)
    except Exception:
        CLASS_FILTER = [0]

    STORE_ID = os.getenv("STORE_ID", "store_01")
    CAMERA_ID = os.getenv("CAMERA_ID", "cam_01")
    STREAM_ID = os.getenv("STREAM_ID", "stream_01")


settings = Settings()


def load_cameras_config(path: str | None = None) -> Dict[str, Any]:
    """Load multi-camera config from YAML file.

    Falls back to single-camera .env mode if YAML is missing.
    """
    if path is None:
        path = str(PROJECT_ROOT / "configs" / "cameras.yaml")

    yaml_path = Path(path)
    if not yaml_path.exists():
        example_path = PROJECT_ROOT / "configs" / "cameras.yaml.example"
        if example_path.exists():
            yaml_path = example_path
        else:
            return _fallback_single_camera()

    with open(yaml_path, "r") as f:
        cfg = yaml.safe_load(f)

    cameras: List[Dict[str, Any]] = cfg.get("cameras", [])
    global_settings: Dict[str, Any] = cfg.get("settings", {})

    # Merge: Pulsar config từ .env hoặc default, override từ YAML
    pulsar_url = os.getenv(
        "PULSAR_SERVICE_URL",
        global_settings.get("pulsar_service_url", "pulsar://localhost:6650"),
    )
    pulsar_topic = os.getenv(
        "PULSAR_TOPIC",
        global_settings.get("pulsar_topic", "persistent://retail/metadata/events"),
    )
    pulsar_media_topic = os.getenv(
        "PULSAR_MEDIA_TOPIC",
        global_settings.get(
            "pulsar_media_topic", "persistent://retail/metadata/media-events"
        ),
    )

    enabled_cameras = [c for c in cameras if c.get("enabled", True)]

    return {
        "cameras": enabled_cameras,
        "pulsar_service_url": pulsar_url,
        "pulsar_topic": pulsar_topic,
        "pulsar_media_topic": pulsar_media_topic,
        "model_name": _get_vision_setting("model_name", global_settings),
        "tracker_type": _get_vision_setting("tracker_type", global_settings),
        "conf_thres": float(_get_vision_setting("conf_thres", global_settings)),
        "class_filter": _get_vision_class_filter(global_settings),
        "frame_policy": _get_frame_policy(global_settings),
        "frame_queue_size": _get_frame_queue_size(global_settings),
        "event_schema_version": str(
            _get_optional("event_schema_version", global_settings) or "1.0"
        ),
        "publish_vision_facts": _get_bool(
            "publish_vision_facts", global_settings, True
        ),
        "detector_type": str(
            _get_optional("detector_type", global_settings) or "ultralytics_yolo"
        ),
        "detector_iou": _get_float("detector_iou", global_settings, 0.70),
        "detector_imgsz": _get_int("detector_imgsz", global_settings, 1280),
        "detector_half": _get_bool("detector_half", global_settings, True),
        "track_activation_threshold": _get_float(
            "track_activation_threshold", global_settings, 0.20
        ),
        "lost_track_buffer": _get_int("lost_track_buffer", global_settings, 60),
        "minimum_consecutive_frames": _get_int(
            "minimum_consecutive_frames", global_settings, 2
        ),
        "minimum_iou_threshold": _get_optional(
            "minimum_iou_threshold", global_settings
        ),
        "high_conf_det_threshold": _get_optional(
            "high_conf_det_threshold", global_settings
        ),
        "tracker_frame_rate": _get_optional("tracker_frame_rate", global_settings),
        "track_smoothing_enabled": _get_bool(
            "track_smoothing_enabled", global_settings, True
        ),
        "track_smoothing_length": _get_int(
            "track_smoothing_length", global_settings, 5
        ),
        "zones_config_path": _resolve_project_path(
            _get_optional("zones_config_path", global_settings) or "configs/zones.yaml"
        ),
        "track_memory_enabled": _get_bool(
            "track_memory_enabled", global_settings, True
        ),
        "track_lost_ttl_ms": _get_int("track_lost_ttl_ms", global_settings, 1000),
        "track_lost_ttl_frames": _get_int(
            "track_lost_ttl_frames", global_settings, 15
        ),
        "track_min_hits": _get_int("track_min_hits", global_settings, 1),
        "track_smooth_alpha": _get_float(
            "track_smooth_alpha", global_settings, 0.65
        ),
        "track_publish_predicted": _get_bool(
            "track_publish_predicted", global_settings, True
        ),
        "track_count_predicted": _get_bool(
            "track_count_predicted", global_settings, True
        ),
        "track_predicted_conf_decay": _get_float(
            "track_predicted_conf_decay", global_settings, 0.85
        ),
        "track_min_predicted_conf": _get_float(
            "track_min_predicted_conf", global_settings, 0.20
        ),
        "track_reid_iou_threshold": _get_float(
            "track_reid_iou_threshold", global_settings, 0.15
        ),
        "track_reid_center_distance_px": _get_float(
            "track_reid_center_distance_px", global_settings, 120.0
        ),
        "health_check_interval_sec": global_settings.get(
            "health_check_interval_sec", 10
        ),
        "worker_graceful_shutdown_sec": global_settings.get(
            "worker_graceful_shutdown_sec", 10
        ),
        "reconnect_delay_max_sec": global_settings.get("reconnect_delay_max_sec", 30),
        "live_media_enabled": _get_bool("live_media_enabled", global_settings, True),
        "live_media_dir": _resolve_project_path(
            _get_optional("live_media_dir", global_settings) or "runtime/live_frames"
        ),
        "live_media_fps": _get_float("live_media_fps", global_settings, 10.0),
        "live_media_jpeg_quality": _get_int(
            "live_media_jpeg_quality", global_settings, 80
        ),
        "media_upload_enabled": _get_bool(
            "media_upload_enabled", global_settings, False
        ),
        "s3_endpoint": _get_s3_optional("s3_endpoint", global_settings),
        "s3_region": _get_s3_optional("s3_region", global_settings) or "us-east-1",
        "s3_bucket": _get_s3_optional("s3_bucket", global_settings) or "warehouse",
        "s3_access_key": _get_s3_credential("s3_access_key", global_settings),
        "s3_secret_key": _get_s3_credential("s3_secret_key", global_settings),
        "s3_path_style": _get_s3_bool("s3_path_style", global_settings, True),
        "frame_sampling_enabled": _get_bool(
            "frame_sampling_enabled", global_settings, True
        ),
        "frame_sample_interval_sec": _get_float(
            "frame_sample_interval_sec", global_settings, 1.0
        ),
        "frame_jpeg_quality": _get_int("frame_jpeg_quality", global_settings, 85),
        "frame_upload_workers": _get_int("frame_upload_workers", global_settings, 2),
        "frame_upload_inflight_limit": _get_int(
            "frame_upload_inflight_limit", global_settings, 8
        ),
        "alert_clip_enabled": _get_bool("alert_clip_enabled", global_settings, False),
        "alert_density_threshold": _get_int(
            "alert_density_threshold", global_settings, 10
        ),
        "alert_pre_buffer_sec": _get_int("alert_pre_buffer_sec", global_settings, 5),
        "alert_post_buffer_sec": _get_int("alert_post_buffer_sec", global_settings, 5),
        "alert_cooldown_sec": _get_int("alert_cooldown_sec", global_settings, 30),
        "clip_jpeg_quality": _get_int("clip_jpeg_quality", global_settings, 80),
        "clip_upload_workers": _get_int("clip_upload_workers", global_settings, 1),
    }


def _get(key: str, global_settings: Dict[str, Any]) -> Any:
    env_key = key.upper()
    env_val = os.getenv(env_key)
    if env_val is not None:
        if key == "conf_thres":
            return float(env_val)
        return env_val
    return global_settings.get(key)


def _get_vision_setting(key: str, global_settings: Dict[str, Any]) -> Any:
    """Resolve production Vision runtime settings.

    Legacy variables like MODEL_NAME/TRACKER_TYPE/CONF_THRES are still used in
    single-camera fallback mode, but multi-camera YAML should not be silently
    overridden by an old services/vision/.env. Use RVA_* for explicit overrides.
    """
    rva_env = os.getenv(f"RVA_{key.upper()}")
    if rva_env is not None and rva_env != "":
        return rva_env
    if key in global_settings and global_settings[key] is not None:
        return global_settings[key]
    return os.getenv(key.upper())


def _get_class_filter(global_settings: Dict[str, Any]) -> List[int]:
    env_str = os.getenv("CLASS_FILTER")
    if env_str:
        try:
            return json.loads(env_str)
        except Exception:
            pass
    return global_settings.get("class_filter", [0])


def _get_vision_class_filter(global_settings: Dict[str, Any]) -> List[int]:
    env_str = os.getenv("RVA_CLASS_FILTER")
    if env_str:
        try:
            return json.loads(env_str)
        except Exception:
            pass
    return global_settings.get("class_filter", _get_class_filter(global_settings))


def _get_frame_policy(global_settings: Dict[str, Any]) -> Dict[str, Any]:
    raw = global_settings.get("frame_policy")
    if not isinstance(raw, dict):
        mode = str(_get_optional("frame_policy_mode", global_settings) or "tracking_safe")
        return {
            "mode": mode,
            "max_queue_size": _get_int("frame_queue_size", global_settings, 4),
            "allow_drop": True,
            "max_consecutive_drops": 3,
        }
    return {
        "mode": str(raw.get("mode", "tracking_safe")),
        "max_queue_size": int(raw.get("max_queue_size", global_settings.get("frame_queue_size", 4))),
        "allow_drop": bool(raw.get("allow_drop", True)),
        "max_consecutive_drops": int(raw.get("max_consecutive_drops", 3)),
    }


def _get_frame_queue_size(global_settings: Dict[str, Any]) -> int:
    policy = _get_frame_policy(global_settings)
    return int(policy.get("max_queue_size", global_settings.get("frame_queue_size", 2)))


def _get_optional(key: str, global_settings: Dict[str, Any]) -> Any:
    for env_key in (f"RVA_{key.upper()}", key.upper()):
        env_val = os.getenv(env_key)
        if env_val is not None and env_val != "":
            return env_val
    return global_settings.get(key)


def _get_s3_optional(key: str, global_settings: Dict[str, Any]) -> Any:
    env_key = key.upper()
    for candidate in (
        os.getenv(f"RVA_{env_key}"),
        os.getenv(env_key),
        ROOT_ENV.get(env_key),
        global_settings.get(key),
    ):
        if candidate is not None and str(candidate) != "":
            return candidate
    return None


def _get_s3_bool(key: str, global_settings: Dict[str, Any], default: bool) -> bool:
    raw = _get_s3_optional(key, global_settings)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_project_path(raw_path: str) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        return str(path)
    return str(PROJECT_ROOT / path)


def _get_s3_credential(key: str, global_settings: Dict[str, Any]) -> Any:
    env_key = key.upper()
    for candidate in (
        os.getenv(env_key),
        ROOT_ENV.get(env_key),
        global_settings.get(key),
    ):
        if candidate is not None and str(candidate) != "":
            return candidate
    return None


def _get_bool(key: str, global_settings: Dict[str, Any], default: bool) -> bool:
    raw = _get_optional(key, global_settings)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(key: str, global_settings: Dict[str, Any], default: int) -> int:
    raw = _get_optional(key, global_settings)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _get_float(key: str, global_settings: Dict[str, Any], default: float) -> float:
    raw = _get_optional(key, global_settings)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _fallback_single_camera() -> Dict[str, Any]:
    """Fallback to single-camera mode using .env settings."""
    return {
        "cameras": [
            {
                "camera_id": settings.CAMERA_ID,
                "store_id": settings.STORE_ID,
                "source_type": "video_file",
                "source_uri": settings.VIDEO_PATH,
                "fps_target": 25,
            }
        ],
        "pulsar_service_url": settings.PULSAR_SERVICE_URL,
        "pulsar_topic": settings.PULSAR_TOPIC,
        "pulsar_media_topic": settings.PULSAR_MEDIA_TOPIC,
        "model_name": settings.MODEL_NAME,
        "tracker_type": settings.TRACKER_TYPE,
        "conf_thres": settings.CONF_THRES,
        "class_filter": settings.CLASS_FILTER,
        "frame_policy": {"mode": "tracking_safe", "max_queue_size": 4, "allow_drop": True},
        "frame_queue_size": 4,
        "event_schema_version": "1.0",
        "publish_vision_facts": True,
        "detector_type": "ultralytics_yolo",
        "detector_iou": 0.70,
        "detector_imgsz": 1280,
        "detector_half": True,
        "track_activation_threshold": 0.20,
        "lost_track_buffer": 60,
        "minimum_consecutive_frames": 2,
        "minimum_iou_threshold": None,
        "high_conf_det_threshold": None,
        "tracker_frame_rate": None,
        "track_smoothing_enabled": True,
        "track_smoothing_length": 5,
        "zones_config_path": _resolve_project_path("configs/zones.yaml"),
        "track_memory_enabled": _get_bool("track_memory_enabled", {}, True),
        "track_lost_ttl_ms": _get_int("track_lost_ttl_ms", {}, 1000),
        "track_lost_ttl_frames": _get_int("track_lost_ttl_frames", {}, 15),
        "track_min_hits": _get_int("track_min_hits", {}, 1),
        "track_smooth_alpha": _get_float("track_smooth_alpha", {}, 0.65),
        "track_publish_predicted": _get_bool("track_publish_predicted", {}, True),
        "track_count_predicted": _get_bool("track_count_predicted", {}, True),
        "track_predicted_conf_decay": _get_float(
            "track_predicted_conf_decay", {}, 0.85
        ),
        "track_min_predicted_conf": _get_float(
            "track_min_predicted_conf", {}, 0.20
        ),
        "track_reid_iou_threshold": _get_float(
            "track_reid_iou_threshold", {}, 0.15
        ),
        "track_reid_center_distance_px": _get_float(
            "track_reid_center_distance_px", {}, 120.0
        ),
        "health_check_interval_sec": 10,
        "worker_graceful_shutdown_sec": 10,
        "reconnect_delay_max_sec": 30,
        "live_media_enabled": _get_bool("live_media_enabled", {}, True),
        "live_media_dir": _resolve_project_path(
            os.getenv("RVA_LIVE_MEDIA_DIR")
            or os.getenv("LIVE_MEDIA_DIR", "runtime/live_frames")
        ),
        "live_media_fps": _get_float("live_media_fps", {}, 10.0),
        "live_media_jpeg_quality": _get_int("live_media_jpeg_quality", {}, 80),
        "media_upload_enabled": _get_bool("media_upload_enabled", {}, False),
        "s3_endpoint": os.getenv("S3_ENDPOINT", ""),
        "s3_region": os.getenv("S3_REGION", "us-east-1"),
        "s3_bucket": os.getenv("S3_BUCKET", "warehouse"),
        "s3_access_key": os.getenv("S3_ACCESS_KEY", ""),
        "s3_secret_key": os.getenv("S3_SECRET_KEY", ""),
        "s3_path_style": _get_bool("s3_path_style", {}, False),
        "frame_sampling_enabled": _get_bool("frame_sampling_enabled", {}, True),
        "frame_sample_interval_sec": _get_float("frame_sample_interval_sec", {}, 1.0),
        "frame_jpeg_quality": _get_int("frame_jpeg_quality", {}, 85),
        "frame_upload_workers": _get_int("frame_upload_workers", {}, 2),
        "frame_upload_inflight_limit": _get_int("frame_upload_inflight_limit", {}, 8),
        "alert_clip_enabled": _get_bool("alert_clip_enabled", {}, False),
        "alert_density_threshold": _get_int("alert_density_threshold", {}, 10),
        "alert_pre_buffer_sec": _get_int("alert_pre_buffer_sec", {}, 5),
        "alert_post_buffer_sec": _get_int("alert_post_buffer_sec", {}, 5),
        "alert_cooldown_sec": _get_int("alert_cooldown_sec", {}, 30),
        "clip_jpeg_quality": _get_int("clip_jpeg_quality", {}, 80),
        "clip_upload_workers": _get_int("clip_upload_workers", {}, 1),
    }
