"""Competition recap generator.

Synthesises per-entry match histories into AI-written profiles, then combines
them into a single tournament narrative. Entry profiles are generated in
parallel via asyncio.to_thread so the event loop is not blocked.
"""
from __future__ import annotations

import asyncio
import json
import logging

from pydantic import BaseModel

from agent.postmortem_graph import get_llm_client
from database import queries
from database.db import open_db

logger = logging.getLogger("aiuxtester.competition.recap")


class _EntryAnalysis(BaseModel):
    what_it_does: str        # What the app was built for (1-2 sentences)
    agent_limitations: str   # AI testing limitations that affected this entry
    human_verdict: str       # Whether it's a good app for real humans
    profile: str             # Competition performance summary


class _NarrativeOutput(BaseModel):
    narrative: str


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_entry_ids(value) -> list[int]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, int)]
    try:
        parsed = json.loads(value or "[]")
        return [item for item in parsed if isinstance(item, int)]
    except Exception:
        return []


def _entry_match_history(entry_id: int, matches: list[dict]) -> list[dict]:
    """Ordered list of matches an entry appeared in, with won/lost flag and run context."""
    history = []
    for match in matches:
        if entry_id not in _parse_entry_ids(match.get("entry_ids")):
            continue
        history.append({
            "run_id": match.get("run_id"),
            "round_number": match["round_number"],
            "won": match.get("winner_entry_id") == entry_id,
            "reasoning": (match.get("judge_reasoning") or "").strip(),
        })
    # Sort by run_id first so matches from the same run appear together
    history.sort(key=lambda m: (m["run_id"] or 0, m["round_number"]))
    return history


def _run_index_map(matches: list[dict]) -> dict:
    """Map run_id → 1-based run index in chronological order."""
    seen: dict[int, int] = {}
    for match in sorted(matches, key=lambda m: m.get("run_id") or 0):
        rid = match.get("run_id")
        if rid is not None and rid not in seen:
            seen[rid] = len(seen) + 1
    return seen


# ── sync LLM calls (run inside thread pool) ──────────────────────────────────

def _generate_entry_profile(
    *,
    entry: dict,
    match_history: list[dict],
    run_index: dict,
    provider: str,
    model: str,
) -> dict:
    goal = (entry.get("goal") or "")[:600]
    url = entry.get("start_url") or entry.get("session_id", "unknown")

    if not match_history:
        return {
            "what_it_does": f"An app at {url}. No match history recorded.",
            "agent_limitations": "The AI testing agent had no recorded interactions with this entry.",
            "human_verdict": "Insufficient data to assess human usability.",
            "profile": "This entry did not appear in any recorded matches.",
        }

    history_lines = [
        f'[Run {run_index.get(item["run_id"], "?")} · Round {item["round_number"]} — {"Won" if item["won"] else "Lost"}] "{item["reasoning"]}"'
        for item in match_history[:24]  # cap to avoid token overflow
    ]
    num_runs = len(set(item["run_id"] for item in match_history))

    system_prompt = (
        "You are writing a thoughtful showcase profile for an app that competed in an AI UX testing tournament. "
        "Your job is to celebrate what was built, give honest technical analysis, and help readers "
        "understand how AI testing agents differ from human users. "
        "Be specific, insightful, and fair. Avoid generic filler. "
        "Respond with JSON only."
    )
    user_prompt = (
        f"App URL: {url}\n"
        f"Testing goal given to the AI agent: {goal}\n\n"
        f"AI judge observations across {len(history_lines)} matches in {num_runs} independent bracket runs:\n"
        + "\n".join(history_lines)
        + "\n\n"
        "Provide four short analyses:\n\n"
        "1. what_it_does (2 sentences): What was this app built for? What problem or use case does it address?\n\n"
        "2. agent_limitations (2 sentences): What specific limitations of the AI testing agent affected "
        "how this app was evaluated? Consider things like: auth walls the agent couldn't bypass, "
        "complex UI patterns the agent struggled with, specialized domain knowledge required, "
        "or cases where the agent succeeded easily on tasks that might challenge real users.\n\n"
        "3. human_verdict (2 sentences): Setting AI testing aside — is this a good app for real human "
        "users? What would humans appreciate that the AI missed, or what real UX issues exist?\n\n"
        "4. profile (2-3 sentences): How did it perform in the competition brackets and why? "
        "What consistently helped or hurt it across runs?\n\n"
        '{"what_it_does": "...", "agent_limitations": "...", "human_verdict": "...", "profile": "..."}'
    )

    llm = get_llm_client(provider)
    result = llm.generate_action(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        images=[],
        schema=_EntryAnalysis,
        temperature=0.5,
        model=model,
    )
    return {
        "what_it_does": result.what_it_does,
        "agent_limitations": result.agent_limitations,
        "human_verdict": result.human_verdict,
        "profile": result.profile,
    }


def _generate_overall_narrative(
    *,
    competition_name: str,
    entry_profiles: dict[str, str],
    entries: list[dict],
    matches: list[dict],
    champion_entry: dict | None,
    run_index: dict,
    provider: str,
    model: str,
) -> str:
    entry_map = {e["id"]: e for e in entries}

    profiles_text = "\n".join(
        f"- {entry_map.get(int(k), {}).get('start_url') or k}: {v['profile'] if isinstance(v, dict) else v}"
        for k, v in entry_profiles.items()
    )

    # Group by run, then by round within each run
    by_run: dict[int, dict[int, list[dict]]] = {}
    for match in matches:
        rid = match.get("run_id") or 0
        by_run.setdefault(rid, {}).setdefault(match["round_number"], []).append(match)

    bracket_lines = []
    for rid in sorted(by_run, key=lambda r: run_index.get(r, r)):
        run_num = run_index.get(rid, rid)
        bracket_lines.append(f"Run {run_num}:")
        for round_num in sorted(by_run[rid]):
            for match in by_run[rid][round_num]:
                eids = _parse_entry_ids(match.get("entry_ids"))
                labels = [entry_map.get(eid, {}).get("start_url") or str(eid) for eid in eids]
                winner_id = match.get("winner_entry_id")
                winner_label = (entry_map.get(winner_id, {}).get("start_url") or str(winner_id)) if winner_id else "?"
                bracket_lines.append(f"  Round {round_num}: {' vs '.join(labels)} → {winner_label}")

    num_runs = len(by_run)
    rounds_per_run = max((max(by_run[r]) for r in by_run), default=0)
    champion_url = (champion_entry.get("start_url") or "unknown") if champion_entry else "unknown"
    # Count how many runs each entry won, for context
    run_wins: dict = {}
    for match in matches:
        if match["round_number"] == rounds_per_run and match.get("winner_entry_id"):
            wid = match["winner_entry_id"]
            run_wins[wid] = run_wins.get(wid, 0) + 1
    champion_wins = run_wins.get(champion_entry["id"], 0) if champion_entry else 0

    system_prompt = (
        "You are writing a tournament recap for a LinkedIn post about an AI UX testing competition. "
        "Your audience is developers and product builders. "
        "Be engaging, specific, and punchy. Avoid corporate filler. "
        "Respond with JSON only."
    )
    user_prompt = (
        f"Competition: {competition_name}\n"
        f"{len(entries)} apps competed across {num_runs} independent runs of a "
        f"{rounds_per_run}-round single-elimination bracket, all judged by AI.\n\n"
        f"Full bracket record ({num_runs} runs × {rounds_per_run} rounds):\n"
        + "\n".join(bracket_lines) + "\n\n"
        f"App profiles (synthesised across all runs):\n{profiles_text}\n\n"
        f"Overall champion (won {champion_wins} of {num_runs} runs): {champion_url}\n\n"
        "Write 4-5 sentences narrating how this tournament played out across all runs. "
        "What themes emerged? Which app dominated and why? Any surprises across different runs? "
        "What ultimately separated the champion from the field?\n\n"
        '{"narrative": "<4-5 sentences>"}'
    )

    llm = get_llm_client(provider)
    result = llm.generate_action(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        images=[],
        schema=_NarrativeOutput,
        temperature=0.6,
        model=model,
    )
    return result.narrative


# ── public async entry point ──────────────────────────────────────────────────

async def generate_recap(
    competition_id: str,
    *,
    provider: str,
    model: str,
) -> dict:
    """Generate and persist a competition recap. Returns the saved recap dict."""
    async with open_db() as db:
        competition = await queries.get_competition(db, competition_id)
        if not competition:
            raise ValueError(f"Competition {competition_id} not found")

        raw_entries = await queries.list_competition_entries(db, competition_id)
        entries: list[dict] = []
        for entry in raw_entries:
            enriched = dict(entry)
            session = await queries.get_session(db, entry["session_id"])
            if session:
                enriched["start_url"] = session["start_url"]
                enriched["goal"] = session["goal"]
            entries.append(enriched)

        # Only matches that have judge reasoning
        all_matches = [
            dict(m) for m in await queries.list_competition_matches(db, competition_id)
            if m.get("judge_reasoning")
        ]

        # Champion = entry that won the most runs (majority vote across all completed runs)
        runs = await queries.list_competition_runs(db, competition_id)
        from collections import Counter
        champion_counts = Counter(
            run["champion_entry_id"] for run in runs
            if run["status"] == "complete" and run.get("champion_entry_id")
        )
        champion_entry_id = champion_counts.most_common(1)[0][0] if champion_counts else None
        champion_entry = next((e for e in entries if e["id"] == champion_entry_id), None)

    run_index = _run_index_map(all_matches)

    # Generate all entry profiles in parallel (outside the DB context so we
    # don't hold the connection while waiting on LLM calls)
    async def _profile(entry: dict) -> tuple[int, dict]:
        history = _entry_match_history(entry["id"], all_matches)
        analysis = await asyncio.to_thread(
            _generate_entry_profile,
            entry=entry,
            match_history=history,
            run_index=run_index,
            provider=provider,
            model=model,
        )
        return entry["id"], analysis

    raw_results = await asyncio.gather(*[_profile(e) for e in entries], return_exceptions=True)

    entry_profiles: dict[str, dict] = {}
    for result in raw_results:
        if isinstance(result, Exception):
            logger.warning("Entry profile generation failed: %s", result)
            continue
        entry_id, analysis = result
        entry_profiles[str(entry_id)] = analysis

    overall_narrative = await asyncio.to_thread(
        _generate_overall_narrative,
        competition_name=competition["name"],
        entry_profiles=entry_profiles,
        entries=entries,
        matches=all_matches,
        champion_entry=champion_entry,
        run_index=run_index,
        provider=provider,
        model=model,
    )

    async with open_db() as db:
        recap_id = await queries.create_competition_recap(
            db,
            competition_id=competition_id,
            entry_profiles=json.dumps(entry_profiles),
            overall_narrative=overall_narrative,
            provider=provider,
            model=model,
        )
        history = await queries.list_competition_recaps(db, competition_id)

    return {
        "id": recap_id,
        "competition_id": competition_id,
        "entry_profiles": entry_profiles,
        "overall_narrative": overall_narrative,
        "provider": provider,
        "model": model,
        "generated_at": queries.now_iso(),
        "generation_count": len(history),
    }
