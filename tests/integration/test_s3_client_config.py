"""Integration tests for S3 client config. Does NOT require running S3."""

import pytest

from storage.s3_client import S3ClientConfig, build_s3_uri


class TestS3ClientConfig:
    def test_minimal_config(self):
        config = S3ClientConfig(
            endpoint_url=None,
            region_name="ap-southeast-1",
            bucket="test-bucket",
        )
        assert config.region_name == "ap-southeast-1"
        assert config.path_style is True

    def test_full_config(self):
        config = S3ClientConfig(
            endpoint_url="http://minio:9000",
            region_name="us-east-1",
            bucket="warehouse",
            access_key="minioadmin",
            secret_key="minioadmin123",
            path_style=True,
        )
        assert config.endpoint_url == "http://minio:9000"

    def test_frozen_dataclass(self):
        config = S3ClientConfig(
            endpoint_url=None,
            region_name="us-east-1",
            bucket="test",
        )
        with pytest.raises(Exception):
            config.bucket = "other"  # type: ignore


class TestBuildS3Uri:
    def test_simple_uri(self):
        uri = build_s3_uri("my-bucket", "frames/2026-05-11/cam_01/10h/img.jpg")
        assert uri == "s3://my-bucket/frames/2026-05-11/cam_01/10h/img.jpg"
