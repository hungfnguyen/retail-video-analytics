"""Runtime package version helpers."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def package_version(package_name: str) -> str | None:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None
