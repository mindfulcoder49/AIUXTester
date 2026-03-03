import asyncio
import os
import uuid

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def _register(client, email: str, password: str = "password"):
    res = await client.post("/auth/register", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


async def _login(client, email: str, password: str):
    res = await client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


async def _wait_for_terminal_status(client, token: str, session_id: str, timeout_s: int = 180):
    start = asyncio.get_event_loop().time()
    while True:
        res = await client.get(f"/sessions/{session_id}", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200, res.text
        data = res.json()
        status = data["session"]["status"]
        if status in {"completed", "failed", "stopped", "loop_detected"}:
            return data
        if asyncio.get_event_loop().time() - start > timeout_s:
            pytest.fail(f"Session did not reach terminal status within {timeout_s}s")
        await asyncio.sleep(2)


async def _wait_for_postmortem(client, token: str, session_id: str, timeout_s: int = 120):
    start = asyncio.get_event_loop().time()
    while True:
        res = await client.get(f"/sessions/{session_id}/postmortem", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200, res.text
        body = res.json()
        if body is not None:
            return body
        if asyncio.get_event_loop().time() - start > timeout_s:
            pytest.fail(f"Postmortem not available within {timeout_s}s")
        await asyncio.sleep(2)


async def test_real_openai_gpt5mini_session(e2e_client, admin_credentials):
    client = e2e_client

    user_email = f"e2e-{uuid.uuid4()}@example.com"
    user_tokens = await _register(client, user_email)
    user_access = user_tokens["access_token"]

    # Promote E2E user to pro so gpt-5-mini is permitted by model gating.
    me = await client.get("/me", headers={"Authorization": f"Bearer {user_access}"})
    assert me.status_code == 200, me.text
    user_id = me.json()["id"]

    admin_tokens = await _login(client, admin_credentials["email"], admin_credentials["password"])
    admin_access = admin_tokens["access_token"]

    promote = await client.patch(
        f"/admin/users/{user_id}/tier",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"tier": "pro"},
    )
    assert promote.status_code == 200, promote.text

    payload = {
        "goal": os.getenv("E2E_TEST_GOAL", "Try to use this website"),
        "start_url": os.getenv("E2E_TEST_START_URL", "https://example.com"),
        "provider": "openai",
        "model": os.getenv("E2E_OPENAI_MODEL", "gpt-5-mini"),
        "config": {
            "mode": os.getenv("E2E_MODE", "desktop"),
            "max_steps": int(os.getenv("E2E_MAX_STEPS", "15")),
            "stop_on_first_error": False,
            "max_history_actions": 10,
            "loop_detection_enabled": True,
            "loop_detection_window": 10,
            "postmortem_depth": "standard",
            "custom_system_prompt_preamble": "",
        },
    }

    created = await client.post("/sessions", json=payload, headers={"Authorization": f"Bearer {user_access}"})
    assert created.status_code == 200, created.text
    session_id = created.json()["session_id"]

    session_detail = await _wait_for_terminal_status(client, user_access, session_id)
    assert session_detail["session"]["status"] in {"completed", "failed", "loop_detected", "stopped"}

    # Validate run artifacts persisted.
    assert len(session_detail["actions"]) >= 1
    assert len(session_detail["screenshots"]) >= 1

    postmortem = await _wait_for_postmortem(client, user_access, session_id)
    assert postmortem is not None
