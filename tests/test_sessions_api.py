import asyncio
import json
from types import SimpleNamespace

import aiosqlite
import config
from database import queries
import ui.app as app_module


async def test_create_session_and_stop(client, user_token, monkeypatch):
    async def fake_run_test_session(*, db, session_row, user_tier, emit):
        await emit({"type": "step", "data": {"step": 1, "action": "click", "screenshot_id": 1, "url": session_row["start_url"]}})
        await queries.update_session_status(db, session_row["id"], "completed", "done")
        return {
            "session_id": session_row["id"],
            "goal": session_row["goal"],
            "status": "completed",
            "end_reason": "done",
            "memory": {},
            "action_history": [],
            "provider": session_row["provider"],
            "model": session_row["model"],
        }

    async def fake_run_postmortem(*, db, state, emit):
        await queries.save_postmortem(db, session_id=state["session_id"], run_analysis="ok", html_analysis="ok", recommendations=json.dumps({"ok": True}))
        await emit({"type": "postmortem", "data": {"run_analysis": "ok"}})

    monkeypatch.setattr(app_module, "run_test_session", fake_run_test_session)
    monkeypatch.setattr(app_module, "run_postmortem", fake_run_postmortem)

    payload = {
        "goal": "test",
        "start_url": "https://example.com",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "config": {"mode": "desktop", "max_steps": 5, "stop_on_first_error": False},
    }
    res = await client.post("/sessions", json=payload, headers={"Authorization": f"Bearer {user_token}"})
    assert res.status_code == 200
    session_id = res.json()["session_id"]

    # stop should update status
    stop = await client.post(f"/sessions/{session_id}/stop", headers={"Authorization": f"Bearer {user_token}"})
    assert stop.status_code == 200

    detail = await client.get(f"/sessions/{session_id}", headers={"Authorization": f"Bearer {user_token}"})
    assert detail.status_code == 200

    task = app_module.SESSION_TASKS.get(session_id)
    if task:
        await task
