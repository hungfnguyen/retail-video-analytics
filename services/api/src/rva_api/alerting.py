from __future__ import annotations

BUSINESS_ALERT_TYPES = frozenset({
    "density_high",
    "queue_overcrowded",
    "long_wait",
})


def is_business_alert_type(alert_type: str | bytes | None) -> bool:
    if isinstance(alert_type, bytes):
        normalized = alert_type.decode("utf-8", errors="ignore")
    else:
        normalized = str(alert_type or "")
    return normalized.strip().lower() in BUSINESS_ALERT_TYPES
