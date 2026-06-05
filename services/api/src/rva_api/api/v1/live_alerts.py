from __future__ import annotations

import json
from typing import Any

RECENT_ALERT_LIMIT = 20


def _decode_redis_text(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    if isinstance(raw, str):
        return raw
    return str(raw)


def _safe_int(raw: Any) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _normalize_severity(raw: Any) -> str:
    value = str(raw or "low").lower()
    return value if value in {"low", "medium", "high"} else "low"


def _normalize_status(raw: Any) -> str:
    value = str(raw or "new").lower()
    return value if value in {"new", "acknowledged", "resolved"} else "new"


def _normalize_alert(record: dict[str, Any]) -> dict[str, Any] | None:
    alert_id = str(record.get("alert_id") or "")
    camera_id = str(record.get("camera_id") or "")
    event_ts = str(record.get("event_ts") or record.get("trigger_ts") or "")
    if not alert_id or not camera_id or not event_ts:
        return None

    alert_type = str(record.get("alert_type") or record.get("event_type") or "alert")
    title = str(record.get("title") or alert_type.replace("_", " ").title())
    description = str(record.get("description") or record.get("message") or "")
    trigger_value = _safe_int(
        record.get("trigger_value") or record.get("current_count")
    )
    threshold = _safe_int(record.get("threshold"))

    return {
        "alert_id": alert_id,
        "store_id": str(record.get("store_id") or ""),
        "camera_id": camera_id,
        "alert_type": alert_type,
        "title": title,
        "description": description,
        "severity": _normalize_severity(record.get("severity")),
        "zone": str(record.get("zone") or ""),
        "track_id": _safe_int(record.get("track_id")),
        "event_ts": event_ts,
        "status": _normalize_status(record.get("status")),
        "trigger_value": trigger_value,
        "threshold": threshold,
        "clip_s3_key": record.get("clip_s3_key"),
        "clip_s3_uri": record.get("clip_s3_uri"),
    }


def read_recent_alerts(
    client: Any, camera_id: str, store_id: str | None = None
) -> list[dict[str, Any]]:
    keys = [f"alerts:recent:{camera_id}"]
    if store_id:
        keys.append(f"alerts:recent:store:{store_id}")

    alerts_by_id: dict[str, dict[str, Any]] = {}
    for key in keys:
        try:
            raw_records = client.lrange(key, 0, RECENT_ALERT_LIMIT - 1)
        except Exception:
            continue

        for raw in raw_records:
            text = _decode_redis_text(raw)
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            alert = _normalize_alert(record)
            if alert is not None:
                alerts_by_id[alert["alert_id"]] = alert

    return sorted(
        alerts_by_id.values(),
        key=lambda alert: str(alert.get("event_ts") or ""),
        reverse=True,
    )[:RECENT_ALERT_LIMIT]
