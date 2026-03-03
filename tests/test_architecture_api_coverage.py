import json
import uuid
from datetime import datetime, timedelta

import aiosqlite
import config

from database import queries
import ui.app as app_module


async def _register_user(client, email: str):
    res = await client.post("/auth/register", json={"email": email, "password": "password"})
    assert res.status_code == 200
    return res.json()


async def _make_user(client):
    email = f"user-{uuid.uuid4()}@example.com"
    tokens = await _register_user(client, email)
    return email, tokens


def _install_fake_workers(monkeypatch):
    async def fake_run_test_session(*, db, session_row, user_tier, emit):
        await emit({
            "type": "step",
            "data": {
                "step": 1,
                "action": "click",
                "screenshot_id": 1,
                "url": session_row["start_url"],
            },
        })
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
            "run_config": json.loads(session_row["config_json"]),
        }

    async def fake_run_postmortem(*, db, state, emit):
        await queries.save_postmortem(
            db,
            session_id=state["session_id"],
            run_analysis="ok",
            html_analysis="ok",
            recommendations=json.dumps({"ok": True}),
        )
        await emit({"type": "postmortem", "data": {"run_analysis": "ok"}})

    monkeypatch.setattr(app_module, "run_test_session", fake_run_test_session)
    monkeypatch.setattr(app_module, "run_postmortem", fake_run_postmortem)


async def _create_session(client, token, *, model="gpt-4o-mini", config_overrides=None):
    payload = {
        "goal": "test flow",
        "start_url": "https://example.com",
        "provider": "openai",
        "model": model,
        "config": {
            "mode": "desktop",
            "max_steps": 5,
            "stop_on_first_error": False,
            **(config_overrides or {}),
        },
    }
    res = await client.post("/sessions", json=payload, headers={"Authorization": f"Bearer {token}"})
    return res


async def _await_session_task(session_id: str):
    task = app_module.SESSION_TASKS.get(session_id)
    if task:
        await task


async def test_auth_refresh_logout_and_expired_refresh(client):
    _, tokens = await _make_user(client)

    refreshed = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200

    logged_out = await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logged_out.status_code == 200

    revoked = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert revoked.status_code == 401

    _, tokens2 = await _make_user(client)
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE refresh_tokens SET expires_at = ? WHERE token = ?",
            ((datetime.utcnow() - timedelta(days=1)).isoformat(), tokens2["refresh_token"]),
        )
        await db.commit()

    expired = await client.post("/auth/refresh", json={"refresh_token": tokens2["refresh_token"]})
    assert expired.status_code == 401


async def test_admin_can_change_tier_and_models_reflect_tier(client, admin_token):
    _, user_tokens = await _make_user(client)

    me_before = await client.get("/me", headers={"Authorization": f"Bearer {user_tokens['access_token']}"})
    assert me_before.status_code == 200
    user_id = me_before.json()["id"]
    assert me_before.json()["tier"] == "free"

    patched = await client.patch(
        f"/admin/users/{user_id}/tier",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"tier": "pro"},
    )
    assert patched.status_code == 200

    me_after = await client.get("/me", headers={"Authorization": f"Bearer {user_tokens['access_token']}"})
    assert me_after.status_code == 200
    assert me_after.json()["tier"] == "pro"

    models = await client.get("/models", headers={"Authorization": f"Bearer {user_tokens['access_token']}"})
    assert models.status_code == 200
    assert "gpt-4.1" in models.json()["openai"]


async def test_session_creation_enforces_tier_gating_and_model_rules(client, admin_token, monkeypatch):
    _install_fake_workers(monkeypatch)

    _, user_tokens = await _make_user(client)
    token = user_tokens["access_token"]

    disallowed_model = await _create_session(client, token, model="gpt-4o")
    assert disallowed_model.status_code == 400

    disallowed_config = await _create_session(client, token, config_overrides={"loop_detection_window": 12})
    assert disallowed_config.status_code == 400

    allowed = await _create_session(client, token)
    assert allowed.status_code == 200
    await _await_session_task(allowed.json()["session_id"])

    me = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["id"]
    up_basic = await client.patch(
        f"/admin/users/{user_id}/tier",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"tier": "basic"},
    )
    assert up_basic.status_code == 200

    basic_allowed = await _create_session(
        client,
        token,
        model="gpt-4o",
        config_overrides={"max_history_actions": 8, "loop_detection_enabled": True, "loop_detection_window": 10},
    )
    assert basic_allowed.status_code == 200
    await _await_session_task(basic_allowed.json()["session_id"])

    basic_pro_key = await _create_session(client, token, config_overrides={"postmortem_depth": "deep"})
    assert basic_pro_key.status_code == 400


async def test_session_and_artifact_access_control(client, admin_token, monkeypatch):
    _install_fake_workers(monkeypatch)

    _, user_a = await _make_user(client)
    _, user_b = await _make_user(client)
    token_a = user_a["access_token"]
    token_b = user_b["access_token"]

    created = await _create_session(client, token_a)
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    await _await_session_task(session_id)

    forbidden_detail = await client.get(f"/sessions/{session_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert forbidden_detail.status_code == 403

    forbidden_stop = await client.post(f"/sessions/{session_id}/stop", headers={"Authorization": f"Bearer {token_b}"})
    assert forbidden_stop.status_code == 403

    forbidden_pm = await client.get(f"/sessions/{session_id}/postmortem", headers={"Authorization": f"Bearer {token_b}"})
    assert forbidden_pm.status_code == 403

    admin_detail = await client.get(f"/sessions/{session_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_detail.status_code == 200
    assert "logs" in admin_detail.json()
    assert isinstance(admin_detail.json()["logs"], list)

    owner_logs = await client.get(f"/sessions/{session_id}/logs", headers={"Authorization": f"Bearer {token_a}"})
    assert owner_logs.status_code == 200
    assert isinstance(owner_logs.json(), list)

    forbidden_logs = await client.get(f"/sessions/{session_id}/logs", headers={"Authorization": f"Bearer {token_b}"})
    assert forbidden_logs.status_code == 403

    # insert screenshot for artifact checks
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        shot_id = await queries.insert_screenshot(
            db,
            session_id=session_id,
            url="https://example.com",
            image_data=b"png-bytes",
            action_taken="click",
            step_number=2,
        )

    owner_header = await client.get(f"/screenshots/{shot_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert owner_header.status_code == 200

    owner_query = await client.get(f"/screenshots/{shot_id}?token={token_a}")
    assert owner_query.status_code == 200

    forbidden_shot = await client.get(f"/screenshots/{shot_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert forbidden_shot.status_code == 403

    unauth_shot = await client.get(f"/screenshots/{shot_id}")
    assert unauth_shot.status_code == 401


async def test_admin_list_endpoints_and_user_session_scoping(client, admin_token, monkeypatch):
    _install_fake_workers(monkeypatch)

    _, user_a = await _make_user(client)
    _, user_b = await _make_user(client)
    token_a = user_a["access_token"]
    token_b = user_b["access_token"]

    created = await _create_session(client, token_a)
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    await _await_session_task(session_id)

    user_a_sessions = await client.get("/sessions", headers={"Authorization": f"Bearer {token_a}"})
    assert user_a_sessions.status_code == 200
    assert any(s["id"] == session_id for s in user_a_sessions.json())

    user_b_sessions = await client.get("/sessions", headers={"Authorization": f"Bearer {token_b}"})
    assert user_b_sessions.status_code == 200
    assert all(s["id"] != session_id for s in user_b_sessions.json())

    admin_users = await client.get("/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_users.status_code == 200
    assert len(admin_users.json()) >= 2

    admin_sessions = await client.get("/admin/sessions", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_sessions.status_code == 200
    assert any(s["id"] == session_id for s in admin_sessions.json())
