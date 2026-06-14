"""Minimal dependency-free Trino client for Gold serving runners.

Reuses the HTTP /v1/statement polling pattern from the API
(services/api/src/rva_api/api/v1/analytics_queries.py:49) — stdlib urllib only,
follows nextUri pagination, raises on query error. Handles DDL/DELETE/INSERT
(which return no data) as well as SELECTs.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, NamedTuple
from urllib.request import Request, urlopen


class TrinoResult(NamedTuple):
    columns: list[str]
    rows: list[list[Any]]


def _url() -> str:
    return os.getenv("TRINO_URL", "http://localhost:8083").rstrip("/")


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "text/plain",
        "X-Trino-User": os.getenv("TRINO_USER", "rva_gold_serving"),
        "X-Trino-Catalog": os.getenv("TRINO_CATALOG", "lakehouse"),
        "X-Trino-Schema": os.getenv("TRINO_SCHEMA", "rva_gold_serving"),
    }


def _get(url: str, request: Request | None = None, timeout: float = 30.0) -> dict[str, Any]:
    with urlopen(request or url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run(sql: str, max_wait: float = 300.0) -> TrinoResult:
    """Execute a single SQL statement, draining all pages. Raises RuntimeError on error."""
    started = time.monotonic()
    request = Request(f"{_url()}/v1/statement", data=sql.encode("utf-8"), headers=_headers(), method="POST")
    payload = _get("", request)

    columns: list[str] = []
    rows: list[list[Any]] = []
    while True:
        if payload.get("error"):
            msg = payload["error"].get("message", "Trino query failed")
            raise RuntimeError(f"{msg} :: {sql[:120].strip()}")
        if not columns and payload.get("columns"):
            columns = [c["name"] for c in payload["columns"]]
        rows.extend(payload.get("data") or [])
        next_uri = payload.get("nextUri")
        if not next_uri:
            return TrinoResult(columns, rows)
        if time.monotonic() - started > max_wait:
            try:
                urlopen(Request(next_uri, method="DELETE"), timeout=2).close()
            except Exception:
                pass
            raise RuntimeError(f"Trino statement exceeded {max_wait:.0f}s :: {sql[:120].strip()}")
        payload = _get(next_uri)


def _strip_sql_comments(sql_text: str) -> str:
    # Drop `--` line comments (no `--` appears inside our string literals).
    return "\n".join(line.split("--", 1)[0] for line in sql_text.splitlines())


def run_script(sql_text: str, max_wait: float = 300.0) -> int:
    """Run a multi-statement SQL string (split on ';'). Returns the count run."""
    cleaned = _strip_sql_comments(sql_text)
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    for stmt in statements:
        run(stmt, max_wait=max_wait)
    return len(statements)


def scalar(sql: str, max_wait: float = 120.0) -> Any:
    """Return the first cell of the first row, or None."""
    result = run(sql, max_wait=max_wait)
    if result.rows and result.rows[0]:
        return result.rows[0][0]
    return None
