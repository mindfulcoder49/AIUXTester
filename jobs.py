import asyncio
import json
import logging

from agent.postmortem_graph import run_postmortem
from agent.test_graph import run_test_session
from database import queries
from database.db import open_db
from queueing import get_async_redis, publish_event_async


logger = logging.getLogger("aiuxtester.worker")


def run_session_job(session_id: str) -> None:
    asyncio.run(_run_session_job(session_id))


async def _run_session_job(session_id: str) -> None:
    redis_conn = get_async_redis()
    try:
        async with open_db() as conn:
            final_state = None

            async def emit(event: dict):
                await publish_event_async(redis_conn, session_id, event)

            try:
                logger.info("Worker started for session %s", session_id)
                session_row = await queries.get_session(conn, session_id)
                if not session_row:
                    await emit({"type": "error", "data": {"message": "Session not found"}})
                    return
                user = await queries.get_user_by_id(conn, session_row["user_id"])
                user_tier = user["tier"] if user else "free"
                final_state = await run_test_session(
                    db=conn,
                    session_row=session_row,
                    user_tier=user_tier,
                    emit=lambda e: asyncio.create_task(emit(e)),
                )
            except Exception as exc:
                message = str(exc)
                logger.exception("Worker failed for session %s: %s", session_id, message)
                await queries.update_session_status(conn, session_id, "failed", message)
                await queries.insert_run_log(
                    conn,
                    session_id=session_id,
                    step_number=None,
                    level="error",
                    message="Session worker crashed",
                    details=message,
                )
                await emit({"type": "status", "data": {"status": "failed", "end_reason": message}})
                await emit({"type": "error", "data": {"message": message}})
                return

            if final_state and final_state.get("status") == "stopped":
                logger.info("Skipping postmortem for stopped session %s", session_id)
                await emit(
                    {
                        "type": "postmortem",
                        "data": {
                            "run_analysis": "Session stopped by user before completion.",
                            "html_analysis": "",
                            "recommendations": "",
                        },
                    }
                )
                return

            try:
                await run_postmortem(db=conn, state=final_state, emit=lambda e: asyncio.create_task(emit(e)))
            except Exception as exc:
                fallback = {
                    "run_analysis": "Postmortem unavailable due to temporary model/API limits.",
                    "html_analysis": "",
                    "recommendations": json.dumps(
                        {"note": "Try rerunning postmortem later.", "error": str(exc)}
                    ),
                }
                await queries.save_postmortem(
                    conn,
                    session_id=session_id,
                    run_analysis=fallback["run_analysis"],
                    html_analysis=fallback["html_analysis"],
                    recommendations=fallback["recommendations"],
                )
                await queries.insert_run_log(
                    conn,
                    session_id=session_id,
                    step_number=None,
                    level="warning",
                    message="Postmortem unavailable",
                    details=str(exc),
                )
                await emit({"type": "postmortem", "data": fallback})
    finally:
        await redis_conn.close()
