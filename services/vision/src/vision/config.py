"""Pydantic settings for the vision service.

Loaded from environment variables (.env or Docker env).
Camera-level config (RTSP URLs, FPS) is loaded from configs/cameras.yaml.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class VisionSettings(BaseSettings):
    """Global vision service settings from environment."""

    # Model
    model_path: str = Field("data/models/yolo11n.pt", alias="VISION_MODEL_PATH")
    device: str = Field("cuda:0", alias="VISION_DEVICE")
    conf_threshold: float = Field(0.5, alias="VISION_CONFIDENCE_THRESHOLD")
    iou_threshold: float = Field(0.45, alias="VISION_IOU_THRESHOLD")

    # Camera config file
    cameras_config_path: str = Field("configs/cameras.yaml", alias="CAMERAS_CONFIG_PATH")

    # Google Cloud Storage
    gcs_project_id: str = Field(..., alias="GCS_PROJECT_ID")
    gcs_bucket_name: str = Field(..., alias="GCS_BUCKET_NAME")

    # Apache Pulsar
    pulsar_service_url: str = Field("pulsar://pulsar:6650", alias="PULSAR_SERVICE_URL")
    pulsar_topic: str = Field(
        "persistent://rva/ingest/detections",
        alias="PULSAR_TOPIC_DETECTIONS",
    )

    # Redis
    redis_url: str = Field("redis://redis:6379", alias="REDIS_URL")

    # PostgreSQL
    postgres_dsn: str = Field(
        "postgresql://rva:rva_secret@postgres:5432/rva_metadata",
        alias="POSTGRES_DSN",
    )

    model_config = {"populate_by_name": True, "env_file": ".env", "extra": "ignore"}
