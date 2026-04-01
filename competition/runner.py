"""
Competition bracket runner.

run_competition_job() is the RQ entry point — called as a background job.
run_competition() is the async orchestrator.
"""
from __future__ import annotations

import asyncio
import logging

from competition.bracket import _make_matches
from competition.judge import judge_match
from database import queries
from database.db import open_db

logger = logging.getLogger("aiuxtester.competition")


# ── RQ entry point ──────────────────────────────────────────────────────────

def run_competition_job(competition_id: str, provider: str, model: str) -> None:
    asyncio.run(_run_competition(competition_id, provider, model))


# ── Async orchestrator ──────────────────────────────────────────────────────

async def _run_competition(competition_id: str, provider: str, model: str) -> None:
    async with open_db() as db:
        try:
            await _execute_bracket(db, competition_id, provider, model)
        except Exception as exc:
            logger.exception("Competition %s failed: %s", competition_id, exc)
            await queries.update_competition_status(db, competition_id, "complete")
            raise


async def _execute_bracket(db, competition_id: str, provider: str, model: str) -> None:
    # Load all entries
    entries = await queries.list_competition_entries(db, competition_id)
    if not entries:
        await queries.update_competition_status(db, competition_id, "complete")
        return

    await queries.update_competition_status(db, competition_id, "running")
    logger.info("Competition %s starting with %d entries", competition_id, len(entries))

    # Map entry id → entry row
    entry_map = {e["id"]: e for e in entries}
    current_entry_ids = [e["id"] for e in entries]

    round_number = 1
    while len(current_entry_ids) > 1:
        matches = _make_matches(current_entry_ids)
        winner_ids: list[int] = []

        for match_number, match_entry_ids in enumerate(matches, start=1):
            # Persist match record
            match_id = await queries.create_competition_match(
                db,
                competition_id=competition_id,
                round_number=round_number,
                match_number=match_number,
                entry_ids=match_entry_ids,
            )

            if len(match_entry_ids) == 1:
                # Bye — only entry advances automatically
                await queries.update_competition_match(
                    db, match_id,
                    winner_entry_id=match_entry_ids[0],
                    reasoning="Advanced automatically (only entry in match).",
                )
                winner_ids.append(match_entry_ids[0])
                continue

            # Fetch sessions and postmortems for each entry in this match
            match_entries = [entry_map[eid] for eid in match_entry_ids]
            sessions = []
            postmortems = []
            for entry in match_entries:
                session = await queries.get_session(db, entry["session_id"])
                postmortem = await queries.get_postmortem(db, entry["session_id"])
                actions = await queries.list_actions(db, entry["session_id"])
                # Inject action_count into entry dict for judge
                enriched = dict(entry)
                enriched["action_count"] = len(actions)
                sessions.append(session)
                postmortems.append(postmortem)
                match_entries[match_entries.index(entry)] = enriched

            logger.info(
                "Competition %s round %d match %d: judging %d entries",
                competition_id, round_number, match_number, len(match_entry_ids),
            )

            try:
                result = judge_match(
                    entries=match_entries,
                    sessions=sessions,
                    postmortems=postmortems,
                    provider=provider,
                    model=model,
                )
                winner_idx = max(0, min(result.winner_index, len(match_entry_ids) - 1))
                winner_entry_id = match_entry_ids[winner_idx]
                reasoning = result.reasoning
            except Exception as exc:
                logger.warning("Judge failed for match %d: %s — picking first entry", match_id, exc)
                winner_entry_id = match_entry_ids[0]
                reasoning = f"Judge unavailable ({exc}); first entry advanced by default."

            await queries.update_competition_match(
                db, match_id,
                winner_entry_id=winner_entry_id,
                reasoning=reasoning,
            )
            winner_ids.append(winner_entry_id)

        current_entry_ids = winner_ids
        round_number += 1

    await queries.update_competition_status(db, competition_id, "complete")
    champion = current_entry_ids[0] if current_entry_ids else None
    logger.info("Competition %s complete. Champion entry id: %s", competition_id, champion)
