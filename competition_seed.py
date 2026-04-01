#!/usr/bin/env python3
"""
competition_seed.py — Seed a local AIUXTester instance for Vibecode Olympics testing.

Creates 7 test users, runs one session per user against 7 different websites
concurrently, waits for all sessions to finish, then submits each completed
session to a new competition.  Log in as admin and click "Run Competition".

────────────────────────────────────────────────────────────────────────────
Quick start (7 local workers, same config as Fly.io):

  # 1. In your .env, set:
  #    QUEUE_MODE=redis
  #    REDIS_URL=redis://127.0.0.1:6379/0
  #    (make sure Redis is running: redis-server)

  # 2. Start the app (one terminal)
  source .venv/bin/activate
  uvicorn main:app --reload --port 8000

  # 3. Start 7 workers (one per terminal, or all in background)
  for i in $(seq 7); do python worker_main.py & done

  # 4. Run this seed script
  python competition_seed.py

  # 5. Go to http://127.0.0.1:8000/#/competitions and log in as admin
  #    Click the competition → "Run Competition" → pick judge model → go
────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ── Config ───────────────────────────────────────────────────────────────────

GOAL = "Try to accomplish something significant on this website"

# (url, email) — one entry per user/website
ENTRIES = [
    ("alcivartech.com",                               "vibecode_user1@example.com"),
    ("publicdatawatch.com",                           "vibecode_user2@example.com"),
    ("mypetfreelancer.alcivartech.com",               "vibecode_user3@example.com"),
    ("aisurvivalmag.com",                             "vibecode_user4@example.com"),
    ("https://literary-essays.fly.dev/",              "vibecode_user5@example.com"),
    ("https://alcivartech-course-creator.fly.dev/",   "vibecode_user6@example.com"),
    ("https://life-agent.fly.dev/",                   "vibecode_user7@example.com"),
]

USER_PASSWORD = "vibecode2024"
TERMINAL_STATUSES = {"completed", "failed", "stopped", "loop_detected"}
STATUS_ICON = {
    "completed": "✓",
    "failed":    "✗",
    "stopped":   "◼",
    "loop_detected": "↻",
    "timeout":   "⏱",
}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class UserRun:
    index: int
    email: str
    url: str
    token: str = ""
    session_id: str = ""
    status: str = "pending"
    action_count: int = 0
    entry_id: int = 0
    error: Optional[str] = None
    _started: float = field(default_factory=time.monotonic, repr=False)
    _ended: Optional[float] = field(default=None, repr=False)

    @property
    def duration(self) -> Optional[float]:
        if self._ended is not None:
            return round(self._ended - self._started, 1)
        return None


# ── HTTP helpers ──────────────────────────────────────────────────────────────

async def _register_or_login(
    client: httpx.AsyncClient, email: str, password: str
) -> str:
    """Return an access token, registering the account if it doesn't exist."""
    try:
        r = await client.post(
            "/auth/register", json={"email": email, "password": password}
        )
        r.raise_for_status()
        return r.json()["access_token"]
    except httpx.HTTPStatusError:
        r = await client.post(
            "/auth/login", json={"email": email, "password": password}
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def _run_session(
    client: httpx.AsyncClient,
    run: UserRun,
    *,
    provider: str,
    model: str,
    max_steps: int,
    poll_seconds: float,
    timeout_seconds: float,
) -> None:
    """Submit a session for this user and poll until a terminal status."""
    headers = {"Authorization": f"Bearer {run.token}"}

    # Submit
    try:
        r = await client.post(
            "/sessions",
            json={
                "goal": GOAL,
                "start_url": run.url,
                "provider": provider,
                "model": model,
                "config": {
                    "mode": "desktop",
                    "max_steps": max_steps,
                    "stop_on_first_error": False,
                },
            },
            headers=headers,
        )
        r.raise_for_status()
        run.session_id = r.json()["session_id"]
        run._started = time.monotonic()
        print(f"  [{run.index + 1}/7] submitted  {run.email}  →  {run.url}")
    except Exception as exc:
        run.status = "failed"
        run.error = f"submit failed: {exc}"
        run._ended = time.monotonic()
        print(f"  [{run.index + 1}/7] ✗ submit error: {exc}")
        return

    # Poll to terminal
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        await asyncio.sleep(poll_seconds)
        try:
            r = await client.get(
                f"/sessions/{run.session_id}", headers=headers
            )
            r.raise_for_status()
            data = r.json()
            status = data["session"]["status"]
            if status in TERMINAL_STATUSES:
                run.status = status
                run.action_count = len(data.get("actions", []))
                run._ended = time.monotonic()
                icon = STATUS_ICON.get(status, "?")
                print(
                    f"  [{run.index + 1}/7] {icon} {status:<14}  "
                    f"{run.duration}s  {run.action_count} actions  {run.email}"
                )
                return
        except Exception as exc:
            run.error = str(exc)

    # Timed out — force-stop and move on
    run.status = "timeout"
    run._ended = time.monotonic()
    print(f"  [{run.index + 1}/7] ⏱ timeout  {run.email}")
    try:
        await client.post(
            f"/sessions/{run.session_id}/stop", headers=headers
        )
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

async def async_main(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/")

    async with httpx.AsyncClient(base_url=base, timeout=30.0) as client:

        # ── 1. Admin auth ────────────────────────────────────────────────────
        print("\n[1/5] Authenticating admin...")
        admin_token = await _register_or_login(
            client, args.admin_email, args.admin_password
        )
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        print(f"  ✓ {args.admin_email}")

        # ── 2. Register test users ───────────────────────────────────────────
        print("\n[2/5] Registering test users...")
        runs: list[UserRun] = []
        for i, (url, email) in enumerate(ENTRIES):
            token = await _register_or_login(client, email, USER_PASSWORD)
            runs.append(UserRun(index=i, email=email, url=url, token=token))
            print(f"  ✓ user {i + 1}: {email}")

        # ── 3. Create competition ────────────────────────────────────────────
        print("\n[3/5] Creating competition...")
        r = await client.post(
            "/competitions",
            json={
                "name": "Vibecode Olympics — Local Test",
                "description": (
                    "7 websites head-to-head, judged by LLM on UX testing quality. "
                    "May the best run win."
                ),
            },
            headers=admin_headers,
        )
        r.raise_for_status()
        competition_id = r.json()["competition_id"]
        print(f"  ✓ id: {competition_id}")
        print(f"    url: {base}/#/competitions/{competition_id}")

        # ── 4. Run all sessions concurrently ─────────────────────────────────
        print(f"\n[4/5] Running {len(runs)} sessions concurrently...\n")
        await asyncio.gather(
            *[
                _run_session(
                    client,
                    run,
                    provider=args.provider,
                    model=args.model,
                    max_steps=args.max_steps,
                    poll_seconds=args.poll_seconds,
                    timeout_seconds=args.timeout_seconds,
                )
                for run in runs
            ],
            return_exceptions=True,
        )

        # ── 5. Submit entries to competition ─────────────────────────────────
        print(f"\n[5/5] Submitting entries to competition...")
        submitted = 0
        skipped = 0
        for run in runs:
            if not run.session_id or run.status not in TERMINAL_STATUSES:
                print(
                    f"  skip  {run.email}  (status={run.status}"
                    + (f", error={run.error}" if run.error else "")
                    + ")"
                )
                skipped += 1
                continue
            user_headers = {"Authorization": f"Bearer {run.token}"}
            try:
                r = await client.post(
                    f"/competitions/{competition_id}/entries",
                    json={
                        "session_id": run.session_id,
                        "note": f"Testing {run.url}",
                    },
                    headers=user_headers,
                )
                r.raise_for_status()
                run.entry_id = r.json()["entry_id"]
                icon = STATUS_ICON.get(run.status, "?")
                print(
                    f"  ✓ entry #{run.entry_id}  {icon} {run.status:<14}  {run.email}"
                )
                submitted += 1
            except httpx.HTTPStatusError as exc:
                print(f"  ✗ {run.email}: {exc.response.text}")
                skipped += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    durations = [r.duration for r in runs if r.duration is not None]
    dur_str = (
        f"min {min(durations):.0f}s / avg {sum(durations)/len(durations):.0f}s / max {max(durations):.0f}s"
        if durations else "—"
    )

    print("\n" + "=" * 70)
    print("  SEED COMPLETE")
    print("=" * 70)
    print(f"  Competition ID : {competition_id}")
    print(f"  URL            : {base}/#/competitions/{competition_id}")
    print(f"  Entries        : {submitted} submitted, {skipped} skipped")
    print(f"  Session times  : {dur_str}")
    print()
    print(f"  Admin login    : {args.admin_email}  /  {args.admin_password}")
    print(f"  Test users     : vibecode_user1@example.com ... vibecode_user7@example.com")
    print(f"  User password  : {USER_PASSWORD}")
    print()
    print("  Next steps:")
    print("    1. Open the competition URL above")
    print("    2. Log in as admin")
    print("    3. Click 'Run Competition', pick judge provider + model")
    print("    4. Watch the bracket fill in round by round")
    print("=" * 70)

    return 0 if skipped == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed a local AIUXTester for Vibecode Olympics competition testing.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8000",
        help="Local app base URL",
    )
    parser.add_argument(
        "--admin-email", default="admin@example.com",
        help="Admin account email",
    )
    parser.add_argument(
        "--admin-password", default="change-me",
        help="Admin account password",
    )
    parser.add_argument(
        "--provider", default="openai",
        help="LLM provider for session runs",
    )
    parser.add_argument(
        "--model", default="gpt-4o-mini",
        help="Model name for session runs",
    )
    parser.add_argument(
        "--max-steps", type=int, default=20,
        help="Max steps per session (higher = richer postmortems)",
    )
    parser.add_argument(
        "--poll-seconds", type=float, default=5.0,
        help="How often to poll each session for completion",
    )
    parser.add_argument(
        "--timeout-seconds", type=float, default=600.0,
        help="Per-session timeout before force-stopping",
    )
    return asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
