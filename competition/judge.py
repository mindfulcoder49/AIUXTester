"""
LLM judge for a single competition match.

Reuses the same generate_action() pattern as agent/postmortem_graph.py.
"""
from __future__ import annotations

from pydantic import BaseModel

from agent.postmortem_graph import get_llm_client


class JudgeOutput(BaseModel):
    winner_index: int  # 0-based index into the entries list
    reasoning: str     # paragraph explaining the decision


def _entry_summary(entry: dict, session: dict, postmortem: dict | None, index: int) -> str:
    label = f"Submission {index + 1}"
    pm = postmortem or {}
    lines = [
        f"=== {label} ===",
        f"App URL: {session.get('start_url', 'unknown')}",
        f"Goal: {session.get('goal', '')[:400]}",
        f"Status: {session.get('status', 'unknown')}",
        f"Actions taken: {entry.get('action_count', 0)}",
        f"End reason: {session.get('end_reason') or 'completed normally'}",
        "",
        "Run Analysis:",
        (pm.get('run_analysis') or 'No postmortem available.')[:800],
        "",
        "Recommendations:",
        (pm.get('recommendations') or 'None.')[:400],
    ]
    if entry.get('note'):
        lines.insert(2, f"Submitter note: {entry['note']}")
    return "\n".join(lines)


def judge_match(
    *,
    entries: list[dict],       # competition_entry rows, each with action_count injected
    sessions: list[dict],      # session rows in same order
    postmortems: list[dict | None],  # postmortem rows (or None) in same order
    provider: str,
    model: str,
) -> JudgeOutput:
    n = len(entries)
    summaries = [
        _entry_summary(entries[i], sessions[i], postmortems[i], i)
        for i in range(n)
    ]

    system_prompt = (
        "You are an impartial judge for the Vibecode Olympics, a competition where developers "
        "submit AI-generated UX test runs of their own web apps. "
        "Your job is to pick the winner of this match based on which APP has the best user experience — "
        "not which test run was most thorough. "
        "Award the win to the app whose testing reveals it works well: smooth user flows, "
        "features that complete successfully, intuitive navigation, and few or no critical errors. "
        "Penalize apps whose runs reveal broken flows, failed registrations, confusing UX, or hard errors. "
        "A test that found nothing wrong is evidence of a good app. "
        "A test that found many bugs is evidence of a bad app, even if the test itself was thorough. "
        "Be decisive. Pick one winner. Respond in JSON."
    )

    user_prompt = (
        f"Compare the following {n} competition submissions and pick the best one.\n\n"
        + "\n\n".join(summaries)
        + f"\n\nRespond with JSON: {{\"winner_index\": <0 to {n-1}>, \"reasoning\": \"<paragraph>\"}}"
    )

    llm = get_llm_client(provider)
    return llm.generate_action(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        images=[],
        schema=JudgeOutput,
        temperature=0.3,
        model=model,
    )
