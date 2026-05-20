"""Redis client abstraction — for realtime state (live count, heatmap, active tracks)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedisClientConfig:
    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    db: int = 0
    socket_timeout: float = 2.0
    socket_connect_timeout: float = 2.0


def create_redis_client(config: RedisClientConfig) -> Any | None:
    """Create a redis client with health check.

    Returns None when redis-py is not installed or Redis is unreachable —
    the pipeline can run without realtime state when Redis is unavailable.
    """
    try:
        import redis as redis_module
    except ImportError:
        logger.warning("redis-py is not installed; realtime Redis state is disabled")
        return None

    client_kwargs: dict[str, Any] = {
        "host": config.host,
        "port": config.port,
        "db": config.db,
        "socket_timeout": config.socket_timeout,
        "socket_connect_timeout": config.socket_connect_timeout,
        "decode_responses": True,
    }
    if config.password:
        client_kwargs["password"] = config.password

    try:
        client = redis_module.Redis(**client_kwargs)
        client.ping()
        logger.info("Connected to Redis at %s:%s", config.host, config.port)
        return client
    except Exception:
        logger.warning(
            "Cannot connect to Redis at %s:%s; realtime state disabled",
            config.host,
            config.port,
            exc_info=True,
        )
        return None
