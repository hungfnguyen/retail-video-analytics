from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_SEC = 0.7
HEALTH_CACHE_TTL_SEC = 5.0
_health_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _service_result(
    *,
    service: str,
    display_name: str,
    role: str,
    status: str,
    now: datetime,
    latency_ms: int,
) -> dict[str, Any]:
    return {
        "service": service,
        "display_name": display_name,
        "role": role,
        "status": status,
        "last_check_ts": now.isoformat(),
        "latency_ms": latency_ms,
    }


def _http_get_json(url: str, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> tuple[int, int, Any]:
    start = time.perf_counter()
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            body = response.read(128 * 1024)
            latency_ms = max(0, int((time.perf_counter() - start) * 1000))
            if not body:
                return response.status, latency_ms, None
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                payload = None
            return response.status, latency_ms, payload
    except HTTPError as exc:
        latency_ms = max(0, int((time.perf_counter() - start) * 1000))
        return exc.code, latency_ms, None
    except (OSError, URLError, TimeoutError):
        latency_ms = max(0, int((time.perf_counter() - start) * 1000))
        return 0, latency_ms, None


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _cached_health(key: str, factory: Any) -> dict[str, Any]:
    cached = _health_cache.get(key)
    now_monotonic = time.monotonic()
    if cached and now_monotonic - cached[0] < HEALTH_CACHE_TTL_SEC:
        return cached[1]

    result = factory()
    _health_cache[key] = (now_monotonic, result)
    return result


def redis_health(now: datetime, redis_latency_ms: int) -> dict[str, Any]:
    return _service_result(
        service="redis",
        display_name="Redis",
        role="Realtime State",
        status="ok",
        now=now,
        latency_ms=redis_latency_ms,
    )


def fastapi_health(now: datetime, frame_status: str) -> dict[str, Any]:
    return _service_result(
        service="fastapi",
        display_name="FastAPI",
        role="Serving API",
        status="ok" if frame_status == "stable" else "warning",
        now=now,
        latency_ms=0,
    )


def flink_health(now: datetime) -> dict[str, Any]:
    def check() -> dict[str, Any]:
        base_url = os.getenv("FLINK_REST_URL", "http://localhost:8081")
        status_code, latency_ms, payload = _http_get_json(_join_url(base_url, "/jobs/overview"))
        status = "down"
        if status_code == 200 and isinstance(payload, dict):
            jobs = payload.get("jobs")
            status = "ok" if isinstance(jobs, list) and any(
                job.get("state") == "RUNNING" for job in jobs
            ) else "warning"

        return _service_result(
            service="flink",
            display_name="Flink",
            role="Stream Processing",
            status=status,
            now=now,
            latency_ms=latency_ms,
        )

    return _cached_health("flink", check)


def pulsar_health(now: datetime) -> dict[str, Any]:
    def check() -> dict[str, Any]:
        base_url = os.getenv("PULSAR_ADMIN_URL", "http://localhost:8084")
        status_code, latency_ms, _ = _http_get_json(_join_url(base_url, "/admin/v2/brokers/health"))
        status = "ok" if status_code == 200 else "down"

        return _service_result(
            service="pulsar",
            display_name="Pulsar",
            role="Message Broker",
            status=status,
            now=now,
            latency_ms=latency_ms,
        )

    return _cached_health("pulsar", check)


def minio_health(now: datetime) -> dict[str, Any]:
    def check() -> dict[str, Any]:
        endpoint = os.getenv("S3_ENDPOINT")
        if not endpoint:
            return _service_result(
                service="minio",
                display_name="MinIO/S3",
                role="Media Storage",
                status="warning",
                now=now,
                latency_ms=0,
            )

        status_code, latency_ms, _ = _http_get_json(_join_url(endpoint, "/minio/health/ready"))
        status = "ok" if status_code == 200 else "down"
        return _service_result(
            service="minio",
            display_name="MinIO/S3",
            role="Media Storage",
            status=status,
            now=now,
            latency_ms=latency_ms,
        )

    return _cached_health("minio", check)


def trino_health(now: datetime) -> dict[str, Any]:
    def check() -> dict[str, Any]:
        base_url = os.getenv("TRINO_URL", "http://localhost:8083")
        status_code, latency_ms, _ = _http_get_json(_join_url(base_url, "/v1/info"))
        status = "ok" if status_code == 200 else "down"

        return _service_result(
            service="trino",
            display_name="Trino",
            role="Analytics Query",
            status=status,
            now=now,
            latency_ms=latency_ms,
        )

    return _cached_health("trino", check)


def pipeline_health(now: datetime, redis_latency_ms: int, frame_status: str) -> list[dict[str, Any]]:
    return [
        redis_health(now, redis_latency_ms),
        fastapi_health(now, frame_status),
        flink_health(now),
        pulsar_health(now),
        minio_health(now),
        trino_health(now),
    ]
