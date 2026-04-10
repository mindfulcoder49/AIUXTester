import asyncio
import json
import uuid
import logging
import os
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from itertools import combinations
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from auth.models import RegisterRequest, LoginRequest, RefreshRequest, TokenResponse, UserResponse, UpdateTierRequest
from auth.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    create_one_time_token, decode_one_time_token,
)
from utils.email import send_email
from auth.dependencies import get_current_user, require_admin
from database.db import init_db, get_db, open_db, close_db
from database import queries
from llm.registry import validate_provider_model, validate_config_for_tier, ConfigError
import config
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
from competition.runner import PROGRESSION_MODES, PAIRING_STRATEGIES, run_competition_batch_job, run_competition_run_job

app = FastAPI()
logger = logging.getLogger("aiuxtester")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
VUE_DIST_DIR = PROJECT_DIR / "frontend-vue" / "dist"
VUE_INDEX_FILE = VUE_DIST_DIR / "index.html"
UI_VARIANT = os.getenv("UI_VARIANT", "legacy").strip().lower()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
if VUE_DIST_DIR.exists():
    app.mount("/static-vue", StaticFiles(directory=str(VUE_DIST_DIR)), name="static-vue")
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


def _parse_entry_ids(value) -> list[int]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, int)]
    try:
        parsed = json.loads(value or "[]")
        return [item for item in parsed if isinstance(item, int)]
    except Exception:
        return []


def _choose_selected_run(runs: list[dict], requested_run_id: Optional[int]) -> Optional[dict]:
    if requested_run_id is not None:
        for run in runs:
            if int(run["id"]) == int(requested_run_id):
                return run
    for run in runs:
        if run["status"] == "running":
            return run
    for run in runs:
        if run["status"] == "awaiting_round":
            return run
    completed_runs = [run for run in runs if run["status"] == "complete"]
    if completed_runs:
        return sorted(completed_runs, key=lambda item: item["run_number"], reverse=True)[0]
    queued_runs = [run for run in runs if run["status"] == "queued"]
    if queued_runs:
        return sorted(queued_runs, key=lambda item: item["run_number"])[0]
    return sorted(runs, key=lambda item: item["run_number"], reverse=True)[0] if runs else None


def _build_competition_summary(entries: list[dict], runs: list[dict], matches: list[dict]) -> dict:
    entry_ids = [entry["id"] for entry in entries]
    total_possible_pairs = len(list(combinations(entry_ids, 2))) if len(entry_ids) > 1 else 0

    matches_by_run: dict[int, list[dict]] = defaultdict(list)
    for match in matches:
        run_id = match["run_id"]
        if run_id is None:
            continue
        matches_by_run[int(run_id)].append(match)

    completed_runs = [run for run in runs if run["status"] == "complete" and run.get("champion_entry_id")]
    champion_counts = Counter(run["champion_entry_id"] for run in completed_runs if run.get("champion_entry_id"))
    finals_counts = Counter()
    unique_pairs_seen = set()
    rivalry_map = defaultdict(lambda: {"meetings": 0, "wins": Counter()})

    for run in runs:
        run_matches = matches_by_run.get(int(run["id"]), [])
        if not run_matches:
            continue

        max_round = max(match["round_number"] for match in run_matches)
        final_match = sorted(
            [match for match in run_matches if match["round_number"] == max_round],
            key=lambda item: item["match_number"],
        )[-1]
        for entry_id in _parse_entry_ids(final_match.get("entry_ids")):
            finals_counts[entry_id] += 1

        for match in run_matches:
            match_entry_ids = _parse_entry_ids(match.get("entry_ids"))
            for left, right in combinations(sorted(match_entry_ids), 2):
                pair = (left, right)
                unique_pairs_seen.add(pair)
                rivalry = rivalry_map[pair]
                rivalry["meetings"] += 1
                if match.get("winner_entry_id"):
                    rivalry["wins"][match["winner_entry_id"]] += 1

    leaderboard = []
    for entry in entries:
        championships = champion_counts[entry["id"]]
        finals = finals_counts[entry["id"]]
        leaderboard.append({
            "entry_id": entry["id"],
            "label": entry.get("start_url") or entry.get("session_id"),
            "goal": entry.get("goal"),
            "championships": championships,
            "finals": finals,
            "championship_share": (championships / len(completed_runs)) if completed_runs else 0,
        })

    leaderboard.sort(
        key=lambda item: (
            item["championships"],
            item["finals"],
            item["label"] or "",
        ),
        reverse=True,
    )

    top_rivalries = []
    for (entry_a_id, entry_b_id), rivalry in sorted(
        rivalry_map.items(),
        key=lambda item: (item[1]["meetings"], sum(item[1]["wins"].values())),
        reverse=True,
    )[:6]:
        top_rivalries.append({
            "entry_a_id": entry_a_id,
            "entry_b_id": entry_b_id,
            "meetings": rivalry["meetings"],
            "wins_a": rivalry["wins"].get(entry_a_id, 0),
            "wins_b": rivalry["wins"].get(entry_b_id, 0),
        })

    consensus_champion = leaderboard[0] if leaderboard and leaderboard[0]["championships"] > 0 else None
    return {
        "run_count": len(runs),
        "completed_run_count": len(completed_runs),
        "running_run_count": sum(1 for run in runs if run["status"] == "running"),
        "awaiting_round_count": sum(1 for run in runs if run["status"] == "awaiting_round"),
        "queued_run_count": sum(1 for run in runs if run["status"] == "queued"),
        "failed_run_count": sum(1 for run in runs if run["status"] == "failed"),
        "unique_champion_count": len(champion_counts),
        "pairing_coverage": (len(unique_pairs_seen) / total_possible_pairs) if total_possible_pairs else 0,
        "consensus_champion": consensus_champion,
        "leaderboard": leaderboard,
        "top_rivalries": top_rivalries,
    }


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
            await queries.backfill_legacy_competition_runs(db)
    else:
        async with open_db() as db:
            await queries.backfill_legacy_competition_runs(db)

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
    if UI_VARIANT == "vue":
        return _serve_vue_index()
    static_version = int((BASE_DIR / "static" / "app.js").stat().st_mtime)
    return templates.TemplateResponse("index.html", {"request": request, "static_version": static_version})


@app.get("/vue-app", response_class=HTMLResponse)
async def vue_index():
    return _serve_vue_index()


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


def _serve_vue_index():
    if not VUE_INDEX_FILE.exists():
        return HTMLResponse(
            "<h1>Vue frontend not built</h1><p>Run <code>npm install</code> and <code>npm run build</code> in <code>frontend-vue/</code>, or use Dockerfile.vue.</p>",
            status_code=503,
        )
    return FileResponse(str(VUE_INDEX_FILE))


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


@app.post("/auth/request-password-reset")
async def request_password_reset(request: Request, db=Depends(get_db)):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    user = await queries.get_user_by_email(db, email)
    if user:
        token    = create_one_time_token(user["id"], "password_reset")
        reset_url = f"{config.APP_BASE_URL}/#/reset-password?token={token}"
        await send_email(
            to=email,
            subject="Reset your AIUXTester password",
            html_body=(
                f"<p>Click the link below to reset your password. "
                f"It expires in 15 minutes.</p>"
                f'<p><a href="{reset_url}">{reset_url}</a></p>'
            ),
            text_body=f"Reset your AIUXTester password:\n{reset_url}\n\nExpires in 15 minutes.",
        )
    # Always return OK so we don't leak whether an account exists
    return {"ok": True}


@app.post("/auth/reset-password")
async def reset_password(request: Request, db=Depends(get_db)):
    body     = await request.json()
    token    = (body.get("token") or "").strip()
    password = (body.get("password") or "").strip()
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters.")
    user_id = decode_one_time_token(token, "password_reset")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")
    await queries.update_user_password(db, user_id, hash_password(password))
    return {"ok": True}


@app.post("/auth/magic-link")
async def request_magic_link(request: Request, db=Depends(get_db)):
    body  = await request.json()
    email = (body.get("email") or "").strip().lower()
    user  = await queries.get_user_by_email(db, email)
    if user:
        token     = create_one_time_token(user["id"], "magic_link")
        login_url = f"{config.APP_BASE_URL}/#/magic?token={token}"
        await send_email(
            to=email,
            subject="Your AIUXTester login link",
            html_body=(
                f"<p>Click the link below to sign in to AIUXTester. "
                f"It expires in 15 minutes.</p>"
                f'<p><a href="{login_url}">{login_url}</a></p>'
            ),
            text_body=f"Sign in to AIUXTester:\n{login_url}\n\nExpires in 15 minutes.",
        )
    return {"ok": True}


@app.get("/auth/magic-link/verify", response_model=TokenResponse)
async def verify_magic_link(token: str, db=Depends(get_db)):
    user_id = decode_one_time_token(token, "magic_link")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired magic link.")
    user = await queries.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Account not found.")
    access_token   = create_access_token(user_id)
    refresh_token  = create_refresh_token(user_id)
    expires_at     = (datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()
    await queries.create_refresh_token(db, user_id=user_id, token=refresh_token, expires_at=expires_at)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


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


@app.patch("/admin/users/{user_id}/password")
async def admin_set_password(user_id: str, request: Request, admin=Depends(require_admin), db=Depends(get_db)):
    body = await request.json()
    new_password = (body.get("password") or "").strip()
    if len(new_password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters.")
    target = await queries.get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    bootstrap_email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    if bootstrap_email and target["email"].strip().lower() == bootstrap_email:
        raise HTTPException(status_code=403, detail="Cannot change the bootstrap admin password here. Update ADMIN_PASSWORD in your environment instead.")
    await queries.update_user_password(db, user_id, hash_password(new_password))
    return {"ok": True}


@app.get("/admin/sessions")
async def admin_list_sessions(
    status: Optional[str] = None,
    limit: int = 50,
    admin=Depends(require_admin),
    db=Depends(get_db),
):
    rows = await queries.list_sessions_admin(db, status=status, limit=min(limit, 500))
    return [dict(row) for row in rows]


@app.get("/admin/sessions/{session_id}/memory")
async def admin_session_memory(session_id: str, admin=Depends(require_admin), db=Depends(get_db)):
    session = await queries.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return await queries.get_memory(db, session_id)


@app.get("/admin/queue")
async def admin_queue_stats(admin=Depends(require_admin)):
    from queueing import get_sync_redis, redis_available
    if not redis_available():
        return {"available": False}
    try:
        from rq import Queue
        conn = get_sync_redis()
        q = Queue("sessions", connection=conn)
        return {
            "available": True,
            "queued": q.count,
            "active": len(q.started_job_registry),
            "failed": len(q.failed_job_registry),
            "finished": len(q.finished_job_registry),
            "deferred": len(q.deferred_job_registry),
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


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


# ── Competitions ─────────────────────────────────────────────────────────────

TERMINAL_SESSION_STATUSES = {"completed", "failed", "stopped", "loop_detected"}


@app.post("/competitions")
async def create_competition(payload: dict, admin=Depends(require_admin), db=Depends(get_db)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    competition_id = str(uuid.uuid4())
    await queries.create_competition(
        db,
        competition_id=competition_id,
        name=name,
        description=payload.get("description"),
        created_by=admin["id"],
    )
    return {"competition_id": competition_id}


@app.get("/competitions")
async def list_competitions(user=Depends(get_current_user), db=Depends(get_db)):
    rows = await queries.list_competitions(db)
    result = []
    for row in rows:
        entries = await queries.list_competition_entries(db, row["id"])
        runs = [dict(run) for run in await queries.list_competition_runs(db, row["id"])]
        latest_complete_run = next((run for run in runs if run["status"] == "complete"), None)
        result.append({
            **dict(row),
            "entry_count": len(entries),
            "run_count": len(runs),
            "completed_run_count": sum(1 for run in runs if run["status"] == "complete"),
            "latest_champion_entry_id": latest_complete_run["champion_entry_id"] if latest_complete_run else None,
        })
    return result


@app.get("/competitions/{competition_id}")
async def get_competition(
    competition_id: str,
    run_id: Optional[int] = None,
    include_all_runs: bool = False,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    competition = await queries.get_competition(db, competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    entries = await queries.list_competition_entries(db, competition_id)
    all_matches = [dict(match) for match in await queries.list_competition_matches(db, competition_id)]
    runs = [dict(run) for run in await queries.list_competition_runs(db, competition_id)]

    # Enrich entries with session + user info (flattened for the frontend)
    enriched_entries = []
    for entry in entries:
        session = await queries.get_session(db, entry["session_id"])
        user_row = await queries.get_user_by_id(db, entry["user_id"])
        actions = await queries.list_actions(db, entry["session_id"])
        first_shot = await queries.get_first_screenshot(db, entry["session_id"])
        enriched_entries.append({
            **dict(entry),
            "email": user_row["email"] if user_row else None,
            "start_url": session["start_url"] if session else None,
            "goal": session["goal"] if session else None,
            "session_status": session["status"] if session else None,
            "action_count": len(actions),
            "first_screenshot_id": first_shot["id"] if first_shot else None,
        })

    entry_map = {entry["id"]: entry for entry in enriched_entries}
    for run in runs:
        run["match_count"] = sum(1 for match in all_matches if match["run_id"] == run["id"])
        champion = entry_map.get(run.get("champion_entry_id"))
        run["champion_label"] = (
            champion.get("start_url") if champion and champion.get("start_url") else (champion.get("session_id") if champion else None)
        )
    selected_run = _choose_selected_run(runs, run_id)
    if include_all_runs:
        displayed_matches = all_matches
    else:
        displayed_matches = [
            match for match in all_matches
            if selected_run and match["run_id"] == selected_run["id"]
        ]
    summary = _build_competition_summary(enriched_entries, runs, all_matches)

    return {
        "competition": {
            **dict(competition),
            "run_count": len(runs),
            "completed_run_count": summary["completed_run_count"],
        },
        "entries": enriched_entries,
        "runs": runs,
        "selected_run": selected_run,
        "matches": displayed_matches,
        "summary": summary,
    }


@app.patch("/competitions/{competition_id}")
async def update_competition(competition_id: str, payload: dict, admin=Depends(require_admin), db=Depends(get_db)):
    competition = await queries.get_competition(db, competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    await queries.update_competition(
        db,
        competition_id,
        name=payload.get("name"),
        description=payload.get("description"),
    )
    if "status" in payload:
        allowed = {"open", "closed"}
        if payload["status"] not in allowed:
            raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
        await queries.update_competition_status(db, competition_id, payload["status"])
    return {"ok": True}


@app.post("/competitions/{competition_id}/entries")
async def submit_competition_entry(
    competition_id: str, payload: dict, user=Depends(get_current_user), db=Depends(get_db)
):
    competition = await queries.get_competition(db, competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    if competition["status"] != "open":
        raise HTTPException(status_code=400, detail="Competition is not accepting entries")

    session_id = (payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    session = await queries.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Session does not belong to you")
    if session["status"] not in TERMINAL_SESSION_STATUSES:
        raise HTTPException(status_code=400, detail="Session must be completed before submitting")

    existing = await queries.get_entry_for_user(db, competition_id, user["id"])
    if existing:
        raise HTTPException(status_code=409, detail="You have already submitted an entry to this competition")

    entry_id = await queries.add_competition_entry(
        db,
        competition_id=competition_id,
        session_id=session_id,
        user_id=user["id"],
        note=payload.get("note"),
    )
    return {"entry_id": entry_id}


async def _queue_competition_runs(competition_id: str, payload: dict, admin: dict, db):
    competition = await queries.get_competition(db, competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    if competition["status"] == "running":
        raise HTTPException(status_code=400, detail=f"Competition cannot be run from status '{competition['status']}'")

    entries = await queries.list_competition_entries(db, competition_id)
    if len(entries) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 entries to run a competition")

    provider = payload.get("provider", "openai")
    model = payload.get("model", "gpt-5-mini")
    try:
        validate_provider_model(provider, model, "pro")
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    pairing_strategy = (payload.get("pairing_strategy") or "balanced_random").strip().lower()
    if pairing_strategy not in PAIRING_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"pairing_strategy must be one of {sorted(PAIRING_STRATEGIES)}")
    progression_mode = (payload.get("progression_mode") or "automatic").strip().lower()
    if progression_mode not in PROGRESSION_MODES:
        raise HTTPException(status_code=400, detail=f"progression_mode must be one of {sorted(PROGRESSION_MODES)}")

    try:
        count = int(payload.get("count", 1))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="count must be an integer")
    if count < 1 or count > 50:
        raise HTTPException(status_code=400, detail="count must be between 1 and 50")

    try:
        base_seed = int(payload["pairing_seed"]) if payload.get("pairing_seed") is not None else random.SystemRandom().randrange(1, 2**31 - 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="pairing_seed must be an integer")

    next_run_number = await queries.get_next_competition_run_number(db, competition_id)
    run_ids = []
    for offset in range(count):
        run_number = next_run_number + offset
        pairing_seed = base_seed + offset if pairing_strategy != "submitted_order" else base_seed
        run_id = await queries.create_competition_run(
            db,
            competition_id=competition_id,
            run_number=run_number,
            pairing_strategy=pairing_strategy,
            progression_mode=progression_mode,
            pairing_seed=pairing_seed,
            provider=provider,
            model=model,
            created_by=admin["id"],
            status="queued",
        )
        run_ids.append(run_id)

    await queries.update_competition_status(db, competition_id, "running")

    if run_ids:
        await queries.update_competition_run_status(db, run_ids[0], "running")

    if progression_mode == "manual":
        target_run_id = run_ids[0]
        if QUEUE_MODE == "redis" and redis_available():
            get_queue("sessions").enqueue(
                run_competition_run_job,
                competition_id,
                target_run_id,
                result_ttl=3600,
                failure_ttl=86400,
            )
        else:
            async def _run_inline():
                from competition.runner import _run_single_competition_run
                await _run_single_competition_run(competition_id, target_run_id)

            asyncio.create_task(_run_inline())
    else:
        if QUEUE_MODE == "redis" and redis_available():
            get_queue("sessions").enqueue(
                run_competition_batch_job,
                competition_id,
                run_ids,
                job_id=f"competition-{competition_id}-runs-{run_ids[0]}-{run_ids[-1]}",
                result_ttl=3600,
                failure_ttl=86400,
            )
        else:
            async def _run_inline():
                from competition.runner import _run_competition_batch
                await _run_competition_batch(competition_id, run_ids)

            asyncio.create_task(_run_inline())

    return {
        "ok": True,
        "competition_id": competition_id,
        "count": count,
        "progression_mode": progression_mode,
        "run_ids": run_ids,
    }


@app.post("/competitions/{competition_id}/runs")
async def create_competition_runs(competition_id: str, payload: dict, admin=Depends(require_admin), db=Depends(get_db)):
    return await _queue_competition_runs(competition_id, payload, admin, db)


@app.post("/competitions/{competition_id}/run")
async def run_competition(competition_id: str, payload: dict, admin=Depends(require_admin), db=Depends(get_db)):
    adjusted_payload = dict(payload or {})
    adjusted_payload.setdefault("count", 1)
    return await _queue_competition_runs(competition_id, adjusted_payload, admin, db)


@app.post("/competitions/{competition_id}/next-round")
async def continue_competition_round(competition_id: str, admin=Depends(require_admin), db=Depends(get_db)):
    competition = await queries.get_competition(db, competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")

    runs = [dict(run) for run in await queries.list_competition_runs(db, competition_id)]
    if any(run["status"] == "running" for run in runs):
        raise HTTPException(status_code=400, detail="A round is already running")

    awaiting_runs = sorted(
        [run for run in runs if run["status"] == "awaiting_round" and run.get("progression_mode") == "manual"],
        key=lambda item: item["run_number"],
    )
    if not awaiting_runs:
        raise HTTPException(status_code=400, detail="No manual run is waiting for the next round")

    target_run = awaiting_runs[0]
    await queries.update_competition_run_status(db, target_run["id"], "running")
    await queries.update_competition_status(db, competition_id, "running")

    if QUEUE_MODE == "redis" and redis_available():
        get_queue("sessions").enqueue(
            run_competition_run_job,
            competition_id,
            target_run["id"],
            result_ttl=3600,
            failure_ttl=86400,
        )
    else:
        async def _run_inline():
            from competition.runner import _run_single_competition_run
            await _run_single_competition_run(competition_id, target_run["id"])

        asyncio.create_task(_run_inline())

    return {"ok": True, "action": "next_round", "run_id": target_run["id"]}


@app.post("/competitions/{competition_id}/next-bracket")
async def continue_competition_bracket(competition_id: str, admin=Depends(require_admin), db=Depends(get_db)):
    competition = await queries.get_competition(db, competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")

    runs = [dict(run) for run in await queries.list_competition_runs(db, competition_id)]
    if any(run["status"] == "running" for run in runs):
        raise HTTPException(status_code=400, detail="A bracket is already running")
    if any(run["status"] == "awaiting_round" and run.get("progression_mode") == "manual" for run in runs):
        raise HTTPException(status_code=400, detail="Finish the paused round before starting the next bracket")

    queued_runs = sorted(
        [run for run in runs if run["status"] == "queued" and run.get("progression_mode") == "manual"],
        key=lambda item: item["run_number"],
    )
    if not queued_runs:
        raise HTTPException(status_code=400, detail="No queued manual bracket is waiting to start")

    target_run = queued_runs[0]
    await queries.update_competition_run_status(db, target_run["id"], "running")
    await queries.update_competition_status(db, competition_id, "running")

    if QUEUE_MODE == "redis" and redis_available():
        get_queue("sessions").enqueue(
            run_competition_run_job,
            competition_id,
            target_run["id"],
            result_ttl=3600,
            failure_ttl=86400,
        )
    else:
        async def _run_inline():
            from competition.runner import _run_single_competition_run
            await _run_single_competition_run(competition_id, target_run["id"])

        asyncio.create_task(_run_inline())

    return {"ok": True, "action": "next_bracket", "run_id": target_run["id"]}


@app.get("/competitions/{competition_id}/recap")
async def get_competition_recap(competition_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    competition = await queries.get_competition(db, competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    recap = await queries.get_latest_competition_recap(db, competition_id)
    if not recap:
        raise HTTPException(status_code=404, detail="No recap generated yet")
    recap_dict = dict(recap)
    try:
        recap_dict["entry_profiles"] = json.loads(recap_dict.get("entry_profiles") or "{}")
    except Exception:
        recap_dict["entry_profiles"] = {}
    history = await queries.list_competition_recaps(db, competition_id)
    recap_dict["generation_count"] = len(history)
    return recap_dict


@app.post("/competitions/{competition_id}/recap/generate")
async def generate_competition_recap(
    competition_id: str,
    payload: dict,
    admin=Depends(require_admin),
    db=Depends(get_db),
):
    competition = await queries.get_competition(db, competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    if competition["status"] != "complete":
        raise HTTPException(status_code=400, detail="Recap can only be generated for completed competitions")
    provider = (payload.get("provider") or "openai").strip()
    model = (payload.get("model") or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="model is required")
    from competition.recap import generate_recap
    try:
        return await generate_recap(competition_id, provider=provider, model=model)
    except Exception as exc:
        logger.exception("Recap generation failed for %s: %s", competition_id, exc)
        raise HTTPException(status_code=500, detail=f"Recap generation failed: {exc}")


@app.post("/sessions/{session_id}/export-to-vibecode")
async def export_session_to_vibecode(
    session_id: str,
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Build a single-session export payload and POST it to VibeCode International.

    Request body (JSON):
        { "app_name": "My App", "app_description": "optional" }
    """
    from config import VIBECODE_EXPORT_URL, VIBECODE_EXPORT_TOKEN
    import base64
    import urllib.request as _urllib_request
    import urllib.error as _urllib_error

    if not VIBECODE_EXPORT_URL:
        raise HTTPException(status_code=503, detail="VibeCode export is not configured on this server.")
    if not VIBECODE_EXPORT_TOKEN:
        raise HTTPException(status_code=503, detail="VibeCode export token is not configured on this server.")

    session_row = await queries.get_session(db, session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail="Session not found")
    session_dict = dict(session_row)
    if user["role"] != "admin" and session_dict["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.json()
    app_name = (body.get("app_name") or "").strip() or None
    app_description = (body.get("app_description") or "").strip() or None

    postmortem_row = await queries.get_postmortem(db, session_id)
    postmortem = dict(postmortem_row) if postmortem_row else None

    actions = [dict(a) for a in await queries.list_actions(db, session_id)]
    screenshots_raw = await queries.list_screenshots(db, session_id)

    # Index screenshots by step_number
    screenshots_by_step: dict[int, dict] = {}
    for sc in screenshots_raw:
        sc = dict(sc)
        img = sc.get("image_data")
        if isinstance(img, memoryview):
            img = bytes(img)
        elif isinstance(img, bytearray):
            img = bytes(img)
        sc["image_b64"] = base64.b64encode(img).decode("ascii") if img else None
        sc.pop("image_data", None)
        screenshots_by_step[sc["step_number"]] = sc

    # Index actions by step_number
    actions_by_step: dict[int, dict] = {}
    for a in actions:
        actions_by_step[a["step_number"]] = dict(a)

    # Union of all step numbers (screenshots + actions), ordered
    all_step_nums = sorted(set(screenshots_by_step.keys()) | set(actions_by_step.keys()))

    steps = []
    for step_num in all_step_nums:
        sc     = screenshots_by_step.get(step_num)
        action = actions_by_step.get(step_num)
        params = action.get("action_params") if action else None
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                pass
        steps.append({
            "step_number":    step_num,
            "action_type":    action["action_type"] if action else "initialize",
            "action_params":  params,
            "intent":         action.get("intent") if action else None,
            "reasoning":      action.get("reasoning") if action else None,
            "action_result":  action.get("action_result") if action else None,
            "success":        bool(action.get("success", True)) if action else True,
            "error_message":  action.get("error_message") if action else None,
            "page_url":       sc["url"] if sc else None,
            "screenshot_b64": sc["image_b64"] if sc else None,
            "timestamp":      action.get("timestamp") if action else (sc.get("timestamp") if sc else None),
        })

    payload = {
        "external_session_id": session_id,
        "external_user_id":    str(user["id"]),
        "user_email":          user.get("email"),
        "app_name":            app_name,
        "app_description":     app_description,
        "exported_at":         datetime.utcnow().isoformat() + "Z",
        "session": {
            "external_id": session_dict.get("id"),
            "goal":        session_dict.get("goal"),
            "start_url":   session_dict.get("start_url"),
            "mode":        session_dict.get("mode"),
            "provider":    session_dict.get("provider"),
            "model":       session_dict.get("model"),
            "status":      session_dict.get("status"),
        },
        "postmortem": {
            "run_analysis":    postmortem.get("run_analysis"),
            "html_analysis":   postmortem.get("html_analysis"),
            "recommendations": postmortem.get("recommendations"),
        } if postmortem else None,
        "steps": steps,
    }

    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = _urllib_request.Request(
        VIBECODE_EXPORT_URL,
        data=body_bytes,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {VIBECODE_EXPORT_TOKEN}",
        },
        method="POST",
    )

    try:
        with _urllib_request.urlopen(req, timeout=30) as resp:
            response_body = resp.read().decode("utf-8")
    except _urllib_error.HTTPError as exc:
        error_text = exc.read().decode("utf-8")
        raise HTTPException(status_code=502, detail=f"VibeCode returned {exc.code}: {error_text[:500]}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Export request failed: {exc}")

    try:
        result = json.loads(response_body)
    except Exception:
        result = {"raw": response_body}

    return {"ok": True, "vibecode": result}


@app.get("/competitions/{competition_id}/export")
async def export_competition(
    competition_id: str,
    no_screenshots: bool = False,
    admin=Depends(require_admin),
):
    """
    Build a full competition export payload (JSON).

    Query params:
        no_screenshots=true   Omit base64 screenshot data (much smaller, ~200 KB vs ~60 MB).

    The returned JSON is the canonical import format for the Vibecode Olympics site.
    """
    competition = None
    async with open_db() as db:
        competition = await queries.get_competition(db, competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    if competition["status"] != "complete":
        raise HTTPException(status_code=400, detail="Only completed competitions can be exported")

    from competition.export import build_export_payload
    try:
        payload = await build_export_payload(
            competition_id,
            include_screenshots=not no_screenshots,
        )
    except Exception as exc:
        logger.exception("Export failed for %s: %s", competition_id, exc)
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")

    filename = f"{competition_id}_export.json"
    import json as _json
    body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
