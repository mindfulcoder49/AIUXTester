from typing import Dict, List

from config import VIEWPORT_DESKTOP, VIEWPORT_MOBILE


def format_memory(memory: Dict[str, str]) -> str:
    if not memory:
        return "No memory saved yet."
    return "\n".join([f"- {k}: {v}" for k, v in memory.items()])


def format_history(history: List[dict], max_items: int) -> str:
    if not history:
        return "No actions yet."
    valid = []
    for h in history:
        if not isinstance(h, dict):
            continue
        action_type = h.get("action_type")
        action_params = h.get("action_params")
        if not action_type or not isinstance(action_params, dict):
            continue
        valid.append(h)
    if not valid:
        return "No valid actions yet."
    items = valid[-max_items:]
    lines = []
    for h in items:
        params = str(h["action_params"])
        action_url = h.get("executed_on_url") or h.get("url") or "unknown_url"
        intent = h.get("intent") or ""
        reasoning = h.get("reasoning") or ""
        result = h.get("execution_result")
        outcome = h.get("action_outcome") or ""
        if result is None:
            lines.append(
                f"{h['step']}. on={action_url} action={h['action_type']} params={params} "
                f"(success={h['success']}) intent={intent} why={reasoning} outcome={outcome}"
            )
        else:
            lines.append(
                f"{h['step']}. on={action_url} action={h['action_type']} params={params} "
                f"(success={h['success']}, result={result}) intent={intent} why={reasoning} outcome={outcome}"
            )
    return "\n".join(lines)


def system_prompt(goal: str, mode: str, memory: Dict[str, str], history: List[dict], max_history: int, preamble: str) -> str:
    viewport = VIEWPORT_MOBILE if mode == "mobile" else VIEWPORT_DESKTOP
    rules = [
        "Rely on the provided HTML/DOM, not screenshots.",
        "If you see a login or registration form and have credentials in memory, use them.",
        "If you are stuck or repeating actions without meaningful progress, use give_up() with a concrete reason.",
        "If the task is complete, use finish() with a clear summary.",
        "Always include a short reasoning for the chosen action.",
        "Always include last_action_result: a concise description of what happened after the previous action (what changed, what was learned, whether it progressed).",
        "Use save_to_memory for any credentials or facts needed later.",
        "Prefer execute_js probes that return concise JSON-serializable results, not scripts that only cause side effects.",
        "Do not repeat substantially the same execute_js inspection on the same URL if the previous inspection already succeeded and the page has not changed.",
        "After one or two successful inspections, either move to a new question or finish with findings instead of re-extracting the same data.",
        "Do not probe for or discuss CSRF tokens, authentication headers, API keys, or internal security tokens — focus on user-facing flows and outcomes.",
        "When a form submission or login attempt succeeds or fails, report the user-visible result, not the underlying HTTP mechanism.",
    ]

    return (
        f"{preamble}\n"
        f"You are an autonomous web interaction agent. Your goal is: {goal}\n\n"
        f"You are operating in {mode} mode (viewport: {viewport['width']}x{viewport['height']}).\n\n"
        f"## Your Memory\n{format_memory(memory)}\n\n"
        f"## Action History (last {max_history} steps)\n{format_history(history, max_history)}\n\n"
        f"## Available Actions\n"
        "- execute_js {script}\n"
        "- navigate {url}\n"
        "- save_to_memory {key,value}\n"
        "- finish {summary}\n"
        "- fail {reason}\n\n"
        "- give_up {reason}\n\n"
        f"## Rules\n- " + "\n- ".join(rules)
        + "\n\n## Required Output Format\n"
        + "Return ONLY valid JSON with these exact top-level keys:\n"
        + '{"action":"<one of allowed actions>","params":{"script":"<JS code when action is execute_js>"},"intent":"<what you are trying to accomplish next>","reasoning":"<why this action is best now>","last_action_result":"<what happened after previous action>","memory_update":null}\n'
        + "Make intent concrete and user-facing (what you are trying to do on this step).\n"
        + "If there is no previous action to evaluate, set last_action_result to null.\n"
        + "If action=finish, params.summary should be a short findings report with this shape:\n"
        + "Verdict: <one sentence>\nFindings:\n- <issue or confirmation>\n- <issue or confirmation>\nNext step: <one concrete recommendation>\n"
        + "Do not return page summaries, markdown, or any extra keys."
    )


def user_prompt(current_url: str, step: int, html: str) -> str:
    return (
        f"Current URL: {current_url}\n"
        f"Step: {step}\n"
        "Current page HTML:\n"
        f"{html}\n\n"
        "Return a JSON object only."
    )
