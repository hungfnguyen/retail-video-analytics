#!/usr/bin/env python3
"""Idempotently (re)create the rva_gold_serving schema + tables.

Safe to run on every startup or before each refresh: the DDL uses
CREATE ... IF NOT EXISTS, so re-running is a cheap metadata no-op.

This guards against the schema disappearing after a stack / Iceberg REST
catalog restart. The `lakehouse.rva` schema is recreated automatically by the
Flink jobs (CREATE DATABASE/TABLE IF NOT EXISTS on startup), but
`lakehouse.rva_gold_serving` is only created by this DDL — so without a bootstrap
step the analyst API fails with SCHEMA_NOT_FOUND after a restart.
"""

from __future__ import annotations

import os

import trino_client as trino

DDL_PATH = os.path.join(os.path.dirname(__file__), "sql", "ddl", "gold_serving.sql")


def ensure_schema() -> int:
    """Apply the Gold serving DDL idempotently. Returns the table count."""
    with open(DDL_PATH) as fh:
        trino.run_script(fh.read())
    rows = trino.run("SHOW TABLES FROM lakehouse.rva_gold_serving").rows
    return len(rows)


def main() -> None:
    count = ensure_schema()
    print(f"gold_serving DDL ensured: {count} tables in lakehouse.rva_gold_serving")


if __name__ == "__main__":
    main()
