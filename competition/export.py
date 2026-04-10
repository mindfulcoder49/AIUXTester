"""
competition/export.py

Export a completed competition to the VibeCode Victory Games showcase site.

Usage (write to file):
    python -m competition.export <competition_id>
    python -m competition.export <competition_id> --output my_export.json
    python -m competition.export <competition_id> --no-screenshots   # smaller payload

Usage (POST directly to the Victory Games site):
    python -m competition.export <competition_id> --post https://yoursite.com/admin/victory-games/import --api-key SECRET

List available competitions:
    python -m competition.export --list
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import queries
from database.db import init_db, open_db

logger = logging.getLogger("aiuxtester.competition.export")


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_entry_ids(value) -> list[int]:
    if isinstance(value, list):
        return [int(item) for item in value if isinstance(item, (int, float))]
    try:
        parsed = json.loads(value or "[]")
        return [int(item) for item in parsed if isinstance(item, (int, float))]
    except Exception:
        return []


def _safe_json(value):
    """Coerce a stored JSON string or raw value to a Python object."""
    if value is None:
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _to_bytes(value) -> bytes | None:
    """Convert DB image_data (bytes / bytearray / memoryview) to bytes."""
    if value is None:
        return None
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


def _derive_placements(
    entries: list[dict],
    runs: list[dict],
    matches: list[dict],
) -> dict[int, int | None]:
    """
    Derive 1st/2nd/3rd placements via majority vote across all completed runs.

    - 1st:  entry that won the champion slot in the most completed runs
    - 2nd:  entry most often in the final match as a loser (excluding champion)
    - 3rd:  entry most often in the semifinal match as a loser (excluding 1st/2nd)
    - None: everyone else (participant)
    """
    entry_ids = {e["id"] for e in entries}
    completed_runs = [
        r for r in runs
        if r.get("status") == "complete" and r.get("champion_entry_id")
    ]

    # Group matches by run_id
    matches_by_run: dict[int, list[dict]] = {}
    for m in matches:
        rid = m.get("run_id")
        if rid is not None:
            matches_by_run.setdefault(int(rid), []).append(m)

    champion_counts: Counter[int] = Counter(
        r["champion_entry_id"] for r in completed_runs
    )
    finals_loser_counts: Counter[int] = Counter()
    semi_loser_counts: Counter[int] = Counter()

    for run in completed_runs:
        run_matches = matches_by_run.get(int(run["id"]), [])
        if not run_matches:
            continue
        max_round = max(m["round_number"] for m in run_matches)

        for m in run_matches:
            if m["round_number"] == max_round:
                winner_id = m.get("winner_entry_id")
                for eid in _parse_entry_ids(m.get("entry_ids")):
                    if eid != winner_id:
                        finals_loser_counts[eid] += 1
            elif max_round >= 2 and m["round_number"] == max_round - 1:
                winner_id = m.get("winner_entry_id")
                for eid in _parse_entry_ids(m.get("entry_ids")):
                    if eid != winner_id:
                        semi_loser_counts[eid] += 1

    placements: dict[int, int | None] = {eid: None for eid in entry_ids}

    if champion_counts:
        placements[champion_counts.most_common(1)[0][0]] = 1

    unplaced = {eid for eid, p in placements.items() if p is None}
    ranked_2nd = [(eid, c) for eid, c in finals_loser_counts.most_common() if eid in unplaced]
    if ranked_2nd:
        placements[ranked_2nd[0][0]] = 2

    unplaced = {eid for eid, p in placements.items() if p is None}
    ranked_3rd = [(eid, c) for eid, c in semi_loser_counts.most_common() if eid in unplaced]
    if ranked_3rd:
        placements[ranked_3rd[0][0]] = 3

    return placements


# ── core export builder ───────────────────────────────────────────────────────

async def build_export_payload(
    competition_id: str,
    *,
    include_screenshots: bool = True,
) -> dict:
    """
    Build the full export JSON payload for a competition.

    Returns a dict with keys:
        export_version, exported_at, competition, recap, runs, entries
    """
    async with open_db() as db:
        competition = await queries.get_competition(db, competition_id)
        if not competition:
            raise ValueError(f"Competition '{competition_id}' not found")
        competition = dict(competition)

        entries_raw = [dict(e) for e in await queries.list_competition_entries(db, competition_id)]
        runs_raw    = [dict(r) for r in await queries.list_competition_runs(db, competition_id)]
        matches_raw = [dict(m) for m in await queries.list_competition_matches(db, competition_id)]
        recap_raw   = await queries.get_latest_competition_recap(db, competition_id)
        recap       = dict(recap_raw) if recap_raw else None

        # Parse recap entry_profiles JSON
        entry_profiles: dict[str, dict] = {}
        if recap:
            try:
                entry_profiles = json.loads(recap.get("entry_profiles") or "{}")
            except Exception:
                entry_profiles = {}

        placements = _derive_placements(entries_raw, runs_raw, matches_raw)

        # held_at = earliest completed_at across completed runs
        held_at = min(
            (r["completed_at"] for r in runs_raw if r.get("status") == "complete" and r.get("completed_at")),
            default=None,
        )

        # Build runs with nested matches
        matches_by_run: dict[int, list[dict]] = {}
        for m in matches_raw:
            rid = m.get("run_id")
            if rid is not None:
                matches_by_run.setdefault(int(rid), []).append(m)

        export_runs = []
        for run in runs_raw:
            run_matches = sorted(
                matches_by_run.get(int(run["id"]), []),
                key=lambda x: (x["round_number"], x["match_number"]),
            )
            export_runs.append({
                "external_id":      run["id"],
                "run_number":       run["run_number"],
                "status":           run["status"],
                "champion_entry_id": run.get("champion_entry_id"),
                "pairing_strategy": run.get("pairing_strategy"),
                "progression_mode": run.get("progression_mode"),
                "provider":         run.get("provider"),
                "model":            run.get("model"),
                "completed_at":     run.get("completed_at"),
                "created_at":       run.get("created_at"),
                "matches": [
                    {
                        "external_id":    m["id"],
                        "round_number":   m["round_number"],
                        "match_number":   m["match_number"],
                        "entry_ids":      _parse_entry_ids(m.get("entry_ids")),
                        "winner_entry_id": m.get("winner_entry_id"),
                        "judge_reasoning": m.get("judge_reasoning"),
                        "status":         m.get("status"),
                    }
                    for m in run_matches
                ],
            })

        # Build entries with session, postmortem, and steps
        export_entries = []
        for entry in entries_raw:
            session    = dict(await queries.get_session(db, entry["session_id"]) or {})
            postmortem = dict(await queries.get_postmortem(db, entry["session_id"]) or {})
            user       = dict(await queries.get_user_by_id(db, entry["user_id"]) or {})
            actions    = [dict(a) for a in await queries.list_actions(db, entry["session_id"])]

            # Load screenshots and index by ID
            screenshots_by_id: dict[int, dict] = {}
            if include_screenshots:
                raw_shots = await queries.list_screenshots(db, entry["session_id"])
                for sc in raw_shots:
                    sc = dict(sc)
                    img_bytes = _to_bytes(sc.get("image_data"))
                    sc["image_b64"] = base64.b64encode(img_bytes).decode("ascii") if img_bytes else None
                    sc.pop("image_data", None)
                    screenshots_by_id[sc["id"]] = sc

            # Build steps: one per action, joined with its screenshot
            steps = []
            for action in actions:
                sc = screenshots_by_id.get(action["screenshot_id"]) if action.get("screenshot_id") else None
                steps.append({
                    "step_number":   action["step_number"],
                    "action_type":   action["action_type"],
                    "action_params": _safe_json(action.get("action_params")),
                    "intent":        action.get("intent"),
                    "reasoning":     action.get("reasoning"),
                    "action_result": action.get("action_result"),
                    "success":       bool(action.get("success", True)),
                    "error_message": action.get("error_message"),
                    "page_url":      sc["url"] if sc else None,
                    "screenshot_b64": sc["image_b64"] if sc else None,
                    "timestamp":     action.get("timestamp"),
                })

            export_entries.append({
                "external_id":      entry["id"],
                "external_user_id": entry["user_id"],
                "user_email":       user.get("email"),
                "note":             entry.get("note"),
                "submitted_at":     entry.get("submitted_at"),
                "placement":        placements.get(entry["id"]),
                "entry_profile":    entry_profiles.get(str(entry["id"])) or {},
                "session": {
                    "external_id": session.get("id"),
                    "goal":        session.get("goal"),
                    "start_url":   session.get("start_url"),
                    "mode":        session.get("mode"),
                    "provider":    session.get("provider"),
                    "model":       session.get("model"),
                    "status":      session.get("status"),
                    "end_reason":  session.get("end_reason"),
                    "created_at":  session.get("created_at"),
                },
                "postmortem": {
                    "run_analysis":    postmortem.get("run_analysis"),
                    "html_analysis":   postmortem.get("html_analysis"),
                    "recommendations": postmortem.get("recommendations"),
                } if postmortem else None,
                "steps": steps,
            })

    return {
        "export_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "competition": {
            "external_id": competition["id"],
            "name":        competition["name"],
            "description": competition.get("description"),
            "status":      competition["status"],
            "held_at":     held_at,
            "created_at":  competition.get("created_at"),
            "updated_at":  competition.get("updated_at"),
        },
        "recap": {
            "overall_narrative": recap.get("overall_narrative"),
            "provider":          recap.get("provider"),
            "model":             recap.get("model"),
            "generated_at":      recap.get("generated_at"),
        } if recap else None,
        "runs":    export_runs,
        "entries": export_entries,
    }


# ── summary helper ────────────────────────────────────────────────────────────

def _print_summary(payload: dict, output_path: str | None = None) -> None:
    comp    = payload["competition"]
    entries = payload.get("entries", [])
    runs    = payload.get("runs", [])

    total_steps       = sum(len(e.get("steps", [])) for e in entries)
    total_screenshots = sum(1 for e in entries for s in e.get("steps", []) if s.get("screenshot_b64"))
    total_matches     = sum(len(r.get("matches", [])) for r in runs)

    placement_labels = {1: "1st", 2: "2nd", 3: "3rd"}
    placement_map = {e["placement"]: e for e in entries if e.get("placement")}

    print(f"\nExport summary for: {comp['name']!r}")
    print(f"  Competition ID : {comp['external_id']}")
    print(f"  Status         : {comp['status']}")
    print(f"  Held at        : {comp.get('held_at') or 'unknown'}")
    print(f"  Entries        : {len(entries)}")
    print(f"  Runs           : {len(runs)} ({sum(1 for r in runs if r['status'] == 'complete')} complete)")
    print(f"  Matches        : {total_matches}")
    print(f"  Steps          : {total_steps}")
    print(f"  Screenshots    : {total_screenshots}")
    print(f"  Recap          : {'yes' if payload.get('recap') else 'no'}")
    print()
    for place in (1, 2, 3):
        if place in placement_map:
            e = placement_map[place]
            url = (e.get("session") or {}).get("start_url") or e["external_user_id"]
            print(f"  {placement_labels[place]} place: {url}")
    print()
    if output_path:
        size_mb = Path(output_path).stat().st_size / 1024 / 1024
        print(f"  Output file: {output_path} ({size_mb:.1f} MB)")


# ── CLI ───────────────────────────────────────────────────────────────────────

async def _cmd_list() -> None:
    await init_db()
    async with open_db() as db:
        comps = await queries.list_competitions(db)
        if not comps:
            print("No competitions found.")
            return
        print(f"{'ID':36}  {'Status':10}  {'Entries':7}  {'Runs':5}  Name")
        print("-" * 80)
        for c in comps:
            c = dict(c)
            entries = list(await queries.list_competition_entries(db, c["id"]))
            runs    = list(await queries.list_competition_runs(db, c["id"]))
            print(f"{c['id']}  {c['status']:10}  {len(entries):7}  {len(runs):5}  {c['name']}")


async def _cmd_export(args: argparse.Namespace) -> None:
    await init_db()
    logger.info("Building export for competition: %s", args.competition_id)

    payload = await build_export_payload(
        args.competition_id,
        include_screenshots=not args.no_screenshots,
    )

    if args.post:
        import urllib.request
        body = json.dumps(payload).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if args.api_key:
            headers["Authorization"] = f"Bearer {args.api_key}"
        req = urllib.request.Request(args.post, data=body, headers=headers, method="POST")
        logger.info("POSTing %d bytes to %s", len(body), args.post)
        with urllib.request.urlopen(req) as resp:
            response_body = resp.read().decode("utf-8")
            logger.info("Response %d: %s", resp.status, response_body[:500])
        _print_summary(payload)
    else:
        output_path = args.output or f"{args.competition_id}_export.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        _print_summary(payload, output_path)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Export a completed competition to the Vibecode Olympics showcase site.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "competition_id",
        nargs="?",
        help="Competition ID to export (omit if using --list)",
    )
    parser.add_argument("--list", action="store_true", help="List all competitions and exit")
    parser.add_argument("--output", "-o", metavar="FILE", help="Output JSON file (default: <id>_export.json)")
    parser.add_argument("--post", metavar="URL", help="POST the export to this URL instead of writing a file")
    parser.add_argument("--api-key", metavar="KEY", help="Bearer token for --post authentication")
    parser.add_argument(
        "--no-screenshots",
        action="store_true",
        help="Omit screenshot base64 data (much smaller payload, step metadata still included)",
    )
    args = parser.parse_args()

    if args.list:
        asyncio.run(_cmd_list())
        return

    if not args.competition_id:
        parser.error("competition_id is required (or use --list to see available competitions)")

    asyncio.run(_cmd_export(args))


if __name__ == "__main__":
    main()
