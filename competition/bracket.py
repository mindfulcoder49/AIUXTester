"""
Bracket builder for single-elimination tournaments.

Rules:
- If N is even: all pairs
- If N is odd: first match is a trio, remaining N-3 entries form pairs
- Recurse on winners each round until 1 remains
"""
from __future__ import annotations

import random


def build_bracket(entry_ids: list[int]) -> list[list[list[int]]]:
    """
    Given a list of entry IDs, return a list of rounds.
    Each round is a list of matches; each match is a list of 2 or 3 entry IDs.

    Example (7 entries):
      Round 1: [[1,2,3], [4,5], [6,7]]   → 3 winners
      Round 2: [[w1,w2,w3]]              → 1 winner (champion)
    """
    ids = list(entry_ids)
    random.shuffle(ids)
    rounds: list[list[list[int]]] = []
    _build_rounds(ids, rounds)
    return rounds


def _make_matches(ids: list[int]) -> list[list[int]]:
    """Split a list of IDs into matches (one trio if odd, rest pairs)."""
    if len(ids) == 1:
        return [ids]
    matches: list[list[int]] = []
    start = 0
    if len(ids) % 2 == 1:
        matches.append([ids[0], ids[1], ids[2]])
        start = 3
    for i in range(start, len(ids), 2):
        matches.append([ids[i], ids[i + 1]])
    return matches


def _build_rounds(ids: list[int], rounds: list[list[list[int]]]) -> None:
    if len(ids) <= 1:
        return
    matches = _make_matches(ids)
    rounds.append(matches)
    # Placeholder winner slots — actual winners filled in by runner
    # Return count of matches so caller knows how many winners to expect
    _build_rounds([0] * len(matches), rounds)


def round_count(n: int) -> int:
    """Return the number of rounds needed for n entries."""
    rounds = 0
    while n > 1:
        n = (n - 3) // 2 + 1 if n % 2 == 1 else n // 2
        rounds += 1
    return rounds
