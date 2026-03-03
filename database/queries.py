import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from aiosqlite import Connection


def now_iso() -> str:
    return datetime.utcnow().isoformat()

# Users
async def create_user(db: Connection, *, user_id: str, email: str, password_hash: str) -> None:
    ts = now_iso()
    await db.execute(
        "INSERT INTO users (id, email, password_hash, role, tier, created_at, updated_at) VALUES (?, ?, ?, 'user', 'free', ?, ?)",
        (user_id, email, password_hash, ts, ts),
    )
    await db.commit()

async def get_user_by_email(db: Connection, email: str):
    cur = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
    return await cur.fetchone()

async def get_user_by_id(db: Connection, user_id: str):
    cur = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return await cur.fetchone()

async def list_users(db: Connection):
    cur = await db.execute("SELECT * FROM users ORDER BY created_at DESC")
    return await cur.fetchall()

async def update_user_tier(db: Connection, user_id: str, tier: str) -> None:
    ts = now_iso()
    await db.execute("UPDATE users SET tier = ?, updated_at = ? WHERE id = ?", (tier, ts, user_id))
    await db.commit()

# Refresh tokens
async def create_refresh_token(db: Connection, *, user_id: str, token: str, expires_at: str) -> None:
    ts = now_iso()
    await db.execute(
        "INSERT INTO refresh_tokens (user_id, token, expires_at, revoked, created_at) VALUES (?, ?, ?, 0, ?)",
        (user_id, token, expires_at, ts),
    )
    await db.commit()

async def revoke_refresh_token(db: Connection, token: str) -> None:
    await db.execute("UPDATE refresh_tokens SET revoked = 1 WHERE token = ?", (token,))
    await db.commit()

async def get_refresh_token(db: Connection, token: str):
    cur = await db.execute("SELECT * FROM refresh_tokens WHERE token = ?", (token,))
    return await cur.fetchone()

# Sessions
async def create_session(
    db: Connection,
    *,
    session_id: str,
    user_id: str,
    goal: str,
    start_url: str,
    mode: str,
    provider: str,
    model: str,
    config: Dict[str, Any],
) -> None:
    ts = now_iso()
    await db.execute(
        """
        INSERT INTO sessions (id, user_id, goal, start_url, mode, status, end_reason,
                              provider, model, config_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'running', NULL, ?, ?, ?, ?, ?)
        """,
        (session_id, user_id, goal, start_url, mode, provider, model, json.dumps(config), ts, ts),
    )
    await db.commit()

async def update_session_status(db: Connection, session_id: str, status: str, end_reason: Optional[str]) -> None:
    ts = now_iso()
    await db.execute(
        "UPDATE sessions SET status = ?, end_reason = ?, updated_at = ? WHERE id = ?",
        (status, end_reason, ts, session_id),
    )
    await db.commit()

async def list_sessions_for_user(db: Connection, user_id: str):
    cur = await db.execute("SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    return await cur.fetchall()

async def list_sessions_all(db: Connection):
    cur = await db.execute("SELECT * FROM sessions ORDER BY created_at DESC")
    return await cur.fetchall()

async def get_session(db: Connection, session_id: str):
    cur = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    return await cur.fetchone()

# Screenshots
async def insert_screenshot(db: Connection, *, session_id: str, url: str, image_data: bytes, action_taken: str, step_number: int):
    ts = now_iso()
    cur = await db.execute(
        "INSERT INTO screenshots (session_id, url, image_data, action_taken, step_number, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, url, image_data, action_taken, step_number, ts),
    )
    await db.commit()
    return cur.lastrowid

async def get_screenshot(db: Connection, screenshot_id: int):
    cur = await db.execute("SELECT * FROM screenshots WHERE id = ?", (screenshot_id,))
    return await cur.fetchone()

async def list_screenshots(db: Connection, session_id: str):
    cur = await db.execute(
        "SELECT * FROM screenshots WHERE session_id = ? ORDER BY step_number ASC, id ASC",
        (session_id,),
    )
    return await cur.fetchall()

# HTML captures
async def insert_html_capture(db: Connection, *, session_id: str, url: str, html: str, step_number: int):
    ts = now_iso()
    cur = await db.execute(
        "INSERT INTO html_captures (session_id, url, html, step_number, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, url, html, step_number, ts),
    )
    await db.commit()
    return cur.lastrowid

async def list_html_captures(db: Connection, session_id: str):
    cur = await db.execute("SELECT * FROM html_captures WHERE session_id = ? ORDER BY step_number ASC", (session_id,))
    return await cur.fetchall()

# Actions
async def insert_action(
    db: Connection,
    *,
    session_id: str,
    step_number: int,
    action_type: str,
    action_params: Dict[str, Any],
    intent: Optional[str],
    reasoning: str,
    screenshot_id: Optional[int],
    success: bool,
    error_message: Optional[str],
) -> None:
    ts = now_iso()
    await db.execute(
        """
        INSERT INTO actions (session_id, step_number, action_type, action_params, intent, reasoning,
                             screenshot_id, success, error_message, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            step_number,
            action_type,
            json.dumps(action_params),
            intent,
            reasoning,
            screenshot_id,
            int(success),
            error_message,
            ts,
        ),
    )
    await db.commit()

async def list_actions(db: Connection, session_id: str):
    cur = await db.execute("SELECT * FROM actions WHERE session_id = ? ORDER BY step_number ASC", (session_id,))
    return await cur.fetchall()

# Memory
async def upsert_memory(db: Connection, *, session_id: str, key: str, value: str) -> None:
    ts = now_iso()
    await db.execute(
        """
        INSERT INTO agent_memory (session_id, key, value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (session_id, key, value, ts),
    )
    await db.commit()

async def get_memory(db: Connection, session_id: str):
    cur = await db.execute("SELECT key, value FROM agent_memory WHERE session_id = ?", (session_id,))
    rows = await cur.fetchall()
    return {row["key"]: row["value"] for row in rows}

# Postmortem
async def save_postmortem(db: Connection, *, session_id: str, run_analysis: str, html_analysis: str, recommendations: str) -> None:
    ts = now_iso()
    await db.execute(
        """
        INSERT INTO postmortem_reports (session_id, run_analysis, html_analysis, recommendations, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, run_analysis, html_analysis, recommendations, ts),
    )
    await db.commit()

async def get_postmortem(db: Connection, session_id: str):
    cur = await db.execute("SELECT * FROM postmortem_reports WHERE session_id = ?", (session_id,))
    return await cur.fetchone()


# Run logs
async def insert_run_log(
    db: Connection,
    *,
    session_id: str,
    level: str,
    message: str,
    details: Optional[str] = None,
    step_number: Optional[int] = None,
) -> None:
    ts = now_iso()
    await db.execute(
        """
        INSERT INTO run_logs (session_id, step_number, level, message, details, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, step_number, level, message, details, ts),
    )
    await db.commit()


async def list_run_logs(db: Connection, session_id: str):
    cur = await db.execute(
        "SELECT * FROM run_logs WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    )
    return await cur.fetchall()
