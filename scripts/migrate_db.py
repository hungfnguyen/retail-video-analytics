#!/usr/bin/env python3
"""Run PostgreSQL schema migrations from infra/postgres/init.sql."""

import asyncio
import os
from pathlib import Path

import asyncpg


INIT_SQL = Path(__file__).parent.parent / "infra" / "postgres" / "init.sql"


async def run() -> None:
    dsn = os.getenv("POSTGRES_DSN", "postgresql://rva:rva_secret@localhost:5432/rva_metadata")

    print(f"Connecting to {dsn.split('@')[-1]}...")
    conn = await asyncpg.connect(dsn)

    try:
        sql = INIT_SQL.read_text()
        print(f"Running {INIT_SQL.name}...")
        await conn.execute(sql)
        print("Migration complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
