"""
Competition bracket runner.

Supports repeated historical runs for the same competition, including a manual
broadcast pacing mode that pauses after each round.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import random
from collections import Counter

from competition.bracket import _make_matches
from competition.judge import judge_match
from database import queries
from database.db import open_db

logger = logging.getLogger("aiuxtester.competition")

PAIRING_STRATEGIES = {"submitted_order", "random", "balanced_random"}
PROGRESSION_MODES = {"automatic", "manual"}
ACTIVE_RUN_STATUSES = {"queued", "running", "awaiting_round"}


def run_competition_job(
    competition_id: str,
    run_id: int,
    provider: str | None = None,
    model: str | None = None,
    pairing_strategy: str | None = None,
    pairing_seed: int | None = None,
) -> None:
    del provider, model, pairing_strategy, pairing_seed
    asyncio.run(_run_single_competition_run(competition_id, run_id))


def run_competition_run_job(competition_id: str, run_id: int) -> None:
    asyncio.run(_run_single_competition_run(competition_id, run_id))


def run_competition_batch_job(competition_id: str, run_ids: list[int]) -> None:
    asyncio.run(_run_competition_batch(competition_id, run_ids))


def _pair_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def _historical_pair_counts(matches: list[dict]) -> Counter[tuple[int, int]]:
    pair_counts: Counter[tuple[int, int]] = Counter()
    for match in matches:
        entry_ids = match.get("entry_ids")
        if isinstance(entry_ids, str):
            try:
                import json

                parsed_ids = json.loads(entry_ids or "[]")
            except Exception:
                parsed_ids = []
        else:
            parsed_ids = entry_ids or []
        real_ids = [int(entry_id) for entry_id in parsed_ids if isinstance(entry_id, int)]
        for left, right in itertools.combinations(real_ids, 2):
            pair_counts[_pair_key(left, right)] += 1
    return pair_counts


def _first_round_score(entry_ids: list[int], pair_counts: Counter[tuple[int, int]]) -> int:
    score = 0
    for match_entry_ids in _make_matches(entry_ids):
        for left, right in itertools.combinations(match_entry_ids, 2):
            score += pair_counts[_pair_key(left, right)]
    return score


def _pick_entry_order(
    entry_ids: list[int],
    *,
    pairing_strategy: str,
    pairing_seed: int | None,
    pair_counts: Counter[tuple[int, int]],
) -> list[int]:
    if pairing_strategy not in PAIRING_STRATEGIES:
        pairing_strategy = "balanced_random"

    if pairing_strategy == "submitted_order":
        return list(entry_ids)

    seed = int(pairing_seed or 0)
    if pairing_strategy == "random":
        shuffled = list(entry_ids)
        random.Random(seed).shuffle(shuffled)
        return shuffled

    best_order = list(entry_ids)
    best_score = None
    attempts = max(12, min(64, len(entry_ids) * 6))
    for attempt in range(attempts):
        candidate = list(entry_ids)
        random.Random(seed + attempt).shuffle(candidate)
        candidate_score = _first_round_score(candidate, pair_counts)
        if best_score is None or candidate_score < best_score:
            best_order = candidate
            best_score = candidate_score
    return best_order


async def _refresh_competition_status(db, competition_id: str) -> None:
    runs = await queries.list_competition_runs(db, competition_id)
    if not runs:
        return

    next_status = "running" if any(run["status"] in ACTIVE_RUN_STATUSES for run in runs) else "complete"
    await queries.update_competition_status(db, competition_id, next_status)


async def _load_run_spec(db, competition_id: str, run_id: int) -> dict | None:
    run = await queries.get_competition_run(db, run_id)
    if not run:
        return None
    run_dict = dict(run)
    if run_dict["competition_id"] != competition_id:
        return None
    return run_dict


async def _run_single_competition_run(competition_id: str, run_id: int) -> None:
    async with open_db() as db:
        try:
            await queries.update_competition_status(db, competition_id, "running")
            run = await _load_run_spec(db, competition_id, run_id)
            if not run:
                return
            await _execute_bracket_run(
                db,
                competition_id,
                run_id=run_id,
                provider=run.get("provider") or "openai",
                model=run.get("model") or "gpt-5-mini",
                pairing_strategy=run.get("pairing_strategy") or "balanced_random",
                pairing_seed=run.get("pairing_seed"),
                stop_after_round=run.get("progression_mode") == "manual",
            )
        except Exception as exc:
            logger.exception("Competition %s run %s failed: %s", competition_id, run_id, exc)
            await queries.update_competition_run_status(db, run_id, "failed")
            raise
        finally:
            await _refresh_competition_status(db, competition_id)


async def _run_competition_batch(competition_id: str, run_ids: list[int]) -> None:
    async with open_db() as db:
        try:
            await queries.update_competition_status(db, competition_id, "running")
            for run_id in run_ids:
                run = await _load_run_spec(db, competition_id, run_id)
                if not run:
                    continue
                try:
                    await _execute_bracket_run(
                        db,
                        competition_id,
                        run_id=run_id,
                        provider=run.get("provider") or "openai",
                        model=run.get("model") or "gpt-5-mini",
                        pairing_strategy=run.get("pairing_strategy") or "balanced_random",
                        pairing_seed=run.get("pairing_seed"),
                        stop_after_round=False,
                    )
                except Exception as exc:
                    logger.exception("Competition %s run %s failed: %s", competition_id, run_id, exc)
                    await queries.update_competition_run_status(db, run_id, "failed")
        finally:
            await _refresh_competition_status(db, competition_id)


async def _starting_state_for_run(
    db,
    competition_id: str,
    *,
    run_id: int,
    pairing_strategy: str,
    pairing_seed: int | None,
) -> tuple[list[dict], list[int], int]:
    entries = await queries.list_competition_entries(db, competition_id)
    if len(entries) < 2:
        return entries, [], 1

    run_matches = [dict(match) for match in await queries.list_competition_matches(db, competition_id, run_id=run_id)]
    if not run_matches:
        historical_matches = [
            dict(match)
            for match in await queries.list_competition_matches(db, competition_id)
            if match["run_id"] != run_id
        ]
        pair_counts = _historical_pair_counts(historical_matches)
        entry_order = _pick_entry_order(
            [entry["id"] for entry in entries],
            pairing_strategy=pairing_strategy,
            pairing_seed=pairing_seed,
            pair_counts=pair_counts,
        )
        return entries, entry_order, 1

    max_round = max(match["round_number"] for match in run_matches)
    latest_round_matches = sorted(
        [match for match in run_matches if match["round_number"] == max_round],
        key=lambda item: item["match_number"],
    )
    winner_ids = [match["winner_entry_id"] for match in latest_round_matches if match.get("winner_entry_id")]
    if len(winner_ids) != len(latest_round_matches):
        raise RuntimeError(f"Run {run_id} cannot resume because round {max_round} is incomplete")
    return entries, winner_ids, max_round + 1


async def _execute_bracket_run(
    db,
    competition_id: str,
    *,
    run_id: int,
    provider: str,
    model: str,
    pairing_strategy: str,
    pairing_seed: int | None,
    stop_after_round: bool,
) -> None:
    entries, current_entry_ids, round_number = await _starting_state_for_run(
        db,
        competition_id,
        run_id=run_id,
        pairing_strategy=pairing_strategy,
        pairing_seed=pairing_seed,
    )
    if len(entries) < 2:
        await queries.update_competition_run_status(db, run_id, "failed")
        return

    if len(current_entry_ids) <= 1:
        champion_entry_id = current_entry_ids[0] if current_entry_ids else None
        await queries.complete_competition_run(db, run_id, champion_entry_id)
        return

    await queries.update_competition_run_status(db, run_id, "running")
    logger.info(
        "Competition %s run %s continuing at round %d using %s seed=%s",
        competition_id,
        run_id,
        round_number,
        pairing_strategy,
        pairing_seed,
    )

    entry_map = {entry["id"]: entry for entry in entries}
    while len(current_entry_ids) > 1:
        matches = _make_matches(current_entry_ids)
        winner_ids: list[int] = []

        for match_number, match_entry_ids in enumerate(matches, start=1):
            match_id = await queries.create_competition_match(
                db,
                competition_id=competition_id,
                run_id=run_id,
                round_number=round_number,
                match_number=match_number,
                entry_ids=match_entry_ids,
            )

            if len(match_entry_ids) == 1:
                await queries.update_competition_match(
                    db,
                    match_id,
                    winner_entry_id=match_entry_ids[0],
                    reasoning="Advanced automatically (only entry in match).",
                )
                winner_ids.append(match_entry_ids[0])
                continue

            match_entries = [entry_map[entry_id] for entry_id in match_entry_ids]
            sessions = []
            postmortems = []
            for index, entry in enumerate(match_entries):
                session = await queries.get_session(db, entry["session_id"])
                postmortem = await queries.get_postmortem(db, entry["session_id"])
                actions = await queries.list_actions(db, entry["session_id"])
                enriched_entry = dict(entry)
                enriched_entry["action_count"] = len(actions)
                match_entries[index] = enriched_entry
                sessions.append(session)
                postmortems.append(postmortem)

            logger.info(
                "Competition %s run %s round %d match %d: judging %d entries",
                competition_id,
                run_id,
                round_number,
                match_number,
                len(match_entry_ids),
            )

            try:
                await queries.update_competition_match_status(db, match_id, "running")
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
                db,
                match_id,
                winner_entry_id=winner_entry_id,
                reasoning=reasoning,
            )
            winner_ids.append(winner_entry_id)

        current_entry_ids = winner_ids
        if stop_after_round and len(current_entry_ids) > 1:
            await queries.update_competition_run_status(db, run_id, "awaiting_round")
            logger.info(
                "Competition %s run %s paused after round %d awaiting the next admin trigger",
                competition_id,
                run_id,
                round_number,
            )
            return
        round_number += 1

    champion_entry_id = current_entry_ids[0] if current_entry_ids else None
    await queries.complete_competition_run(db, run_id, champion_entry_id)
    logger.info(
        "Competition %s run %s complete. Champion entry id: %s",
        competition_id,
        run_id,
        champion_entry_id,
    )
