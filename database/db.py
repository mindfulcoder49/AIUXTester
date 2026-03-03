import aiosqlite
from pathlib import Path
from typing import AsyncIterator
import config

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

async def init_db() -> None:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        schema_sql = SCHEMA_PATH.read_text()
        await db.executescript(schema_sql)
        cols = {row[1] for row in await (await db.execute("PRAGMA table_info(actions)")).fetchall()}
        if "intent" not in cols:
            await db.execute("ALTER TABLE actions ADD COLUMN intent TEXT")
        await db.commit()

async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db
