#!/usr/bin/env python3
"""
manage.py — AIUXTester admin CLI

Reads BASE_URL, ADMIN_EMAIL, and ADMIN_PASSWORD from the local .env by default.
All commands authenticate as admin automatically.

Usage:
  python manage.py users
  python manage.py sessions [--status failed|completed|running|stopped|loop_detected] [--limit N] [--search text]
  python manage.py session <session_id>
  python manage.py memory <session_id>
  python manage.py logs <session_id> [--level error|warning|info]
  python manage.py competitions
  python manage.py queue

Global options (override .env defaults):
  --base-url   http://127.0.0.1:8001
  --email      admin@example.com
  --password   password
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

DEFAULT_BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8001")
DEFAULT_EMAIL    = os.getenv("ADMIN_EMAIL", "admin@example.com")
DEFAULT_PASSWORD = os.getenv("ADMIN_PASSWORD", "password")

# ── ANSI helpers ──────────────────────────────────────────────────────────────

_USE_COLOR = sys.stdout.isatty()

def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

def bold(t):   return _c(t, "1")
def muted(t):  return _c(t, "2")
def ok(t):     return _c(t, "32")
def err(t):    return _c(t, "31")
def warn(t):   return _c(t, "33")

STATUS_COLOR = {
    "completed":    ok,
    "running":      lambda t: _c(t, "34"),
    "failed":       err,
    "stopped":      muted,
    "loop_detected": warn,
}

def colored_status(s: str) -> str:
    fn = STATUS_COLOR.get(s, lambda t: t)
    return fn(s)


# ── HTTP client ───────────────────────────────────────────────────────────────

class AdminClient:
    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url.rstrip("/")
        self._email = email
        self._password = password
        self._token: Optional[str] = None

    def _authenticate(self) -> None:
        with httpx.Client(base_url=self.base_url, timeout=15) as c:
            try:
                r = c.post("/auth/register", json={"email": self._email, "password": self._password})
                r.raise_for_status()
                self._token = r.json()["access_token"]
            except httpx.HTTPStatusError:
                r = c.post("/auth/login", json={"email": self._email, "password": self._password})
                r.raise_for_status()
                self._token = r.json()["access_token"]

    def get(self, path: str, **kwargs):
        if not self._token:
            self._authenticate()
        with httpx.Client(base_url=self.base_url, timeout=30) as c:
            r = c.get(path, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)
            r.raise_for_status()
            return r.json()


# ── Formatters ────────────────────────────────────────────────────────────────

def _hr(char: str = "─", width: int = 72) -> str:
    return muted(char * width)

def _table(rows: list[dict], columns: list[tuple[str, str, int]]) -> None:
    """Print a simple fixed-width table.
    columns = [(header, key, width), ...]
    """
    header = "  ".join(bold(h.ljust(w)) for h, _, w in columns)
    print(header)
    print(_hr("─", sum(w + 2 for _, _, w in columns)))
    for row in rows:
        cells = []
        for _, key, width in columns:
            val = str(row.get(key) or "")
            cells.append(val[:width].ljust(width))
        print("  ".join(cells))


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_users(client: AdminClient, args) -> None:
    users = client.get("/admin/users")
    print(f"\n{bold('Users')} ({len(users)})\n")
    _table(users, [
        ("Email",      "email",      36),
        ("Role",       "role",        6),
        ("Tier",       "tier",        6),
        ("Joined",     "created_at", 10),
    ])
    print()


def cmd_sessions(client: AdminClient, args) -> None:
    params: dict = {"limit": args.limit}
    if args.status:
        params["status"] = args.status
    sessions = client.get("/admin/sessions", params=params)

    if args.search:
        q = args.search.lower()
        sessions = [s for s in sessions if
                    q in (s.get("email") or "").lower() or
                    q in (s.get("start_url") or "").lower() or
                    q in (s.get("goal") or "").lower()]

    print(f"\n{bold('Sessions')} ({len(sessions)})\n")
    for s in sessions:
        ts = (s.get("created_at") or "")[:16].replace("T", " ")
        status = colored_status(s.get("status", ""))
        actions = s.get("action_count", 0)
        print(f"  {muted(s['id'][:8])}  {status:<22}  "
              f"{str(actions).rjust(3)} actions  "
              f"{(s.get('email') or ''):<30}  "
              f"{(s.get('start_url') or '')[:50]}")
        if s.get("goal"):
            print(f"           {muted((s['goal'])[:70])}")
    print()


def cmd_session(client: AdminClient, args) -> None:
    data = client.get(f"/sessions/{args.session_id}")
    s = data["session"]
    actions = data.get("actions", [])
    logs = data.get("logs", [])

    print(f"\n{bold('Session')} {s['id']}")
    print(_hr())
    print(f"  Goal      {s.get('goal')}")
    print(f"  URL       {s.get('start_url')}")
    print(f"  Status    {colored_status(s.get('status', ''))}")
    if s.get("end_reason"):
        print(f"  End       {s['end_reason']}")
    print(f"  Provider  {s.get('provider')} / {s.get('model')}")
    print(f"  Mode      {s.get('mode')}")
    print(f"  Created   {s.get('created_at')}")
    print()

    if actions:
        print(f"{bold('Actions')} ({len(actions)})")
        for a in actions:
            res = f" → {a.get('action_result')}" if a.get("action_result") else ""
            success = ok("✓") if a.get("success") else err("✗")
            print(f"  {success} step {str(a['step_number']).rjust(3)}  "
                  f"{a.get('action_type', ''):<14}  "
                  f"{muted((a.get('intent') or '')[:60])}{res}")
        print()

    error_logs = [l for l in logs if l.get("level") == "error"]
    if error_logs:
        print(f"{bold('Errors')} ({len(error_logs)})")
        for l in error_logs:
            print(f"  {err('✗')} step {str(l.get('step_number') or '-').rjust(3)}  {l.get('message')}")
            if l.get("details"):
                print(f"    {muted(l['details'][:120])}")
        print()


def cmd_memory(client: AdminClient, args) -> None:
    memory = client.get(f"/admin/sessions/{args.session_id}/memory")
    print(f"\n{bold('Memory')} — session {args.session_id[:8]}…\n")
    if not memory:
        print(f"  {muted('(empty)')}")
    else:
        for key, val in memory.items():
            print(f"  {bold(key)}")
            print(f"    {val}")
            print()


def cmd_logs(client: AdminClient, args) -> None:
    logs = client.get(f"/sessions/{args.session_id}/logs")
    if args.level:
        logs = [l for l in logs if (l.get("level") or "info") == args.level]
    print(f"\n{bold('Logs')} — session {args.session_id[:8]}… ({len(logs)} entries)\n")
    level_fn = {"error": err, "warning": warn, "info": lambda t: t}
    for l in logs:
        lvl = l.get("level") or "info"
        fn  = level_fn.get(lvl, lambda t: t)
        step = str(l.get("step_number") or "-").rjust(3)
        print(f"  {fn(lvl.upper()[:4]):<12} step {step}  {l.get('message', '')}")
        if l.get("details"):
            details = l["details"]
            if len(details) > 200:
                details = details[:200] + "…"
            print(f"    {muted(details)}")


def cmd_competitions(client: AdminClient, args) -> None:
    comps = client.get("/competitions")
    print(f"\n{bold('Competitions')} ({len(comps)})\n")
    for c in comps:
        entries = c.get("entry_count", 0)
        print(f"  {c['id'][:8]}…  {colored_status(c.get('status',''))}  "
              f"{str(entries).rjust(2)} entries  {bold(c['name'])}")
        if c.get("description"):
            print(f"           {muted(c['description'][:70])}")
    print()


def cmd_queue(client: AdminClient, args) -> None:
    q = client.get("/admin/queue")
    print(f"\n{bold('Queue stats')}\n")
    if not q.get("available"):
        print(f"  {err('Redis unavailable')}  {q.get('error', '')}")
        return
    print(f"  Queued (waiting)  {q.get('queued', 0)}")
    print(f"  Active (running)  {q.get('active', 0)}")
    failed = q.get("failed", 0)
    print(f"  Failed            {err(str(failed)) if failed else '0'}")
    print(f"  Finished          {q.get('finished', 0)}")
    print(f"  Deferred          {q.get('deferred', 0)}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def _global_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--email",    default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)


def main() -> int:
    root = argparse.ArgumentParser(
        description="AIUXTester admin CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _global_args(root)
    sub = root.add_subparsers(dest="command")

    sub.add_parser("users", help="List all users")

    p_sessions = sub.add_parser("sessions", help="List sessions")
    p_sessions.add_argument("--status", default=None,
        choices=["running", "completed", "failed", "stopped", "loop_detected"])
    p_sessions.add_argument("--limit", type=int, default=50)
    p_sessions.add_argument("--search", default=None, help="Filter by email, URL, or goal")

    p_session = sub.add_parser("session", help="Full detail for one session")
    p_session.add_argument("session_id")

    p_memory = sub.add_parser("memory", help="Show agent memory for a session")
    p_memory.add_argument("session_id")

    p_logs = sub.add_parser("logs", help="Show run logs for a session")
    p_logs.add_argument("session_id")
    p_logs.add_argument("--level", default=None, choices=["error", "warning", "info"])

    sub.add_parser("competitions", help="List competitions")
    sub.add_parser("queue", help="Show Redis queue stats")

    args = root.parse_args()
    if not args.command:
        root.print_help()
        return 0

    client = AdminClient(args.base_url, args.email, args.password)

    try:
        dispatch = {
            "users":        cmd_users,
            "sessions":     cmd_sessions,
            "session":      cmd_session,
            "memory":       cmd_memory,
            "logs":         cmd_logs,
            "competitions": cmd_competitions,
            "queue":        cmd_queue,
        }
        dispatch[args.command](client, args)
    except httpx.HTTPStatusError as e:
        print(err(f"API error {e.response.status_code}: {e.response.text}"), file=sys.stderr)
        return 1
    except httpx.ConnectError:
        print(err(f"Cannot connect to {args.base_url}"), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
