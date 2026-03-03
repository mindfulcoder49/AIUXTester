import os
import uuid
import tempfile
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv


@pytest.fixture(scope="session", autouse=True)
def load_env_file():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@pytest.fixture(scope="session")
def e2e_enabled():
    if os.getenv("E2E_RUN", "0") != "1":
        pytest.skip("E2E tests are disabled. Set E2E_RUN=1 to enable real end-to-end runs.")
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required for E2E tests.")
    return True


@pytest.fixture(scope="session")
def admin_credentials(e2e_enabled):
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
    if not email or not password:
        pytest.skip("ADMIN_EMAIL and ADMIN_PASSWORD are required for E2E tests.")
    return {"email": email, "password": password}


@pytest.fixture
async def e2e_client(e2e_enabled, monkeypatch):
    # Keep E2E DB isolated from regular test/dev data.
    with tempfile.TemporaryDirectory() as tmp:
        import config

        db_path = Path(tmp) / "e2e.db"
        monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))

        from ui.app import app

        await app.router.startup()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
        await app.router.shutdown()
