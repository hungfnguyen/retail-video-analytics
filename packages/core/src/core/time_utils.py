"""Shared time utilities."""

from __future__ import annotations

from datetime import datetime, timezone


def ensure_utc(ts: datetime) -> datetime:
    """Convert a datetime to UTC. Naive datetimes are treated as UTC."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
