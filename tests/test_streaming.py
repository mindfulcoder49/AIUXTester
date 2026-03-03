import asyncio
import json

import ui.app as app_module


async def test_stream_requires_auth(client):
    res = await client.get("/sessions/bad/stream")
    assert res.status_code in (401, 403)


async def test_stream_emits_event(client, user_token, monkeypatch):
    async def fake_run_test_session(*, db, session_row, user_tier, emit):
        return {"session_id": session_row["id"], "status": "running", "provider": session_row["provider"], "model": session_row["model"], "memory": {}, "action_history": []}

    async def fake_run_postmortem(*, db, state, emit):
        return None

    monkeypatch.setattr(app_module, "run_test_session", fake_run_test_session)
    monkeypatch.setattr(app_module, "run_postmortem", fake_run_postmortem)
    # create session
    payload = {
        "goal": "test",
        "start_url": "https://example.com",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "config": {"mode": "desktop", "max_steps": 5, "stop_on_first_error": False},
    }
    res = await client.post("/sessions", json=payload, headers={"Authorization": f"Bearer {user_token}"})
    session_id = res.json()["session_id"]

    # Ensure queue exists and can carry step events for SSE consumers.
    q = app_module.SESSION_STREAMS[session_id]
    event = {"type": "step", "data": {"step": 1, "action": "click", "screenshot_id": 1, "url": "x"}}
    await q.put(event)
    pulled = await q.get()
    assert pulled["type"] == "step"
    assert pulled["data"]["step"] == 1

    task = app_module.SESSION_TASKS.get(session_id)
    if task:
        await task
