"""S3 client abstraction — shared by vision, API, and tooling."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class S3ClientConfig:
    endpoint_url: str | None
    region_name: str
    bucket: str
    access_key: str | None = None
    secret_key: str | None = None
    path_style: bool = True


def create_s3_client(config: S3ClientConfig) -> Any | None:
    """Create a boto3 S3 client.

    Returns None when boto3 is not installed — the pipeline
    can run without media upload when S3 is unavailable.
    """
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        logger.warning("boto3 is not installed; S3 media upload is disabled")
        return None

    client_kwargs: dict[str, Any] = {
        "service_name": "s3",
        "region_name": config.region_name,
    }

    if config.endpoint_url:
        client_kwargs["endpoint_url"] = config.endpoint_url
    if config.access_key:
        client_kwargs["aws_access_key_id"] = config.access_key
    if config.secret_key:
        client_kwargs["aws_secret_access_key"] = config.secret_key
    if config.path_style:
        client_kwargs["config"] = Config(s3={"addressing_style": "path"})

    return boto3.client(**client_kwargs)


def build_s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"
