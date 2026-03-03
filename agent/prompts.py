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
        lines.append(f"{h['step']}. {h['action_type']} {h['action_params']} (success={h['success']})")
    return "\n".join(lines)


def system_prompt(goal: str, mode: str, memory: Dict[str, str], history: List[dict], max_history: int, preamble: str) -> str:
    viewport = VIEWPORT_MOBILE if mode == "mobile" else VIEWPORT_DESKTOP
    rules = [
        "Coordinates must be within viewport bounds.",
        "If you see a login form and have credentials in memory, use them.",
        "If you have taken the same action 3+ times without progress, use fail().",
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
        "- scroll_down {pixels}\n"
        "- scroll_up {pixels}\n"
        "- swipe_left {x,y,distance}\n"
        "- swipe_right {x,y,distance}\n"
        "- click {x,y}\n"
        "- click_and_drag {x1,y1,x2,y2}\n"
        "- type {text}\n"
        "- navigate {url}\n"
        "- save_to_memory {key,value}\n"
        "- finish {summary}\n"
        "- fail {reason}\n\n"
        f"## Rules\n- " + "\n- ".join(rules)
        + "\n\n## Required Output Format\n"
        + "Return ONLY valid JSON with these exact top-level keys:\n"
        + '{"action":"<one of allowed actions>","params":{},"intent":"<what you are trying to accomplish next>","reasoning":"<why this action is best now>","memory_update":null}\n'
        + "Make intent concrete and user-facing (what you are trying to do on this step).\n"
        + "Do not return page summaries, markdown, or any extra keys."
    )


def user_prompt(current_url: str, step: int) -> str:
    return f"Current URL: {current_url}\nStep: {step}\nReturn a JSON object only."
