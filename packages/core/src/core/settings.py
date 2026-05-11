"""Shared settings loader for YAML + env var configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


def _get_env(key: str) -> str | None:
    return os.getenv(key.upper())


def get_str(
    key: str,
    defaults: dict[str, Any],
    *,
    env_key: str | None = None,
) -> str:
    env_val = _get_env(env_key or key)
    if env_val is not None and env_val != "":
        return env_val
    return str(defaults.get(key, ""))


def get_optional(
    key: str,
    defaults: dict[str, Any],
    *,
    env_key: str | None = None,
) -> Any:
    env_val = _get_env(env_key or key)
    if env_val is not None and env_val != "":
        return env_val
    return defaults.get(key)


def get_bool(key: str, defaults: dict[str, Any], default: bool = False) -> bool:
    raw = get_optional(key, defaults)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_int(key: str, defaults: dict[str, Any], default: int) -> int:
    raw = get_optional(key, defaults)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_float(key: str, defaults: dict[str, Any], default: float) -> float:
    raw = get_optional(key, defaults)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def get_class_filter(defaults: dict[str, Any]) -> list[int]:
    env_str = os.getenv("CLASS_FILTER")
    if env_str:
        try:
            return json.loads(env_str)
        except Exception:
            pass
    return defaults.get("class_filter", [0])


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file. Returns empty dict if file not found."""
    yaml_path = Path(path)
    if not yaml_path.exists():
        return {}
    with open(yaml_path) as f:
        return yaml.safe_load(f) or {}
