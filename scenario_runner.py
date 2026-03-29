from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Iterable, Sequence

from scenarios import ExpandedScenario, expand_scenarios, load_scenario_bank, resolve_bank_path


DEFAULT_REPORT_DIR = Path("reports/scenario_runs")
TERMINAL_STATUSES = {"completed", "failed", "stopped", "loop_detected"}


@dataclass(frozen=True)
class StructuredSummary:
    verdict: str | None
    findings: tuple[str, ...]
    next_step: str | None


@dataclass(frozen=True)
class ScenarioRunResult:
    run_id: str
    scenario_id: str
    title: str
    entry_url: str
    surface: str
    device: str
    tags: tuple[str, ...]
    session_id: str
    status: str
    end_reason: str | None
    verdict: str | None
    findings: tuple[str, ...]
    next_step: str | None
    action_count: int
    started_at: str
    completed_at: str
    duration_seconds: float
    postmortem_id: int | None = None


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def available_banks() -> list[str]:
    scenario_dir = resolve_bank_path("publicdatawatch").parent
    return sorted(path.stem for path in scenario_dir.glob("*.json"))


def _month_rotation_seed(for_date: date) -> str:
    return f"{for_date.year:04d}-{for_date.month:02d}"


def select_daily_scenarios(
    scenarios: Sequence[ExpandedScenario],
    *,
    for_date: date,
    count: int,
    include_tags: Iterable[str] | None = None,
    exclude_tags: Iterable[str] | None = None,
    offset: int = 0,
) -> list[ExpandedScenario]:
    include = set(include_tags or [])
    exclude = set(exclude_tags or [])

    filtered = [
        scenario
        for scenario in scenarios
        if (not include or include.issubset(set(scenario.tags)))
        and not (exclude and exclude.intersection(scenario.tags))
    ]
    if not filtered:
        return []

    seed = _month_rotation_seed(for_date)
    ordered = sorted(
        filtered,
        key=lambda scenario: hashlib.sha256(f"{seed}:{scenario.run_id}".encode("utf-8")).hexdigest(),
    )

    actual_count = min(count, len(ordered))
    start = ((for_date.day - 1 + offset) * actual_count) % len(ordered)
    window = []
    for idx in range(actual_count):
        window.append(ordered[(start + idx) % len(ordered)])
    return window


def parse_structured_summary(text: str | None) -> StructuredSummary:
    if not text:
        return StructuredSummary(verdict=None, findings=(), next_step=None)

    verdict: str | None = None
    findings: list[str] = []
    next_step: str | None = None
    mode: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Verdict:"):
            verdict = line.split(":", 1)[1].strip() or None
            mode = None
            continue
        if line.startswith("Findings:"):
            mode = "findings"
            continue
        if line.startswith("Next step:"):
            next_step = line.split(":", 1)[1].strip() or None
            mode = None
            continue
        if mode == "findings" and line.startswith("- "):
            findings.append(line[2:].strip())

    return StructuredSummary(
        verdict=verdict,
        findings=tuple(findings),
        next_step=next_step,
    )


def render_markdown_report(
    *,
    bank_name: str,
    for_date: date,
    results: Sequence[ScenarioRunResult],
    selected_count: int,
) -> str:
    status_counts: dict[str, int] = {}
    surface_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
        surface_counts[result.surface] = surface_counts.get(result.surface, 0) + 1

    lines = [
        f"# {bank_name} Scenario Run Report",
        "",
        f"- date: `{for_date.isoformat()}`",
        f"- selected scenarios: `{selected_count}`",
        f"- completed results: `{len(results)}`",
        "",
        "## Status Summary",
        "",
    ]

    if status_counts:
        for status, count in sorted(status_counts.items()):
            lines.append(f"- `{status}`: `{count}`")
    else:
        lines.append("- no runs recorded")

    lines.extend(["", "## Surface Summary", ""])
    if surface_counts:
        for surface, count in sorted(surface_counts.items()):
            lines.append(f"- `{surface}`: `{count}`")
    else:
        lines.append("- no surfaces recorded")

    lines.extend(["", "## Runs", ""])
    for result in results:
        lines.append(f"### {result.title}")
        lines.append(f"- run id: `{result.run_id}`")
        lines.append(f"- session id: `{result.session_id}`")
        lines.append(f"- status: `{result.status}`")
        lines.append(f"- device: `{result.device}`")
        lines.append(f"- surface: `{result.surface}`")
        lines.append(f"- tags: `{', '.join(result.tags)}`")
        if result.verdict:
            lines.append(f"- verdict: {result.verdict}")
        if result.findings:
            lines.append("- findings:")
            for finding in result.findings:
                lines.append(f"  - {finding}")
        if result.next_step:
            lines.append(f"- next step: {result.next_step}")
        if result.end_reason and not result.verdict:
            lines.append(f"- end reason: {result.end_reason}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


async def _build_local_client():
    import config
    import httpx
    from ui.app import app

    original_queue_mode = config.QUEUE_MODE
    config.QUEUE_MODE = "inline"
    await app.router.startup()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://scenario-runner")
    return client, app, config, original_queue_mode


class LocalScenarioBatchRunner:
    def __init__(
        self,
        *,
        email: str,
        password: str,
        model: str,
        max_steps: int,
        poll_seconds: float,
        timeout_seconds: float,
    ):
        self.email = email
        self.password = password
        self.model = model
        self.max_steps = max_steps
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self._client = None
        self._app = None
        self._config = None
        self._original_queue_mode = None
        self._token = ""

    async def __aenter__(self):
        client, app, config, original_queue_mode = await _build_local_client()
        self._client = client
        self._app = app
        self._config = config
        self._original_queue_mode = original_queue_mode
        await self._authenticate()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client is not None:
            await self._client.aclose()
        if self._app is not None:
            await self._app.router.shutdown()
        if self._config is not None and self._original_queue_mode is not None:
            self._config.QUEUE_MODE = self._original_queue_mode

    async def _request(self, method: str, path: str, *, json_body: dict | None = None):
        assert self._client is not None
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        response = await self._client.request(method, path, json=json_body, headers=headers)
        response.raise_for_status()
        return response.json()

    async def _authenticate(self) -> None:
        try:
            payload = await self._request(
                "POST",
                "/auth/register",
                json_body={"email": self.email, "password": self.password},
            )
        except Exception:
            payload = await self._request(
                "POST",
                "/auth/login",
                json_body={"email": self.email, "password": self.password},
            )
        self._token = payload["access_token"]

    async def run_scenario(self, scenario: ExpandedScenario) -> ScenarioRunResult:
        start_ts = datetime.now(UTC)
        session_payload = {
            "goal": scenario.goal,
            "start_url": scenario.entry_url,
            "provider": "openai",
            "model": self.model,
            "config": {
                "mode": scenario.device,
                "max_steps": self.max_steps,
                "stop_on_first_error": False,
            },
        }
        created = await self._request("POST", "/sessions", json_body=session_payload)
        session_id = created["session_id"]

        detail = None
        timeout_at = asyncio.get_event_loop().time() + self.timeout_seconds
        while asyncio.get_event_loop().time() < timeout_at:
            detail = await self._request("GET", f"/sessions/{session_id}")
            status = detail["session"]["status"]
            if status in TERMINAL_STATUSES:
                break
            await asyncio.sleep(self.poll_seconds)

        if detail is None:
            raise RuntimeError("Session detail missing after scenario run")

        if detail["session"]["status"] not in TERMINAL_STATUSES:
            await self._request("POST", f"/sessions/{session_id}/stop")
            detail = await self._request("GET", f"/sessions/{session_id}")

        postmortem = await self._request("GET", f"/sessions/{session_id}/postmortem")
        summary = parse_structured_summary(detail["session"].get("end_reason"))
        end_ts = datetime.now(UTC)

        return ScenarioRunResult(
            run_id=scenario.run_id,
            scenario_id=scenario.scenario_id,
            title=scenario.title,
            entry_url=scenario.entry_url,
            surface=scenario.surface,
            device=scenario.device,
            tags=tuple(scenario.tags),
            session_id=session_id,
            status=detail["session"]["status"],
            end_reason=detail["session"].get("end_reason"),
            verdict=summary.verdict,
            findings=summary.findings,
            next_step=summary.next_step,
            action_count=len(detail["actions"]),
            started_at=start_ts.isoformat(),
            completed_at=end_ts.isoformat(),
            duration_seconds=round((end_ts - start_ts).total_seconds(), 2),
            postmortem_id=(postmortem or {}).get("id") if isinstance(postmortem, dict) else None,
        )


async def run_daily_batch(
    *,
    bank_name: str,
    bank_path: str,
    for_date: date,
    count: int,
    include_tags: Sequence[str],
    exclude_tags: Sequence[str],
    report_dir: Path,
    model: str,
    max_steps: int,
    poll_seconds: float,
    timeout_seconds: float,
    email: str,
    password: str,
) -> dict[str, object]:
    scenarios = expand_scenarios(load_scenario_bank(bank_path))
    selected = select_daily_scenarios(
        scenarios,
        for_date=for_date,
        count=count,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
    )

    results: list[ScenarioRunResult] = []
    async with LocalScenarioBatchRunner(
        email=email,
        password=password,
        model=model,
        max_steps=max_steps,
        poll_seconds=poll_seconds,
        timeout_seconds=timeout_seconds,
    ) as runner:
        for scenario in selected:
            results.append(await runner.run_scenario(scenario))

    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{for_date.isoformat()}-{bank_name}.json"
    md_path = report_dir / f"{for_date.isoformat()}-{bank_name}.md"

    payload = {
        "bank": bank_name,
        "date": for_date.isoformat(),
        "selected_count": len(selected),
        "results": [asdict(result) for result in results],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        render_markdown_report(
            bank_name=bank_name,
            for_date=for_date,
            results=results,
            selected_count=len(selected),
        ),
        encoding="utf-8",
    )

    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "selected_count": len(selected),
        "results": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run daily AIUXTester scenario batches.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-banks", help="List bundled scenario banks.")

    preview = subparsers.add_parser("preview", help="Preview the daily scenario selection.")
    preview.add_argument("--bank", default="publicdatawatch")
    preview.add_argument("--date", default=date.today().isoformat())
    preview.add_argument("--count", type=int, default=6)
    preview.add_argument("--include-tag", action="append", default=[])
    preview.add_argument("--exclude-tag", action="append", default=[])

    run_daily = subparsers.add_parser("run-daily", help="Run the daily scenario batch.")
    run_daily.add_argument("--bank", default="publicdatawatch")
    run_daily.add_argument("--date", default=date.today().isoformat())
    run_daily.add_argument("--count", type=int, default=6)
    run_daily.add_argument("--include-tag", action="append", default=[])
    run_daily.add_argument("--exclude-tag", action="append", default=[])
    run_daily.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    run_daily.add_argument("--model", default="gpt-5-mini")
    run_daily.add_argument("--max-steps", type=int, default=8)
    run_daily.add_argument("--poll-seconds", type=float, default=5.0)
    run_daily.add_argument("--timeout-seconds", type=float, default=180.0)
    run_daily.add_argument("--email", default="scenario-runner@example.com")
    run_daily.add_argument("--password", default="password")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    if args.command == "list-banks":
        for bank in available_banks():
            print(bank)
        return 0

    bank_path = resolve_bank_path(args.bank)
    bank_name = Path(bank_path).stem
    for_date = date.fromisoformat(args.date)

    if args.command == "preview":
        scenarios = expand_scenarios(load_scenario_bank(str(bank_path)))
        selected = select_daily_scenarios(
            scenarios,
            for_date=for_date,
            count=args.count,
            include_tags=args.include_tag,
            exclude_tags=args.exclude_tag,
        )
        for scenario in selected:
            print(
                json.dumps(
                    {
                        "run_id": scenario.run_id,
                        "title": scenario.title,
                        "device": scenario.device,
                        "surface": scenario.surface,
                        "tags": scenario.tags,
                        "entry_url": scenario.entry_url,
                    }
                )
            )
        return 0

    outcome = await run_daily_batch(
        bank_name=bank_name,
        bank_path=str(bank_path),
        for_date=for_date,
        count=args.count,
        include_tags=args.include_tag,
        exclude_tags=args.exclude_tag,
        report_dir=Path(args.report_dir),
        model=args.model,
        max_steps=args.max_steps,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
        email=args.email,
        password=args.password,
    )
    print(
        json.dumps(
            {
                "json_path": outcome["json_path"],
                "markdown_path": outcome["markdown_path"],
                "selected_count": outcome["selected_count"],
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
