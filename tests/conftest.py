import os
import uuid
import asyncio
import tempfile
from pathlib import Path

import pytest
import httpx

import config
from database.db import init_db
from database import queries
from auth.security import hash_password
from ui.app import app, SESSION_STREAMS, SESSION_TASKS


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)


@pytest.fixture
async def temp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))
        await init_db()
        yield db_path


@pytest.fixture
async def client(temp_db):
    await app.router.startup()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await app.router.shutdown()


@pytest.fixture
async def user_token(client):
    email = f"user-{uuid.uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "password"})
    res = await client.post("/auth/login", json={"email": email, "password": "password"})
    return res.json()["access_token"]


@pytest.fixture
async def admin_token(temp_db, client):
    async def make_admin():
        import aiosqlite
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            user_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO users (id, email, password_hash, role, tier, created_at, updated_at) VALUES (?, ?, ?, 'admin', 'pro', ?, ?)",
                (user_id, "admin@example.com", hash_password("password"), queries.now_iso(), queries.now_iso()),
            )
            await db.commit()
            return user_id

    user_id = await make_admin()
    res = await client.post("/auth/login", json={"email": "admin@example.com", "password": "password"})
    return res.json()["access_token"]


@pytest.fixture(autouse=True)
def clear_streams():
    SESSION_STREAMS.clear()
    SESSION_TASKS.clear()
    yield
    SESSION_STREAMS.clear()
    SESSION_TASKS.clear()
