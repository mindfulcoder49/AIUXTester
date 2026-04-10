from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional
from urllib.parse import urlparse

import aiosqlite

import config

SCHEMA_SQLITE_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_MARIADB_PATH = Path(__file__).with_name("schema_mariadb.sql")

_MARIADB_POOL = None
_POOL_LOCK = asyncio.Lock()


def _is_mariadb() -> bool:
    return config.DB_BACKEND == "mariadb"


def _split_sql_script(script: str) -> list[str]:
    return [stmt.strip() for stmt in script.split(";") if stmt.strip()]


async def _get_mariadb_pool():
    global _MARIADB_POOL
    if _MARIADB_POOL is not None:
        return _MARIADB_POOL

    async with _POOL_LOCK:
        if _MARIADB_POOL is not None:
            return _MARIADB_POOL
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is required when DB_BACKEND=mariadb")
        import aiomysql

        parsed = urlparse(config.DATABASE_URL)
        if parsed.scheme not in {"mysql", "mariadb"}:
            raise RuntimeError("DATABASE_URL must use mysql:// or mariadb://")
        _MARIADB_POOL = await aiomysql.create_pool(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=parsed.username or "",
            password=parsed.password or "",
            db=(parsed.path or "/").lstrip("/") or "",
            minsize=1,
            maxsize=10,
            # Keep reads fresh across pooled connections and avoid stale tx snapshots.
            autocommit=True,
            charset="utf8mb4",
        )
        return _MARIADB_POOL


async def close_db() -> None:
    global _MARIADB_POOL
    if _MARIADB_POOL is not None:
        _MARIADB_POOL.close()
        await _MARIADB_POOL.wait_closed()
        _MARIADB_POOL = None


async def _sqlite_migrations(db: aiosqlite.Connection) -> None:
    cols = {row[1] for row in await (await db.execute("PRAGMA table_info(actions)")).fetchall()}
    if "intent" not in cols:
        await db.execute("ALTER TABLE actions ADD COLUMN intent TEXT")
    if "action_result" not in cols:
        await db.execute("ALTER TABLE actions ADD COLUMN action_result TEXT")
    comp_run_cols = {row[1] for row in await (await db.execute("PRAGMA table_info(competition_runs)")).fetchall()}
    if "progression_mode" not in comp_run_cols:
        await db.execute("ALTER TABLE competition_runs ADD COLUMN progression_mode TEXT NOT NULL DEFAULT 'automatic'")
    comp_match_cols = {row[1] for row in await (await db.execute("PRAGMA table_info(competition_matches)")).fetchall()}
    if "run_id" not in comp_match_cols:
        await db.execute("ALTER TABLE competition_matches ADD COLUMN run_id INTEGER")


async def _mariadb_migrations(conn) -> None:
    import aiomysql

    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'actions'
            """
        )
        cols = {row["COLUMN_NAME"] for row in await cur.fetchall()}
        if "intent" not in cols:
            await cur.execute("ALTER TABLE actions ADD COLUMN intent TEXT NULL")
        if "action_result" not in cols:
            await cur.execute("ALTER TABLE actions ADD COLUMN action_result TEXT NULL")
        await cur.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'competition_runs'
            """
        )
        comp_run_cols = {row["COLUMN_NAME"] for row in await cur.fetchall()}
        if "progression_mode" not in comp_run_cols:
            await cur.execute(
                "ALTER TABLE competition_runs ADD COLUMN progression_mode VARCHAR(32) NOT NULL DEFAULT 'automatic'"
            )
        await cur.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'competition_matches'
            """
        )
        comp_match_cols = {row["COLUMN_NAME"] for row in await cur.fetchall()}
        if "run_id" not in comp_match_cols:
            await cur.execute("ALTER TABLE competition_matches ADD COLUMN run_id BIGINT NULL")


async def init_db() -> None:
    if _is_mariadb():
        pool = await _get_mariadb_pool()
        async with pool.acquire() as conn:
            import aiomysql

            schema_sql = SCHEMA_MARIADB_PATH.read_text()
            async with conn.cursor(aiomysql.DictCursor) as cur:
                for stmt in _split_sql_script(schema_sql):
                    await cur.execute(stmt)
            await _mariadb_migrations(conn)
            await conn.commit()
        return

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=10000")
        schema_sql = SCHEMA_SQLITE_PATH.read_text()
        await db.executescript(schema_sql)
        await _sqlite_migrations(db)
        await db.commit()


@asynccontextmanager
async def open_db():
    if _is_mariadb():
        pool = await _get_mariadb_pool()
        conn = await pool.acquire()
        try:
            yield conn
        finally:
            pool.release(conn)
    else:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=10000")
            yield db


async def get_db() -> AsyncIterator:
    async with open_db() as db:
        yield db
