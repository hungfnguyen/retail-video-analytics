"""Pulsar producer/consumer wrappers shared across services."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class PulsarProducer:
    """Thin wrapper around pulsar.Producer with retry logic."""

    def __init__(
        self,
        service_url: str,
        topic: str,
        *,
        max_retries: int = 3,
        initial_backoff: float = 0.5,
        listener_name: str = "external",
    ):
        import pulsar

        self.service_url = service_url
        self.topic = topic
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff

        self._client = pulsar.Client(service_url, listener_name=listener_name)
        self._producer = self._client.create_producer(topic)
        logger.info("Connected to Pulsar topic '%s'", topic)

    def send(self, payload: bytes) -> bool:
        for attempt in range(self.max_retries):
            try:
                self._producer.send(payload)
                return True
            except Exception:
                if attempt < self.max_retries - 1:
                    backoff = self.initial_backoff * (2**attempt)
                    logger.warning(
                        "Pulsar send failed (attempt %d/%d), retrying in %.2fs",
                        attempt + 1,
                        self.max_retries,
                        backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.exception("Pulsar send failed after %d attempts", self.max_retries)
                    return False
        return False

    def send_json(self, data: dict[str, Any]) -> bool:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return self.send(payload)

    def close(self) -> None:
        try:
            self._producer.close()
            self._client.close()
        except Exception:
            logger.exception("Error closing Pulsar producer")


class PulsarConsumer:
    """Thin wrapper around pulsar.Consumer for replay/testing."""

    def __init__(
        self,
        service_url: str,
        topic: str,
        subscription: str,
        *,
        listener_name: str = "external",
    ):
        import pulsar

        self._client = pulsar.Client(service_url, listener_name=listener_name)
        self._consumer = self._client.subscribe(
            topic,
            subscription,
            consumer_type=pulsar.ConsumerType.Shared,
        )
        logger.info("Subscribed to '%s' as '%s'", topic, subscription)

    def receive(self, timeout_millis: int = 1000) -> dict[str, Any] | None:
        try:
            msg = self._consumer.receive(timeout_millis=timeout_millis)
            data = json.loads(msg.data().decode("utf-8"))
            self._consumer.acknowledge(msg)
            return data
        except Exception:
            return None

    def close(self) -> None:
        try:
            self._consumer.close()
            self._client.close()
        except Exception:
            logger.exception("Error closing Pulsar consumer")
