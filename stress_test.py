#!/usr/bin/env python3
"""
stress_test.py — Submit N concurrent test sessions to a deployed AIUXTester instance.

Scale up workers first:
  fly scale count worker=20 --app aiuxtester

Run the stress test:
  python stress_test.py \\
    --base-url https://aiuxtester.fly.dev \\
    --email admin@example.com \\
    --password secret \\
    --count 20

Scale back down after:
  fly scale count worker=1 --app aiuxtester
"""
from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import httpx

from scenario_runner import select_daily_scenarios
from scenarios import expand_scenarios, load_scenario_bank, resolve_bank_path

TERMINAL_STATUSES = {"completed", "failed", "stopped", "loop_detected"}

STATUS_ICON = {
    "completed": "✓",
    "failed": "✗",
    "stopped": "◼",
    "loop_detected": "↻",
    "timeout": "⏱",
}


@dataclass
class SessionResult:
    index: int
    run_id: str
    title: str
    device: str
    session_id: str = ""
    status: str = "pending"
    action_count: int = 0
    _started: float = field(default_factory=time.monotonic, repr=False)
    _ended: Optional[float] = field(default=None, repr=False)
    error: Optional[str] = None

    @property
    def duration(self) -> Optional[float]:
        if self._ended is not None:
            return round(self._ended - self._started, 1)
        return None


class StressTestRunner:
    def __init__(
        self,
        *,
        base_url: str,
        email: str,
        password: str,
        provider: str,
        model: str,
        max_steps: int,
        stagger: float,
        poll_seconds: float,
        timeout_seconds: float,
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.provider = provider
        self.model = model
        self.max_steps = max_steps
        self.stagger = stagger
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self._token = ""
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        await self._authenticate()
        return self

    async def __aexit__(self, *_):
        if self._client:
            await self._client.aclose()

    async def _req(self, method: str, path: str, *, body=None):
        assert self._client is not None
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        resp = await self._client.request(method, path, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _authenticate(self) -> None:
        try:
            data = await self._req(
                "POST", "/auth/register",
                body={"email": self.email, "password": self.password},
            )
        except httpx.HTTPStatusError:
            data = await self._req(
                "POST", "/auth/login",
                body={"email": self.email, "password": self.password},
            )
        self._token = data["access_token"]

    async def _run_one(self, result: SessionResult, scenario, delay: float) -> None:
        if delay:
            await asyncio.sleep(delay)

        # Submit
        try:
            data = await self._req(
                "POST", "/sessions",
                body={
                    "goal": scenario.goal,
                    "start_url": scenario.entry_url,
                    "provider": self.provider,
                    "model": self.model,
                    "config": {
                        "mode": scenario.device,
                        "max_steps": self.max_steps,
                        "stop_on_first_error": False,
                    },
                },
            )
        except Exception as exc:
            result.status = "failed"
            result.error = f"submit error: {exc}"
            result._ended = time.monotonic()
            _print_progress(result)
            return

        result.session_id = data["session_id"]
        result._started = time.monotonic()
        _print_progress(result, submitted=True)

        # Poll
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(self.poll_seconds)
            try:
                data = await self._req("GET", f"/sessions/{result.session_id}")
                status = data["session"]["status"]
                if status in TERMINAL_STATUSES:
                    result.status = status
                    result.action_count = len(data.get("actions", []))
                    result._ended = time.monotonic()
                    _print_progress(result)
                    return
            except Exception as exc:
                result.error = str(exc)

        # Timed out
        result.status = "timeout"
        result._ended = time.monotonic()
        _print_progress(result)
        try:
            await self._req("POST", f"/sessions/{result.session_id}/stop")
        except Exception:
            pass

    async def run_all(self, scenarios) -> list[SessionResult]:
        results = [
            SessionResult(
                index=i,
                run_id=s.run_id,
                title=s.title,
                device=s.device,
            )
            for i, s in enumerate(scenarios)
        ]
        await asyncio.gather(
            *[
                self._run_one(result, scenario, delay=i * self.stagger)
                for i, (result, scenario) in enumerate(zip(results, scenarios))
            ],
            return_exceptions=True,
        )
        return results


def _print_progress(result: SessionResult, *, submitted: bool = False) -> None:
    tag = f"[{result.index + 1:02d}/{result.run_id}]"
    if submitted:
        print(f"  {tag} submitted  {result.title[:60]}")
    else:
        icon = STATUS_ICON.get(result.status, "?")
        dur = f"{result.duration}s" if result.duration is not None else "?"
        extra = f"{result.action_count} actions" if result.action_count else (result.error or "")
        print(f"  {tag} {icon} {result.status:<14} {dur:>7}  {extra}")


def _print_summary(results: list[SessionResult], wall_seconds: float) -> None:
    print("\n" + "=" * 72)
    print(f"  RESULTS  ({len(results)} sessions, wall time {wall_seconds:.1f}s)")
    print("=" * 72)

    col_w = 42
    print(f"  {'#':>2}  {'status':<14}  {'dur':>7}  {'act':>4}  title")
    print(f"  {'-'*2}  {'-'*14}  {'-'*7}  {'-'*4}  {'-'*col_w}")
    for r in results:
        icon = STATUS_ICON.get(r.status, "?")
        dur = f"{r.duration}s" if r.duration is not None else "—"
        title = r.title[:col_w]
        print(f"  {r.index+1:>2}  {icon} {r.status:<13}  {dur:>7}  {r.action_count:>4}  {title}")

    print()
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    for status, n in sorted(counts.items()):
        print(f"  {STATUS_ICON.get(status, '?')} {status}: {n}")

    durations = [r.duration for r in results if r.duration is not None]
    if durations:
        print(f"\n  min {min(durations):.1f}s  /  avg {sum(durations)/len(durations):.1f}s  /  max {max(durations):.1f}s")
    print("=" * 72)


async def async_main(args: argparse.Namespace) -> int:
    bank_path = resolve_bank_path(args.bank)
    scenarios_all = expand_scenarios(load_scenario_bank(str(bank_path)))
    selected = select_daily_scenarios(
        scenarios_all,
        for_date=date.today(),
        count=args.count,
    )

    if not selected:
        print("No scenarios selected — check bank name and count.")
        return 1

    if len(selected) < args.count:
        print(f"Warning: only {len(selected)} scenarios available (requested {args.count}).")

    print(f"\nStress test: {len(selected)} sessions → {args.base_url}")
    print(f"  model={args.model}  max_steps={args.max_steps}  stagger={args.stagger}s\n")

    async with StressTestRunner(
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        provider=args.provider,
        model=args.model,
        max_steps=args.max_steps,
        stagger=args.stagger,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
    ) as runner:
        wall_start = time.monotonic()
        results = await runner.run_all(selected)
        wall_time = time.monotonic() - wall_start

    _print_summary(results, wall_time)
    failed = sum(1 for r in results if r.status not in {"completed"})
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit N concurrent sessions to a deployed AIUXTester instance.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--base-url", required=True, help="Deployed app URL, e.g. https://aiuxtester.fly.dev")
    parser.add_argument("--email", required=True, help="Account email (created automatically if new)")
    parser.add_argument("--password", required=True, help="Account password")
    parser.add_argument("--count", type=int, default=20, help="Number of concurrent sessions")
    parser.add_argument("--bank", default="publicdatawatch", help="Scenario bank name")
    parser.add_argument("--provider", default="openai", help="LLM provider")
    parser.add_argument("--model", default="gpt-5-mini", help="Model name")
    parser.add_argument("--max-steps", type=int, default=6, help="Max steps per session")
    parser.add_argument(
        "--stagger", type=float, default=1.0,
        help="Seconds between each session submission (reduces LLM rate-limit spikes)",
    )
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="Polling interval")
    parser.add_argument("--timeout-seconds", type=float, default=600.0, help="Per-session timeout before force-stop")
    return asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
