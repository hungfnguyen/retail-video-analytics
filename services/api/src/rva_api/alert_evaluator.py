"""Background alert evaluator — reads Redis condition state on a tick and writes alerts."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.settings import load_yaml_config
from rva_api.alerting import is_business_alert_type
from rva_api.api.v1.analytics_queries import (
    ensure_alert_history_table,
    insert_alert_history_sql,
    trino_execute,
)
from storage import RedisClientConfig, create_redis_client

log = logging.getLogger(__name__)

EVAL_INTERVAL_SEC = 10
ALERT_STORE_TTL = 86_400  # 24h
ALERT_STORE_MAX = 25

_evaluator_client: Any | None = None
_s3_client: Any | None = None
_s3_bucket: str = ""
_live_media_redis_client: Any | None = None


def _redis_config() -> RedisClientConfig:
    return RedisClientConfig(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", os.getenv("REDIS_HOST_PORT", "16379"))),
        password=os.getenv("REDIS_PASSWORD") or None,
        db=int(os.getenv("REDIS_DB", "0")),
    )


def _get_client() -> Any:
    global _evaluator_client
    if _evaluator_client is None:
        _evaluator_client = create_redis_client(_redis_config())
    return _evaluator_client


def _live_media_transport() -> str:
    return str(
        os.getenv("RVA_LIVE_MEDIA_TRANSPORT")
        or os.getenv("LIVE_MEDIA_TRANSPORT")
        or "file"
    ).strip().lower()


def _live_media_redis_prefix() -> str:
    return str(
        os.getenv("RVA_LIVE_MEDIA_REDIS_PREFIX")
        or os.getenv("LIVE_MEDIA_REDIS_PREFIX")
        or "live:frame"
    )


def _live_media_redis_config() -> RedisClientConfig:
    return RedisClientConfig(
        host=str(
            os.getenv("RVA_LIVE_REDIS_HOST")
            or os.getenv("LIVE_REDIS_HOST")
            or os.getenv("REDIS_HOST", "localhost")
        ),
        port=int(
            os.getenv("RVA_LIVE_REDIS_PORT")
            or os.getenv("LIVE_REDIS_PORT")
            or os.getenv("REDIS_HOST_PORT")
            or os.getenv("REDIS_PORT", "16379")
        ),
        password=os.getenv("RVA_LIVE_REDIS_PASSWORD")
        or os.getenv("LIVE_REDIS_PASSWORD")
        or os.getenv("REDIS_PASSWORD")
        or None,
        db=int(
            os.getenv("RVA_LIVE_REDIS_DB")
            or os.getenv("LIVE_REDIS_DB")
            or os.getenv("REDIS_DB", "0")
        ),
        decode_responses=False,
    )


def _get_live_media_client() -> Any | None:
    global _live_media_redis_client
    if _live_media_redis_client is not None:
        return _live_media_redis_client
    _live_media_redis_client = create_redis_client(_live_media_redis_config())
    return _live_media_redis_client


def _live_media_frame_key(cam: str) -> str:
    return f"{_live_media_redis_prefix()}:bytes:{cam}"


def _get_s3() -> tuple[Any, str] | tuple[None, str]:
    global _s3_client, _s3_bucket
    if _s3_client is not None:
        return _s3_client, _s3_bucket
    bucket = os.getenv("S3_BUCKET", "")
    if not bucket:
        return None, ""
    try:
        from storage import S3ClientConfig, create_s3_client
        config = S3ClientConfig(
            endpoint_url=os.getenv("S3_ENDPOINT") or None,
            region_name=os.getenv("S3_REGION", "us-east-1"),
            bucket=bucket,
            access_key=os.getenv("S3_ACCESS_KEY") or None,
            secret_key=os.getenv("S3_SECRET_KEY") or None,
        )
        _s3_client = create_s3_client(config)
        _s3_bucket = bucket
    except Exception:
        log.warning("snapshot S3 client init failed")
        return None, ""
    return _s3_client, _s3_bucket


def _upload_snapshot(cam: str, alert_id: str) -> str:
    """Read the current live JPEG for cam and upload to S3. Returns S3 key or ''."""
    if _live_media_transport() == "redis":
        live_media_client = _get_live_media_client()
        if live_media_client is None:
            return ""
        frame_bytes = live_media_client.get(_live_media_frame_key(cam))
        if not frame_bytes:
            return ""
    else:
        live_frames_dir = os.getenv("LIVE_FRAMES_DIR", "runtime/live_frames")
        frame_path = Path(live_frames_dir) / f"{cam}.jpg"
        if not frame_path.exists():
            return ""
        frame_bytes = frame_path.read_bytes()

    s3, bucket = _get_s3()
    if s3 is None:
        return ""
    key = f"snapshots/{cam}/{alert_id}.jpg"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=frame_bytes, ContentType="image/jpeg")
        log.debug("snapshot uploaded: %s", key)
        return key
    except Exception:
        log.warning("snapshot upload failed for %s / %s", cam, alert_id)
        return ""


def _load_alert_config() -> tuple[list[str], dict[str, Any], dict[str, str]]:
    config_path = Path(os.getenv("RVA_CAMERA_CONFIG", "configs/cameras.yaml"))
    if not config_path.exists():
        example = config_path.with_name("cameras.yaml.example")
        if example.exists():
            config_path = example
    cfg = load_yaml_config(config_path)
    cameras = cfg.get("cameras", [])
    camera_store_ids: dict[str, str] = {}
    camera_ids = [
        c["camera_id"]
        for c in cameras
        if isinstance(c, dict) and c.get("enabled", True) and c.get("camera_id")
    ]
    for camera in cameras:
        if not isinstance(camera, dict):
            continue
        camera_id = str(camera.get("camera_id") or "")
        if not camera_id or not camera.get("enabled", True):
            continue
        camera_store_ids[camera_id] = str(camera.get("store_id") or "store_001")
    settings = cfg.get("settings", {}) if isinstance(cfg, dict) else {}
    return camera_ids, settings, camera_store_ids


def _invalidate_alert_history_cache(client: Any) -> None:
    try:
        keys = list(client.scan_iter("analytics:cache:v2:alerts:*"))
    except Exception:
        return
    if not keys:
        return
    try:
        client.delete(*keys)
    except Exception:
        return


def _write_alert_history(record: dict[str, str], client: Any) -> None:
    if not is_business_alert_type(record.get("alert_type")):
        return
    try:
        ensure_alert_history_table()
        trino_execute(insert_alert_history_sql(record), 15.0)
    except Exception:
        log.exception("alert history insert failed for %s", record.get("alert_id"))
        return
    _invalidate_alert_history_cache(client)


def _write_live_alert_record(client: Any, record: dict[str, str], ts_ms: int) -> None:
    alert_id = str(record["alert_id"])
    camera_id = str(record["camera_id"])
    pipe = client.pipeline()
    pipe.hset(f"alert:item:{alert_id}", mapping=record)
    pipe.expire(f"alert:item:{alert_id}", ALERT_STORE_TTL)
    pipe.zadd(f"alert:live:{camera_id}", {alert_id: float(ts_ms)})
    pipe.expire(f"alert:live:{camera_id}", ALERT_STORE_TTL)
    pipe.zremrangebyrank(f"alert:live:{camera_id}", 0, -(ALERT_STORE_MAX + 1))
    pipe.execute()


def _maybe_emit(
    client: Any,
    cam: str,
    store_id: str,
    zone: str,
    alert_type: str,
    severity: str,
    title: str,
    description: str,
    cooldown_sec: int,
) -> dict[str, str] | None:
    """Emit alert if not on cooldown. Returns the alert record if emitted."""
    cooldown_key = f"alert:cooldown:{cam}:{zone}:{alert_type}"
    # SET NX EX is atomic — only the first uvicorn worker to acquire this key
    # proceeds; all other workers see None and skip, preventing duplicate alerts
    # when running with --workers > 1.
    if not client.set(cooldown_key, 1, ex=cooldown_sec, nx=True):
        return None

    now = datetime.now(timezone.utc)
    ts_ms = int(now.timestamp() * 1000)
    alert_id = f"{cam}_{zone}_{alert_type}_{ts_ms}"

    record: dict[str, str] = {
        "alert_id": alert_id,
        "store_id": store_id,
        "camera_id": cam,
        "alert_type": alert_type,
        "severity": severity,
        "title": title,
        "description": description,
        "zone": zone,
        "event_ts": now.isoformat(),
        "status": "new",
        "track_id": "",
        "snapshot_key": "",
        "clip_s3_key": "",
        "clip_s3_uri": "",
    }

    _write_live_alert_record(client, record, ts_ms)
    log.info("alert emitted: %s", alert_id)
    return record


def _check_queue_zones(
    client: Any,
    cam: str,
    store_id: str,
    overcrowded_threshold: int,
    long_wait_ms: int,
    cooldown_sec: int,
) -> None:
    queue_keys = list(client.scan_iter(f"queue:live:{cam}:*"))
    if not queue_keys:
        return

    zone_counts_hash: dict[str, str] = client.hgetall(f"zone:count:{cam}") or {}

    pipe = client.pipeline(transaction=False)
    for k in queue_keys:
        pipe.hgetall(k)
    queue_results = pipe.execute()

    for key, result in zip(queue_keys, queue_results):
        if not result:
            continue
        key_str = key if isinstance(key, str) else key.decode()
        zone_id = key_str.split(":")[-1]

        count = int(zone_counts_hash.get(zone_id, 0) or 0)
        max_wait = int(result.get("max_wait_ms", 0) or 0)
        avg_wait = int(result.get("avg_wait_ms", 0) or 0)

        if count >= overcrowded_threshold:
            record = _maybe_emit(
                client, cam, store_id, zone_id, "queue_overcrowded", "high",
                f"Queue overcrowded — {zone_id.replace('_', ' ')}",
                f"{count} people waiting in queue",
                cooldown_sec,
            )
            if record is not None:
                snap = _upload_snapshot(cam, record["alert_id"])
                if snap:
                    record["snapshot_key"] = snap
                    client.hset(f"alert:item:{record['alert_id']}", "snapshot_key", snap)
                _write_alert_history(record, client)

        if max_wait > long_wait_ms:
            max_m, max_s = divmod(max_wait // 1000, 60)
            avg_m, avg_s = divmod(avg_wait // 1000, 60)
            record = _maybe_emit(
                client, cam, store_id, zone_id, "long_wait", "medium",
                f"Long wait — {zone_id.replace('_', ' ')}",
                f"Max {max_m}m {max_s:02d}s, avg {avg_m}m {avg_s:02d}s",
                cooldown_sec,
            )
            if record is not None:
                snap = _upload_snapshot(cam, record["alert_id"])
                if snap:
                    record["snapshot_key"] = snap
                    client.hset(f"alert:item:{record['alert_id']}", "snapshot_key", snap)
                _write_alert_history(record, client)


def _evaluate_once(
    client: Any,
    camera_ids: list[str],
    settings: dict[str, Any],
    camera_store_ids: dict[str, str],
) -> None:
    overcrowded = int(settings.get("alert_queue_overcrowded_threshold", 5))
    long_wait = int(settings.get("alert_long_wait_ms", 120_000))
    cooldown = int(settings.get("alert_cooldown_sec", 60))

    for cam in camera_ids:
        _check_queue_zones(
            client,
            cam,
            camera_store_ids.get(cam, "store_001"),
            overcrowded,
            long_wait,
            cooldown,
        )


def _write_clip_alert(client: Any, event: dict[str, Any]) -> None:
    source = event.get("source") or {}
    cam = source.get("camera_id", "")
    if not cam:
        return
    alert_id = event.get("alert_id", "")
    if not cam or not alert_id:
        return

    cooldown_key = f"alert:cooldown:{cam}:clip:{alert_id}"
    if client.exists(cooldown_key):
        return

    alert_type = event.get("alert_type", "density_high")
    if not is_business_alert_type(alert_type):
        return
    now = datetime.now(timezone.utc)
    ts_ms = int(now.timestamp() * 1000)
    duration = event.get("clip_duration_sec") or 0
    record: dict[str, str] = {
        "alert_id": alert_id,
        "store_id": str(source.get("store_id") or "store_001"),
        "camera_id": cam,
        "alert_type": alert_type,
        "severity": "high",
        "title": "High density detected" if alert_type == "density_high" else f"Incident clip — {alert_type.replace('_', ' ')}",
        "description": (
            f"Current density incident on camera {cam} — {duration:.0f}s clip recorded"
            if alert_type == "density_high"
            else f"Camera {cam} — {duration:.0f}s clip recorded"
        ),
        "zone": str(event.get("zone") or source.get("zone") or "camera"),
        "event_ts": event.get("trigger_ts", now.isoformat()),
        "status": "new",
        "track_id": "",
        "clip_s3_key": event.get("clip_s3_key", ""),
        "clip_s3_uri": event.get("clip_s3_uri", ""),
        "snapshot_key": _upload_snapshot(cam, alert_id) or "",
    }

    pipe = client.pipeline()
    pipe.hset(f"alert:item:{alert_id}", mapping=record)
    pipe.expire(f"alert:item:{alert_id}", ALERT_STORE_TTL)
    pipe.zadd(f"alert:live:{cam}", {alert_id: float(ts_ms)})
    pipe.expire(f"alert:live:{cam}", ALERT_STORE_TTL)
    pipe.zremrangebyrank(f"alert:live:{cam}", 0, -(ALERT_STORE_MAX + 1))
    pipe.set(cooldown_key, 1, ex=3600)
    pipe.execute()
    _write_alert_history(record, client)
    log.info("clip alert written: %s", alert_id)


def _media_consumer_loop(client: Any) -> None:
    """Daemon thread: consume clip_created events from Pulsar media-events."""
    pulsar_url = os.getenv("PULSAR_SERVICE_URL", "pulsar://localhost:6650")
    topic = "persistent://retail/metadata/media-events"
    subscription = "alert-evaluator-media-sub"

    try:
        from messaging.pulsar import PulsarConsumer
        consumer = PulsarConsumer(
            service_url=pulsar_url,
            topic=topic,
            subscription=subscription,
        )
    except Exception:
        log.warning("alert media consumer: Pulsar unavailable — clip alerts disabled")
        return

    log.info("alert media consumer: subscribed to %s", topic)
    try:
        while True:
            try:
                event = consumer.receive(timeout_millis=5000)
                if event and event.get("event_type") == "clip_created":
                    _write_clip_alert(client, event)
            except Exception:
                log.exception("alert media consumer: error processing event (continuing)")
    finally:
        try:
            consumer.close()
        except Exception:
            pass


async def run_alert_evaluator() -> None:
    """Async background loop — starts with the API lifespan, runs until cancelled."""
    try:
        camera_ids, settings, camera_store_ids = _load_alert_config()
    except Exception:
        log.exception("alert evaluator: failed to load config, not starting")
        return

    if not camera_ids:
        log.warning("alert evaluator: no enabled cameras found, not starting")
        return

    log.info("alert evaluator started — cameras: %s", camera_ids)

    client = _get_client()
    if client is None:
        log.warning("alert evaluator: Redis unavailable, not starting")
        return

    try:
        ensure_alert_history_table()
    except Exception:
        log.exception("alert evaluator: failed to prepare alert history table")

    import threading
    media_thread = threading.Thread(
        target=_media_consumer_loop,
        args=(client,),
        daemon=True,
        name="alert-media-consumer",
    )
    media_thread.start()

    while True:
        try:
            # Run sync Redis calls in a thread so the async event loop is not blocked
            await asyncio.to_thread(_evaluate_once, client, camera_ids, settings, camera_store_ids)
        except Exception:
            log.exception("alert evaluator: evaluation error (continuing)")
        try:
            await asyncio.sleep(EVAL_INTERVAL_SEC)
        except asyncio.CancelledError:
            log.info("alert evaluator stopped")
            return
