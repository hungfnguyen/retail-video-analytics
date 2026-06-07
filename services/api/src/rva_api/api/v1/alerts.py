from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException

from rva_api.schemas.live import Alert
from storage import RedisClientConfig, create_redis_client

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
        ids = client.zrevrange(f"alert:live:{cam}", 0, limit - 1)
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
        if not r:
            continue
        if status and r.get("status") != status:
            continue
        try:
            if not r.get("track_id"):
                r.pop("track_id", None)
            alerts.append(Alert.model_validate(r))
        except Exception:
            continue

    alerts.sort(key=lambda a: a.event_ts, reverse=True)
    return alerts[:limit]


@router.post("/{alert_id}/ack")
def acknowledge_alert(alert_id: str) -> dict[str, str]:
    client = _get_redis_client()
    key = f"alert:item:{alert_id}"
    if not client.exists(key):
        raise HTTPException(status_code=404, detail="Alert not found")
    client.hset(key, "status", "acknowledged")
    return {"status": "ok"}
