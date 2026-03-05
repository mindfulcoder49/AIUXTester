from typing import Dict, List

from config import VIEWPORT_DESKTOP, VIEWPORT_MOBILE


def format_memory(memory: Dict[str, str]) -> str:
    if not memory:
        return "No memory saved yet."
    return "\n".join([f"- {k}: {v}" for k, v in memory.items()])


def format_history(history: List[dict], max_items: int) -> str:
    if not history:
        return "No actions yet."
    items = history[-max_items:]
    lines = []
    for h in items:
        params = str(h["action_params"])
        result = h.get("execution_result")
        if result is None:
            lines.append(f"{h['step']}. {h['action_type']} {params} (success={h['success']})")
        else:
            lines.append(
                f"{h['step']}. {h['action_type']} {params} (success={h['success']}, result={result})"
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
        "Use save_to_memory for any credentials or facts needed later.",
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
        + '{"action":"<one of allowed actions>","params":{"script":"<JS code when action is execute_js>"},"intent":"<what you are trying to accomplish next>","reasoning":"<why this action is best now>","memory_update":null}\n'
        + "Make intent concrete and user-facing (what you are trying to do on this step).\n"
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
