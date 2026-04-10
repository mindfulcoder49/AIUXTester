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


async def update_user_password(db, user_id: str, password_hash: str) -> None:
    ts = now_iso()
    await _run(db, "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?", (password_hash, ts, user_id))
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


async def list_sessions_admin(db, *, status: Optional[str] = None, limit: int = 50):
    """Sessions enriched with user email and action count, for the admin panel."""
    where_parts = []
    params: list = []
    if status:
        where_parts.append("s.status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    sql = f"""
        SELECT s.*,
               u.email,
               (SELECT COUNT(*) FROM actions a WHERE a.session_id = s.id) AS action_count
        FROM sessions s
        LEFT JOIN users u ON s.user_id = u.id
        {where}
        ORDER BY s.created_at DESC
        LIMIT ?
    """
    params.append(limit)
    return await _run(db, sql, tuple(params), fetch="all")


async def get_session(db, session_id: str):
    return await _run(db, "SELECT * FROM sessions WHERE id = ?", (session_id,), fetch="one")


async def list_running_sessions(db):
    return await _run(
        db,
        "SELECT * FROM sessions WHERE status = 'running' ORDER BY created_at ASC",
        fetch="all",
    )


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


async def get_last_run_log(db, session_id: str):
    return await _run(
        db,
        "SELECT * FROM run_logs WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
        fetch="one",
    )


# Competitions
async def create_competition(db, *, competition_id: str, name: str, description: Optional[str], created_by: str) -> None:
    ts = now_iso()
    await _run(
        db,
        "INSERT INTO competitions (id, name, description, status, created_by, created_at, updated_at) VALUES (?, ?, ?, 'open', ?, ?, ?)",
        (competition_id, name, description, created_by, ts, ts),
    )
    await _commit(db)


async def get_competition(db, competition_id: str):
    return await _run(db, "SELECT * FROM competitions WHERE id = ?", (competition_id,), fetch="one")


async def list_competitions(db):
    return await _run(db, "SELECT * FROM competitions ORDER BY created_at DESC", fetch="all")


async def update_competition_status(db, competition_id: str, status: str) -> None:
    ts = now_iso()
    await _run(db, "UPDATE competitions SET status = ?, updated_at = ? WHERE id = ?", (status, ts, competition_id))
    await _commit(db)


async def update_competition(db, competition_id: str, *, name: Optional[str] = None, description: Optional[str] = None) -> None:
    ts = now_iso()
    if name is not None:
        await _run(db, "UPDATE competitions SET name = ?, updated_at = ? WHERE id = ?", (name, ts, competition_id))
    if description is not None:
        await _run(db, "UPDATE competitions SET description = ?, updated_at = ? WHERE id = ?", (description, ts, competition_id))
    await _commit(db)


# Competition entries
async def add_competition_entry(db, *, competition_id: str, session_id: str, user_id: str, note: Optional[str]) -> int:
    ts = now_iso()
    row_id = await _run(
        db,
        "INSERT INTO competition_entries (competition_id, session_id, user_id, note, submitted_at) VALUES (?, ?, ?, ?, ?)",
        (competition_id, session_id, user_id, note, ts),
    )
    await _commit(db)
    return row_id


async def get_competition_entry(db, entry_id: int):
    return await _run(db, "SELECT * FROM competition_entries WHERE id = ?", (entry_id,), fetch="one")


async def get_entry_for_user(db, competition_id: str, user_id: str):
    return await _run(
        db,
        "SELECT * FROM competition_entries WHERE competition_id = ? AND user_id = ?",
        (competition_id, user_id),
        fetch="one",
    )


async def list_competition_entries(db, competition_id: str):
    return await _run(
        db,
        "SELECT * FROM competition_entries WHERE competition_id = ? ORDER BY submitted_at ASC",
        (competition_id,),
        fetch="all",
    )


# Competition runs
async def create_competition_run(
    db,
    *,
    competition_id: str,
    run_number: int,
    pairing_strategy: str,
    progression_mode: str,
    pairing_seed: Optional[int],
    provider: Optional[str],
    model: Optional[str],
    created_by: str,
    status: str = "queued",
) -> int:
    ts = now_iso()
    row_id = await _run(
        db,
        """
        INSERT INTO competition_runs (
            competition_id, run_number, pairing_strategy, progression_mode, pairing_seed,
            provider, model, champion_entry_id, status, created_by,
            created_at, updated_at, completed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL)
        """,
        (
            competition_id,
            run_number,
            pairing_strategy,
            progression_mode,
            pairing_seed,
            provider,
            model,
            status,
            created_by,
            ts,
            ts,
        ),
    )
    await _commit(db)
    return row_id


async def get_competition_run(db, run_id: int):
    return await _run(db, "SELECT * FROM competition_runs WHERE id = ?", (run_id,), fetch="one")


async def get_first_competition_run(db, competition_id: str):
    return await _run(
        db,
        "SELECT * FROM competition_runs WHERE competition_id = ? ORDER BY run_number ASC LIMIT 1",
        (competition_id,),
        fetch="one",
    )


async def get_latest_competition_run(db, competition_id: str):
    return await _run(
        db,
        "SELECT * FROM competition_runs WHERE competition_id = ? ORDER BY run_number DESC LIMIT 1",
        (competition_id,),
        fetch="one",
    )


async def list_competition_runs(db, competition_id: str):
    return await _run(
        db,
        "SELECT * FROM competition_runs WHERE competition_id = ? ORDER BY run_number DESC",
        (competition_id,),
        fetch="all",
    )


async def get_next_queued_competition_run(db, competition_id: str, *, progression_mode: Optional[str] = None):
    query = "SELECT * FROM competition_runs WHERE competition_id = ? AND status = 'queued'"
    params: list = [competition_id]
    if progression_mode:
        query += " AND progression_mode = ?"
        params.append(progression_mode)
    query += " ORDER BY run_number ASC LIMIT 1"
    return await _run(db, query, tuple(params), fetch="one")


async def get_next_competition_run_number(db, competition_id: str) -> int:
    row = await _run(
        db,
        "SELECT COALESCE(MAX(run_number), 0) AS max_run_number FROM competition_runs WHERE competition_id = ?",
        (competition_id,),
        fetch="one",
    )
    max_run_number = row["max_run_number"] if row and row["max_run_number"] is not None else 0
    return int(max_run_number) + 1


async def update_competition_run_status(db, run_id: int, status: str) -> None:
    ts = now_iso()
    completed_at = ts if status in {"complete", "failed"} else None
    await _run(
        db,
        "UPDATE competition_runs SET status = ?, updated_at = ?, completed_at = ? WHERE id = ?",
        (status, ts, completed_at, run_id),
    )
    await _commit(db)


async def complete_competition_run(db, run_id: int, champion_entry_id: Optional[int]) -> None:
    ts = now_iso()
    await _run(
        db,
        """
        UPDATE competition_runs
        SET champion_entry_id = ?, status = 'complete', updated_at = ?, completed_at = ?
        WHERE id = ?
        """,
        (champion_entry_id, ts, ts, run_id),
    )
    await _commit(db)


async def assign_unscoped_competition_matches_to_run(db, competition_id: str, run_id: int) -> None:
    await _run(
        db,
        "UPDATE competition_matches SET run_id = ? WHERE competition_id = ? AND run_id IS NULL",
        (run_id, competition_id),
    )
    await _commit(db)


async def backfill_legacy_competition_runs(db) -> int:
    competitions = await _run(
        db,
        """
        SELECT c.*
        FROM competitions c
        WHERE EXISTS (
            SELECT 1
            FROM competition_matches m
            WHERE m.competition_id = c.id
        )
        AND (
            NOT EXISTS (
                SELECT 1
                FROM competition_runs r
                WHERE r.competition_id = c.id
            )
            OR EXISTS (
                SELECT 1
                FROM competition_matches m2
                WHERE m2.competition_id = c.id AND m2.run_id IS NULL
            )
        )
        ORDER BY c.created_at ASC
        """,
        fetch="all",
    )

    created_count = 0
    for competition in competitions:
        matches = await list_competition_matches(db, competition["id"])
        if not matches:
            continue

        run = await get_first_competition_run(db, competition["id"])
        if not run:
            created_count += 1
            max_round = max(match["round_number"] for match in matches)
            final_match = sorted(
                [match for match in matches if match["round_number"] == max_round],
                key=lambda item: item["match_number"],
            )[-1]
            champion_entry_id = final_match["winner_entry_id"]
            created_at = min((match["created_at"] for match in matches), default=competition["created_at"])
            updated_at = max((match["updated_at"] for match in matches), default=competition["updated_at"])
            status = "complete" if champion_entry_id else "running"
            run_id = await _run(
                db,
                """
                INSERT INTO competition_runs (
                    competition_id, run_number, pairing_strategy, progression_mode, pairing_seed,
                    provider, model, champion_entry_id, status, created_by,
                    created_at, updated_at, completed_at
                )
                VALUES (?, 1, 'legacy', 'automatic', NULL, NULL, NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    competition["id"],
                    champion_entry_id,
                    status,
                    competition["created_by"],
                    created_at,
                    updated_at,
                    updated_at if status == "complete" else None,
                ),
            )
            await _commit(db)
        else:
            run_id = run["id"]

        await assign_unscoped_competition_matches_to_run(db, competition["id"], run_id)

    return created_count


# Competition matches
async def create_competition_match(
    db, *, competition_id: str, run_id: int, round_number: int, match_number: int, entry_ids: list
) -> int:
    ts = now_iso()
    row_id = await _run(
        db,
        """
        INSERT INTO competition_matches (competition_id, run_id, round_number, match_number, entry_ids, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (competition_id, run_id, round_number, match_number, json.dumps(entry_ids), ts, ts),
    )
    await _commit(db)
    return row_id


async def update_competition_match_status(db, match_id: int, status: str) -> None:
    ts = now_iso()
    await _run(
        db,
        "UPDATE competition_matches SET status = ?, updated_at = ? WHERE id = ?",
        (status, ts, match_id),
    )
    await _commit(db)


async def update_competition_match(db, match_id: int, *, winner_entry_id: int, reasoning: str) -> None:
    ts = now_iso()
    await _run(
        db,
        "UPDATE competition_matches SET winner_entry_id = ?, judge_reasoning = ?, status = 'complete', updated_at = ? WHERE id = ?",
        (winner_entry_id, reasoning, ts, match_id),
    )
    await _commit(db)


async def list_competition_matches(db, competition_id: str, run_id: Optional[int] = None):
    if run_id is None:
        return await _run(
            db,
            """
            SELECT *
            FROM competition_matches
            WHERE competition_id = ?
            ORDER BY COALESCE(run_id, 0) ASC, round_number ASC, match_number ASC
            """,
            (competition_id,),
            fetch="all",
        )
    return await _run(
        db,
        """
        SELECT *
        FROM competition_matches
        WHERE competition_id = ? AND run_id = ?
        ORDER BY round_number ASC, match_number ASC
        """,
        (competition_id, run_id),
        fetch="all",
    )


async def get_first_screenshot(db, session_id: str):
    return await _run(
        db,
        "SELECT * FROM screenshots WHERE session_id = ? ORDER BY step_number ASC, id ASC LIMIT 1",
        (session_id,),
        fetch="one",
    )


# Competition recaps
async def create_competition_recap(
    db,
    *,
    competition_id: str,
    entry_profiles: str,
    overall_narrative: str,
    provider: str,
    model: str,
) -> int:
    ts = now_iso()
    row_id = await _run(
        db,
        """
        INSERT INTO competition_recaps
            (competition_id, entry_profiles, overall_narrative, provider, model, generated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (competition_id, entry_profiles, overall_narrative, provider, model, ts),
    )
    await _commit(db)
    return row_id


async def get_latest_competition_recap(db, competition_id: str):
    return await _run(
        db,
        "SELECT * FROM competition_recaps WHERE competition_id = ? ORDER BY id DESC LIMIT 1",
        (competition_id,),
        fetch="one",
    )


async def list_competition_recaps(db, competition_id: str):
    return await _run(
        db,
        "SELECT id, competition_id, provider, model, generated_at FROM competition_recaps WHERE competition_id = ? ORDER BY id DESC",
        (competition_id,),
        fetch="all",
    )
