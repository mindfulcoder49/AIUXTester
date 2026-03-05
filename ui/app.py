import asyncio
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from auth.models import RegisterRequest, LoginRequest, RefreshRequest, TokenResponse, UserResponse, UpdateTierRequest
from auth.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from auth.dependencies import get_current_user, require_admin
from database.db import init_db, get_db, open_db, close_db
from database import queries
from llm.registry import validate_provider_model, validate_config_for_tier, ConfigError
from config import MODEL_REGISTRY
from agent.test_graph import run_test_session
from agent.postmortem_graph import run_postmortem
from config import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    QUEUE_MODE,
    SESSION_WATCHDOG_INTERVAL_SECONDS,
    SESSION_WATCHDOG_STALE_SECONDS,
)
from jobs import run_session_job
from queueing import get_async_redis, get_queue, redis_available, session_channel
from rq import Retry

app = FastAPI()
logger = logging.getLogger("aiuxtester")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

SESSION_STREAMS: dict[str, asyncio.Queue] = {}
SESSION_TASKS: dict[str, asyncio.Task] = {}
WATCHDOG_TASK: Optional[asyncio.Task] = None


def _extract_bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    return None


async def _resolve_user(request: Request, token: Optional[str], db) -> Optional[dict]:
    token = token or _extract_bearer(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        return None
    return await queries.get_user_by_id(db, payload["sub"])


def refresh_expiry_iso() -> str:
    return (datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()


def normalize_start_url(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return v
    if v.startswith(("http://", "https://", "/")):
        return v
    return f"https://{v}"


@app.on_event("startup")
async def startup():
    global WATCHDOG_TASK
    await init_db()
    # create admin user if env vars present
    import os
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if admin_email and admin_password:
        async with open_db() as db:
            user = await queries.get_user_by_email(db, admin_email)
            if not user:
                await queries.create_user(
                    db,
                    user_id=str(uuid.uuid4()),
                    email=admin_email,
                    password_hash=hash_password(admin_password),
                    role="admin",
                    tier="pro",
                )

    if QUEUE_MODE == "redis":
        WATCHDOG_TASK = asyncio.create_task(session_watchdog())


@app.on_event("shutdown")
async def shutdown():
    global WATCHDOG_TASK
    if WATCHDOG_TASK:
        WATCHDOG_TASK.cancel()
        try:
            await WATCHDOG_TASK
        except asyncio.CancelledError:
            pass
        WATCHDOG_TASK = None
    await close_db()


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


async def session_watchdog():
    while True:
        try:
            if QUEUE_MODE != "redis":
                await asyncio.sleep(SESSION_WATCHDOG_INTERVAL_SECONDS)
                continue

            now = datetime.utcnow()
            redis_conn = get_async_redis() if redis_available() else None
            async with open_db() as db:
                running = await queries.list_running_sessions(db)
                for row in running:
                    session_id = row["id"]
                    last_log = await queries.get_last_run_log(db, session_id)
                    if not last_log:
                        # Session is queued but not yet started; don't mark stale.
                        continue
                    ref = _parse_iso(last_log.get("timestamp")) or _parse_iso(row.get("updated_at")) or _parse_iso(row.get("created_at"))
                    if not ref:
                        continue
                    age = (now - ref).total_seconds()
                    if age < SESSION_WATCHDOG_STALE_SECONDS:
                        continue
                    reason = (
                        f"Session appears stalled/crashed: no progress log for {int(age)}s. "
                        "Please retry the run."
                    )
                    await queries.update_session_status(db, session_id, "failed", reason)
                    await queries.insert_run_log(
                        db,
                        session_id=session_id,
                        step_number=None,
                        level="error",
                        message="Session marked failed by watchdog",
                        details=reason,
                    )
                    if redis_conn:
                        await redis_conn.publish(
                            session_channel(session_id),
                            json.dumps({"type": "status", "data": {"status": "failed", "end_reason": reason}}),
                        )
                        await redis_conn.publish(
                            session_channel(session_id),
                            json.dumps({"type": "error", "data": {"message": reason}}),
                        )
            if redis_conn:
                await redis_conn.close()
        except Exception:
            logger.exception("Session watchdog loop failed")

        await asyncio.sleep(SESSION_WATCHDOG_INTERVAL_SECONDS)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    static_version = int((BASE_DIR / "static" / "app.js").stat().st_mtime)
    return templates.TemplateResponse("index.html", {"request": request, "static_version": static_version})


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


# Auth
@app.post("/auth/register", response_model=TokenResponse)
async def register(data: RegisterRequest, db=Depends(get_db)):
    existing = await queries.get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    await queries.create_user(db, user_id=user_id, email=data.email, password_hash=hash_password(data.password))
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    await queries.create_refresh_token(db, user_id=user_id, token=refresh, expires_at=refresh_expiry_iso())
    return TokenResponse(access_token=access, refresh_token=refresh)


@app.post("/auth/login", response_model=TokenResponse)
async def login(data: LoginRequest, db=Depends(get_db)):
    user = await queries.get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access = create_access_token(user["id"])
    refresh = create_refresh_token(user["id"])
    await queries.create_refresh_token(db, user_id=user["id"], token=refresh, expires_at=refresh_expiry_iso())
    return TokenResponse(access_token=access, refresh_token=refresh)


@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db=Depends(get_db)):
    token_row = await queries.get_refresh_token(db, data.refresh_token)
    if not token_row or token_row["revoked"]:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if token_row["expires_at"]:
        try:
            if datetime.fromisoformat(token_row["expires_at"]) < datetime.utcnow():
                raise HTTPException(status_code=401, detail="Refresh token expired")
        except ValueError:
            pass
    user_id = token_row["user_id"]
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    await queries.create_refresh_token(db, user_id=user_id, token=refresh, expires_at=refresh_expiry_iso())
    return TokenResponse(access_token=access, refresh_token=refresh)


@app.post("/auth/logout")
async def logout(data: RefreshRequest, db=Depends(get_db)):
    await queries.revoke_refresh_token(db, data.refresh_token)
    return {"ok": True}


@app.get("/me", response_model=UserResponse)
async def me(user=Depends(get_current_user)):
    return UserResponse(id=user["id"], email=user["email"], role=user["role"], tier=user["tier"])


@app.get("/models")
async def get_models(user=Depends(get_current_user)):
    tier = user["tier"]
    return {provider: tiers.get(tier, []) for provider, tiers in MODEL_REGISTRY.items()}


# Admin
@app.get("/admin/users")
async def admin_list_users(admin=Depends(require_admin), db=Depends(get_db)):
    rows = await queries.list_users(db)
    return [dict(row) for row in rows]


@app.patch("/admin/users/{user_id}/tier")
async def admin_update_tier(user_id: str, data: UpdateTierRequest, admin=Depends(require_admin), db=Depends(get_db)):
    await queries.update_user_tier(db, user_id, data.tier)
    return {"ok": True}


@app.get("/admin/sessions")
async def admin_list_sessions(admin=Depends(require_admin), db=Depends(get_db)):
    rows = await queries.list_sessions_all(db)
    return [dict(row) for row in rows]


# Sessions
@app.post("/sessions")
async def create_session(payload: dict, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        config = validate_config_for_tier(payload.get("config", {}), user["tier"])
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))

    provider = payload.get("provider")
    model = payload.get("model")
    if not provider or not model:
        raise HTTPException(status_code=400, detail="Provider and model required")

    try:
        validate_provider_model(provider, model, user["tier"])
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session_id = str(uuid.uuid4())
    await queries.create_session(
        db,
        session_id=session_id,
        user_id=user["id"],
        goal=payload.get("goal", ""),
        start_url=normalize_start_url(payload.get("start_url", "")),
        mode=config.get("mode", "desktop"),
        provider=provider,
        model=model,
        config=config,
    )

    if QUEUE_MODE == "redis" and redis_available():
        get_queue("sessions").enqueue(
            run_session_job,
            session_id,
            job_id=session_id,
            retry=Retry(max=2, interval=[10, 30]),
            result_ttl=3600,
            failure_ttl=86400,
        )
    else:
        queue = asyncio.Queue()
        SESSION_STREAMS[session_id] = queue

        async def emit(event: dict):
            await queue.put(event)

        async def worker():
            async with open_db() as conn:
                final_state = None
                try:
                    logger.info("Session %s worker started", session_id)
                    session_row = await queries.get_session(conn, session_id)
                    final_state = await run_test_session(
                        db=conn,
                        session_row=session_row,
                        user_tier=user["tier"],
                        emit=lambda e: asyncio.create_task(emit(e)),
                    )
                except Exception as exc:
                    message = str(exc)
                    logger.exception("Session %s worker failed: %s", session_id, message)
                    await queries.update_session_status(conn, session_id, "failed", message)
                    await queries.insert_run_log(
                        conn,
                        session_id=session_id,
                        step_number=None,
                        level="error",
                        message="Session worker crashed",
                        details=message,
                    )
                    await emit({"type": "error", "data": {"message": message}})
                    return

                if final_state and final_state.get("status") == "stopped":
                    await emit({"type": "postmortem", "data": {
                        "run_analysis": "Session stopped by user before completion.",
                        "html_analysis": "",
                        "recommendations": "",
                    }})
                    return

                try:
                    await run_postmortem(db=conn, state=final_state, emit=lambda e: asyncio.create_task(emit(e)))
                except Exception as exc:
                    logger.warning("Session %s postmortem failed: %s", session_id, str(exc))
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

        SESSION_TASKS[session_id] = asyncio.create_task(worker())

    return {"session_id": session_id}


@app.get("/sessions")
async def list_sessions(user=Depends(get_current_user), db=Depends(get_db)):
    if user["role"] == "admin":
        rows = await queries.list_sessions_all(db)
    else:
        rows = await queries.list_sessions_for_user(db, user["id"])
    return [dict(r) for r in rows]


@app.get("/sessions/{session_id}")
async def get_session(session_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    session = await queries.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if user["role"] != "admin" and session["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    actions = await queries.list_actions(db, session_id)
    screenshots = await queries.list_screenshots(db, session_id)
    logs = await queries.list_run_logs(db, session_id)
    screenshot_summaries = []
    for row in screenshots:
        item = dict(row)
        item.pop("image_data", None)
        screenshot_summaries.append(item)
    return {
        "session": dict(session),
        "actions": [dict(a) for a in actions],
        "screenshots": screenshot_summaries,
        "logs": [dict(l) for l in logs],
    }


@app.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    session = await queries.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if user["role"] != "admin" and session["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    await queries.update_session_status(db, session_id, "stopped", "Stopped by user")
    return {"ok": True}


@app.get("/sessions/{session_id}/postmortem")
async def get_postmortem(session_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    session = await queries.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if user["role"] != "admin" and session["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    report = await queries.get_postmortem(db, session_id)
    return dict(report) if report else None


@app.get("/sessions/{session_id}/logs")
async def get_session_logs(session_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    session = await queries.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if user["role"] != "admin" and session["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    logs = await queries.list_run_logs(db, session_id)
    return [dict(l) for l in logs]


@app.get("/screenshots/{screenshot_id}")
async def get_screenshot(request: Request, screenshot_id: int, token: Optional[str] = None, db=Depends(get_db)):
    user = await _resolve_user(request, token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    row = await queries.get_screenshot(db, screenshot_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    # Access control: ensure user owns the session
    session = await queries.get_session(db, row["session_id"])
    if user["role"] != "admin" and session["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    image_data = row["image_data"]
    if isinstance(image_data, memoryview):
        image_data = image_data.tobytes()
    elif isinstance(image_data, bytearray):
        image_data = bytes(image_data)
    return Response(content=image_data, media_type="image/png")


@app.get("/sessions/{session_id}/stream")
async def stream(request: Request, session_id: str, token: Optional[str] = None, db=Depends(get_db)):
    user = await _resolve_user(request, token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    session = await queries.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if user["role"] != "admin" and session["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    if QUEUE_MODE == "redis" and redis_available():
        async def event_generator():
            redis_conn = get_async_redis()
            pubsub = redis_conn.pubsub()
            channel = session_channel(session_id)
            await pubsub.subscribe(channel)
            try:
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                    if message and message.get("data"):
                        payload = message["data"]
                        if isinstance(payload, bytes):
                            payload = payload.decode("utf-8")
                        yield f"data: {payload}\n\n"
                    else:
                        yield ": ping\n\n"
                        await asyncio.sleep(1)
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
                await redis_conn.close()
    else:
        queue = SESSION_STREAMS.get(session_id)
        if not queue:
            raise HTTPException(status_code=404, detail="Stream not found")

        async def event_generator():
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
