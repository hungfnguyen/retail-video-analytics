from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from rva_api.alerting import is_business_alert_type
from rva_api.schemas.live import Alert
from storage import RedisClientConfig, S3ClientConfig, create_redis_client, create_s3_client

router = APIRouter(prefix="/alerts", tags=["alerts"])

_alerts_redis_client: Any | None = None


def _redis_config() -> RedisClientConfig:
    return RedisClientConfig(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", os.getenv("REDIS_HOST_PORT", "16379"))),
        password=os.getenv("REDIS_PASSWORD") or None,
        db=int(os.getenv("REDIS_DB", "0")),
    )


def _get_redis_client() -> Any:
    global _alerts_redis_client
    if _alerts_redis_client is None:
        _alerts_redis_client = create_redis_client(_redis_config())
    if _alerts_redis_client is None:
        raise HTTPException(status_code=503, detail="Redis realtime state is unavailable")
    return _alerts_redis_client


def _s3_client_and_bucket() -> tuple[Any, str]:
    bucket = os.getenv("S3_BUCKET", "warehouse")
    config = S3ClientConfig(
        endpoint_url=os.getenv("S3_ENDPOINT") or None,
        region_name=os.getenv("S3_REGION", "us-east-1"),
        bucket=bucket,
        access_key=os.getenv("S3_ACCESS_KEY") or None,
        secret_key=os.getenv("S3_SECRET_KEY") or None,
        path_style=True,
    )
    client = create_s3_client(config)
    if client is None:
        raise HTTPException(status_code=503, detail="S3 unavailable (boto3 not installed)")
    return client, bucket


def _parse_alert(r: dict[str, Any]) -> Alert | None:
    if not r:
        return None
    try:
        clean = {k: v for k, v in r.items() if v != ""}
        if not is_business_alert_type(clean.get("alert_type")):
            return None
        clean.pop("track_id", None)
        if not clean.get("clip_s3_key"):
            clean.pop("clip_s3_key", None)
        if not clean.get("snapshot_key"):
            clean.pop("snapshot_key", None)
        return Alert.model_validate(clean)
    except Exception:
        return None


@router.get("", response_model=list[Alert])
def list_alerts(
    camera_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[Alert]:
    client = _get_redis_client()

    if camera_id:
        cam_keys = [camera_id]
    else:
        cam_keys = [
            k.replace("alert:live:", "") if isinstance(k, str) else k.decode().replace("alert:live:", "")
            for k in client.scan_iter("alert:live:*")
        ]

    alert_ids: list[str] = []
    for cam in cam_keys:
        ids = client.zrevrange(f"alert:live:{cam}", 0, max(limit * 5, 25) - 1)
        if ids:
            alert_ids.extend(ids if isinstance(ids[0], str) else [i.decode() for i in ids])

    if not alert_ids:
        return []

    pipe = client.pipeline(transaction=False)
    for aid in alert_ids:
        pipe.hgetall(f"alert:item:{aid}")
    raw_results = pipe.execute()

    alerts: list[Alert] = []
    for r in raw_results:
        if status and r.get("status") != status:
            continue
        parsed = _parse_alert(r)
        if parsed:
            alerts.append(parsed)

    alerts.sort(key=lambda a: a.event_ts, reverse=True)
    return alerts[:limit]


@router.get("/{alert_id}/clip")
def get_alert_clip(alert_id: str) -> RedirectResponse:
    client = _get_redis_client()
    clip_key = client.hget(f"alert:item:{alert_id}", "clip_s3_key")
    if not clip_key:
        raise HTTPException(status_code=404, detail="No clip available for this alert")

    s3, bucket = _s3_client_and_bucket()
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": clip_key},
        ExpiresIn=300,
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/{alert_id}/snapshot")
def get_alert_snapshot(alert_id: str) -> RedirectResponse:
    client = _get_redis_client()
    snap_key = client.hget(f"alert:item:{alert_id}", "snapshot_key")
    if not snap_key:
        raise HTTPException(status_code=404, detail="No snapshot available for this alert")

    s3, bucket = _s3_client_and_bucket()
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": snap_key},
        ExpiresIn=300,
    )
    return RedirectResponse(url=url, status_code=302)


@router.post("/{alert_id}/ack")
def acknowledge_alert(alert_id: str) -> dict[str, str]:
    client = _get_redis_client()
    key = f"alert:item:{alert_id}"
    if not client.exists(key):
        raise HTTPException(status_code=404, detail="Alert not found")
    camera_id = client.hget(key, "camera_id") or ""
    pipe = client.pipeline()
    pipe.hset(key, "status", "acknowledged")
    if camera_id:
        pipe.zrem(f"alert:live:{camera_id}", alert_id)
    pipe.execute()
    return {"status": "ok"}
