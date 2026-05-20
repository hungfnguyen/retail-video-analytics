"""Shared constants for the RVA platform."""

# Event schema
SCHEMA_VERSION = "1.0"

# Topic naming
TOPIC_DETECTION_FRAMES = "persistent://retail/metadata/events"
TOPIC_MEDIA_EVENTS = "persistent://retail/metadata/media-events"
TOPIC_DLQ = "persistent://retail/metadata/dlq-events"
TOPIC_TRACK_LIFECYCLE = "persistent://retail/ops/track-lifecycle-v1"
TOPIC_ALERTS = "persistent://retail/ops/alerts-v1"
TOPIC_SYSTEM_METRICS = "persistent://retail/ops/system-metrics-v1"

# Detection
DEFAULT_CLASS_FILTER = [0]  # person only
DEFAULT_CONF_THRES = 0.25

# Media upload
DEFAULT_FRAME_SAMPLE_INTERVAL_SEC = 1.0
DEFAULT_JPEG_QUALITY = 85
DEFAULT_CLIP_JPEG_QUALITY = 80
DEFAULT_ALERT_COOLDOWN_SEC = 30
DEFAULT_ALERT_DENSITY_THRESHOLD = 10
DEFAULT_PRE_BUFFER_SEC = 5
DEFAULT_POST_BUFFER_SEC = 5

# Vision pipeline
DEFAULT_FPS_TARGET = 25
DEFAULT_FRAME_QUEUE_SIZE = 2
DEFAULT_HEALTH_CHECK_INTERVAL_SEC = 10
DEFAULT_GRACEFUL_SHUTDOWN_SEC = 10
DEFAULT_RECONNECT_DELAY_MAX_SEC = 30
