import json
from datetime import datetime
from typing import Any, Dict, Optional

import config


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def _is_mariadb() -> bool:
    return config.DB_BACKEND == "mariadb"


def _adapt_sql(sql: str) -> str:
    if not _is_mariadb():
        return sql
    return sql.replace("?", "%s")


async def _run(db, sql: str, params=(), fetch: Optional[str] = None):
    sql = _adapt_sql(sql)
    if _is_mariadb():
        import aiomysql

        async with db.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, params)
            if fetch == "one":
                return await cur.fetchone()
            if fetch == "all":
                return await cur.fetchall()
            return cur.lastrowid
    else:
        cur = await db.execute(sql, params)
        if fetch == "one":
            return await cur.fetchone()
        if fetch == "all":
            return await cur.fetchall()
        return cur.lastrowid


async def _commit(db):
    await db.commit()


# Users
async def create_user(
    db,
    *,
    user_id: str,
    email: str,
    password_hash: str,
    role: str = "user",
    tier: str = "free",
) -> None:
    ts = now_iso()
    await _run(
        db,
        "INSERT INTO users (id, email, password_hash, role, tier, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, email, password_hash, role, tier, ts, ts),
    )
    await _commit(db)


async def get_user_by_email(db, email: str):
    return await _run(db, "SELECT * FROM users WHERE email = ?", (email,), fetch="one")


async def get_user_by_id(db, user_id: str):
    return await _run(db, "SELECT * FROM users WHERE id = ?", (user_id,), fetch="one")


async def list_users(db):
    return await _run(db, "SELECT * FROM users ORDER BY created_at DESC", fetch="all")


async def update_user_tier(db, user_id: str, tier: str) -> None:
    ts = now_iso()
    await _run(db, "UPDATE users SET tier = ?, updated_at = ? WHERE id = ?", (tier, ts, user_id))
    await _commit(db)


# Refresh tokens
async def create_refresh_token(db, *, user_id: str, token: str, expires_at: str) -> None:
    ts = now_iso()
    await _run(
        db,
        "INSERT INTO refresh_tokens (user_id, token, expires_at, revoked, created_at) VALUES (?, ?, ?, 0, ?)",
        (user_id, token, expires_at, ts),
    )
    await _commit(db)


async def revoke_refresh_token(db, token: str) -> None:
    await _run(db, "UPDATE refresh_tokens SET revoked = 1 WHERE token = ?", (token,))
    await _commit(db)


async def get_refresh_token(db, token: str):
    return await _run(db, "SELECT * FROM refresh_tokens WHERE token = ?", (token,), fetch="one")


# Sessions
async def create_session(
    db,
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
    await _run(
        db,
        """
        INSERT INTO sessions (id, user_id, goal, start_url, mode, status, end_reason,
                              provider, model, config_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'running', NULL, ?, ?, ?, ?, ?)
        """,
        (session_id, user_id, goal, start_url, mode, provider, model, json.dumps(config), ts, ts),
    )
    await _commit(db)


async def update_session_status(db, session_id: str, status: str, end_reason: Optional[str]) -> None:
    ts = now_iso()
    await _run(
        db,
        "UPDATE sessions SET status = ?, end_reason = ?, updated_at = ? WHERE id = ?",
        (status, end_reason, ts, session_id),
    )
    await _commit(db)


async def list_sessions_for_user(db, user_id: str):
    return await _run(db, "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC", (user_id,), fetch="all")


async def list_sessions_all(db):
    return await _run(db, "SELECT * FROM sessions ORDER BY created_at DESC", fetch="all")


async def get_session(db, session_id: str):
    return await _run(db, "SELECT * FROM sessions WHERE id = ?", (session_id,), fetch="one")


# Screenshots
async def insert_screenshot(db, *, session_id: str, url: str, image_data: bytes, action_taken: str, step_number: int):
    ts = now_iso()
    row_id = await _run(
        db,
        "INSERT INTO screenshots (session_id, url, image_data, action_taken, step_number, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, url, image_data, action_taken, step_number, ts),
    )
    await _commit(db)
    return row_id


async def get_screenshot(db, screenshot_id: int):
    return await _run(db, "SELECT * FROM screenshots WHERE id = ?", (screenshot_id,), fetch="one")


async def list_screenshots(db, session_id: str):
    return await _run(
        db,
        "SELECT * FROM screenshots WHERE session_id = ? ORDER BY step_number ASC, id ASC",
        (session_id,),
        fetch="all",
    )


# HTML captures
async def insert_html_capture(db, *, session_id: str, url: str, html: str, step_number: int):
    ts = now_iso()
    row_id = await _run(
        db,
        "INSERT INTO html_captures (session_id, url, html, step_number, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, url, html, step_number, ts),
    )
    await _commit(db)
    return row_id


async def list_html_captures(db, session_id: str):
    return await _run(db, "SELECT * FROM html_captures WHERE session_id = ? ORDER BY step_number ASC", (session_id,), fetch="all")


# Actions
async def insert_action(
    db,
    *,
    session_id: str,
    step_number: int,
    action_type: str,
    action_params: Dict[str, Any],
    intent: Optional[str],
    reasoning: str,
    action_result: Optional[str],
    screenshot_id: Optional[int],
    success: bool,
    error_message: Optional[str],
) -> None:
    ts = now_iso()
    await _run(
        db,
        """
        INSERT INTO actions (session_id, step_number, action_type, action_params, intent, reasoning,
                             action_result, screenshot_id, success, error_message, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            step_number,
            action_type,
            json.dumps(action_params),
            intent,
            reasoning,
            action_result,
            screenshot_id,
            int(success),
            error_message,
            ts,
        ),
    )
    await _commit(db)


async def list_actions(db, session_id: str):
    return await _run(db, "SELECT * FROM actions WHERE session_id = ? ORDER BY step_number ASC", (session_id,), fetch="all")


# Memory
async def upsert_memory(db, *, session_id: str, key: str, value: str) -> None:
    ts = now_iso()
    if _is_mariadb():
        sql = """
        INSERT INTO agent_memory (session_id, `key`, `value`, updated_at)
        VALUES (?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), updated_at = VALUES(updated_at)
        """
    else:
        sql = """
        INSERT INTO agent_memory (session_id, key, value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """
    await _run(db, sql, (session_id, key, value, ts))
    await _commit(db)


async def get_memory(db, session_id: str):
    if _is_mariadb():
        sql = "SELECT `key`, `value` FROM agent_memory WHERE session_id = ?"
    else:
        sql = "SELECT key, value FROM agent_memory WHERE session_id = ?"
    rows = await _run(db, sql, (session_id,), fetch="all")
    return {row["key"]: row["value"] for row in rows}


# Postmortem
async def save_postmortem(db, *, session_id: str, run_analysis: str, html_analysis: str, recommendations: str) -> None:
    ts = now_iso()
    await _run(
        db,
        """
        INSERT INTO postmortem_reports (session_id, run_analysis, html_analysis, recommendations, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, run_analysis, html_analysis, recommendations, ts),
    )
    await _commit(db)


async def get_postmortem(db, session_id: str):
    return await _run(db, "SELECT * FROM postmortem_reports WHERE session_id = ?", (session_id,), fetch="one")


# Run logs
async def insert_run_log(
    db,
    *,
    session_id: str,
    level: str,
    message: str,
    details: Optional[str] = None,
    step_number: Optional[int] = None,
) -> None:
    ts = now_iso()
    await _run(
        db,
        """
        INSERT INTO run_logs (session_id, step_number, level, message, details, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, step_number, level, message, details, ts),
    )
    await _commit(db)


async def list_run_logs(db, session_id: str):
    return await _run(
        db,
        "SELECT * FROM run_logs WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
        fetch="all",
    )
