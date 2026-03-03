import asyncio
import json
import uuid
from typing import Callable

from langgraph.graph import StateGraph, END

from agent.state import AgentState, AgentAction
from agent.prompts import system_prompt, user_prompt
from browser.manager import BrowserManager
from browser import actions as browser_actions
from database.queries import (
    insert_screenshot,
    insert_html_capture,
    insert_action,
    insert_run_log,
    update_session_status,
    get_memory,
    get_session,
)
from llm.registry import validate_provider_model
from llm.openai_client import OpenAIClient
from llm.gemini_client import GeminiClient
from llm.claude_client import ClaudeClient
from utils.image import to_base64_png
from utils.loop_detector import fingerprint, is_looping


def get_llm_client(provider: str):
    if provider == "openai":
        return OpenAIClient()
    if provider == "gemini":
        return GeminiClient()
    if provider == "claude":
        return ClaudeClient()
    raise ValueError("Unknown provider")


def compute_recursion_limit(max_steps: int) -> int:
    # Graph has multiple node transitions per logical step. Keep margin for init/teardown.
    return max(50, max_steps * 6 + 20)


def build_graph(db, emit: Callable[[dict], None]):
    browser = BrowserManager()

    def require_page():
        page = browser.page
        if page is None:
            raise RuntimeError("Browser page unavailable")
        return page

    async def log_event(state: AgentState, level: str, message: str, details: str | None = None):
        await insert_run_log(
            db,
            session_id=state["session_id"],
            level=level,
            message=message,
            details=details,
            step_number=state.get("current_step"),
        )
        emit({"type": "log", "data": {"level": level, "message": message, "details": details, "step": state.get("current_step")}})

    async def initialize(state: AgentState):
        await log_event(state, "info", "Initializing browser session", f"mode={state['mode']} url={state['start_url']}")
        await browser.launch(state["mode"])
        await browser_actions.navigate(require_page(), state["start_url"])
        png = await browser.screenshot()
        html = await browser.get_html()
        url = await browser.get_url()
        screenshot_id = await insert_screenshot(
            db,
            session_id=state["session_id"],
            url=url,
            image_data=png,
            action_taken="initialize",
            step_number=0,
        )
        await insert_html_capture(
            db,
            session_id=state["session_id"],
            url=url,
            html=html,
            step_number=0,
        )
        state["current_url"] = url
        state["current_screenshot"] = to_base64_png(png)
        state["current_screenshot_id"] = screenshot_id
        state["current_step"] = 0
        state["pages_visited"] = [url]
        emit({"type": "step", "data": {"step": 0, "action": "initialize", "screenshot_id": screenshot_id, "url": url}})
        await log_event(state, "info", "Initialization complete", f"url={url} screenshot_id={screenshot_id}")
        return state

    async def think(state: AgentState):
        if state["status"] != "running":
            return state
        # Hard fail-safe in case control flow reaches think beyond configured bounds.
        if state["current_step"] >= state["run_config"].get("max_steps", 50):
            state["status"] = "failed"
            state["end_reason"] = "Max steps reached"
            await log_event(state, "warning", "Max steps reached before next LLM decision")
            return state

        memory = await get_memory(db, state["session_id"])
        state["memory"] = memory

        run_config = state["run_config"]
        max_history = run_config.get("max_history_actions", 5)
        preamble = run_config.get("custom_system_prompt_preamble", "")

        prompt = system_prompt(state["goal"], state["mode"], memory, state["action_history"], max_history, preamble)
        user = user_prompt(state["current_url"], state["current_step"])

        validate_provider_model(state["provider"], state["model"], state["tier"])
        llm = get_llm_client(state["provider"])

        try:
            await log_event(state, "debug", "Requesting next action from LLM", f"provider={state['provider']} model={state['model']}")
            action = llm.generate_action(
                system_prompt=prompt,
                user_prompt=user,
                images=[base64_to_bytes(state["current_screenshot"])],
                schema=AgentAction,
                temperature=0.2,
                model=state["model"],
            )
            next_action = action.model_dump()
            if not next_action.get("intent"):
                next_action["intent"] = f"Execute {next_action.get('action')} to make progress toward the goal."
            state["next_action"] = next_action
            await log_event(
                state,
                "info",
                "LLM returned next action",
                (
                    f"action={state['next_action'].get('action')} "
                    f"intent={state['next_action'].get('intent')} "
                    f"why={state['next_action'].get('reasoning')}"
                ),
            )
        except Exception as exc:
            state["next_action"] = {
                "action": "fail",
                "params": {"reason": f"LLM decision error: {str(exc)}"},
                "intent": "Stop the run because next-action planning failed.",
                "reasoning": "LLM call failed; ending session safely.",
                "memory_update": None,
            }
            await log_event(state, "error", "LLM call failed", str(exc))
        return state

    async def execute(state: AgentState):
        if state["status"] != "running":
            return state

        action = state["next_action"]
        action_type = action["action"]
        params = action.get("params", {})
        intent = action.get("intent")
        reasoning = action.get("reasoning", "")
        memory_update = action.get("memory_update")
        success, error = True, None
        next_step = state["current_step"] + 1

        async def emit_coordinate_preview(markers: list[dict], label: str):
            png_preview = await browser.screenshot_with_markers(markers)
            preview_url = await browser.get_url()
            preview_id = await insert_screenshot(
                db,
                session_id=state["session_id"],
                url=preview_url,
                image_data=png_preview,
                action_taken=f"{action_type}_preview",
                step_number=next_step,
            )
            emit(
                {
                    "type": "step",
                    "data": {
                        "step": next_step,
                        "action": f"{label} (preview)",
                        "intent": intent,
                        "reasoning": reasoning,
                        "screenshot_id": preview_id,
                        "url": preview_url,
                    },
                }
            )

        if action_type == "scroll_down":
            success, error = await browser_actions.scroll_down(require_page(), params.get("pixels", 300))
        elif action_type == "scroll_up":
            success, error = await browser_actions.scroll_up(require_page(), params.get("pixels", 300))
        elif action_type == "swipe_left":
            await emit_coordinate_preview(
                [{"x": params.get("x"), "y": params.get("y"), "label": "swipe start"}],
                f"swipe_left @ ({params.get('x')}, {params.get('y')})",
            )
            success, error = await browser_actions.swipe_left(require_page(), params.get("x"), params.get("y"), params.get("distance", 100))
        elif action_type == "swipe_right":
            await emit_coordinate_preview(
                [{"x": params.get("x"), "y": params.get("y"), "label": "swipe start"}],
                f"swipe_right @ ({params.get('x')}, {params.get('y')})",
            )
            success, error = await browser_actions.swipe_right(require_page(), params.get("x"), params.get("y"), params.get("distance", 100))
        elif action_type == "click":
            await emit_coordinate_preview(
                [{"x": params.get("x"), "y": params.get("y"), "label": "click target"}],
                f"click @ ({params.get('x')}, {params.get('y')})",
            )
            success, error = await browser_actions.click(require_page(), params.get("x"), params.get("y"))
        elif action_type == "click_and_drag":
            await emit_coordinate_preview(
                [
                    {"x": params.get("x1"), "y": params.get("y1"), "label": "drag start", "color": "#d14343"},
                    {"x": params.get("x2"), "y": params.get("y2"), "label": "drag end", "color": "#0f766e"},
                ],
                f"drag ({params.get('x1')}, {params.get('y1')}) -> ({params.get('x2')}, {params.get('y2')})",
            )
            success, error = await browser_actions.click_and_drag(require_page(), params.get("x1"), params.get("y1"), params.get("x2"), params.get("y2"))
        elif action_type == "type":
            success, error = await browser_actions.type_text(require_page(), params.get("text", ""))
        elif action_type == "navigate":
            success, error = await browser_actions.navigate(require_page(), params.get("url"))
        elif action_type == "save_to_memory":
            if params.get("key") and params.get("value") and not memory_update:
                memory_update = {params["key"]: params["value"]}
            success, error = True, None
        elif action_type == "finish":
            state["status"] = "completed"
            state["end_reason"] = params.get("summary", "completed")
        elif action_type == "fail":
            state["status"] = "failed"
            state["end_reason"] = params.get("reason", "failed")
        else:
            success, error = False, f"Unknown action: {action_type}"

        # memory updates captured by capture node
        state["_last_action"] = {
            "action_type": action_type,
            "action_params": params,
            "intent": intent,
            "reasoning": reasoning,
            "success": success,
            "error": error,
            "memory_update": memory_update,
        }
        await log_event(
            state,
            "info",
            "Executed action",
            f"action={action_type} params={params} success={success} error={error}",
        )
        return state

    async def capture(state: AgentState):
        last_action = state.get("_last_action", {})
        step = state["current_step"] + 1
        png = await browser.screenshot()
        html = await browser.get_html()
        url = await browser.get_url()
        screenshot_id = await insert_screenshot(
            db,
            session_id=state["session_id"],
            url=url,
            image_data=png,
            action_taken=last_action.get("action_type"),
            step_number=step,
        )
        await insert_html_capture(
            db,
            session_id=state["session_id"],
            url=url,
            html=html,
            step_number=step,
        )

        await insert_action(
            db,
            session_id=state["session_id"],
            step_number=step,
            action_type=last_action.get("action_type", ""),
            action_params=last_action.get("action_params", {}),
            intent=last_action.get("intent"),
            reasoning=last_action.get("reasoning", ""),
            screenshot_id=screenshot_id,
            success=bool(last_action.get("success", False)),
            error_message=last_action.get("error"),
        )

        # update memory if needed
        memory_update = last_action.get("memory_update")
        if memory_update:
            from database.queries import upsert_memory
            for k, v in memory_update.items():
                await upsert_memory(db, session_id=state["session_id"], key=k, value=v)

        # update state
        state["current_step"] = step
        state["current_url"] = url
        state["current_screenshot"] = to_base64_png(png)
        state["current_screenshot_id"] = screenshot_id

        record = {
            "step": step,
            "action_type": last_action.get("action_type"),
            "action_params": last_action.get("action_params"),
            "intent": last_action.get("intent"),
            "reasoning": last_action.get("reasoning"),
            "url": url,
            "success": bool(last_action.get("success", False)),
            "error": last_action.get("error"),
        }
        state["action_history"].append(record)
        state["pages_visited"].append(url)

        # loop detection
        fp = fingerprint(last_action.get("action_type", ""), last_action.get("action_params", {}))
        state["recent_action_fingerprints"].append(fp)
        window = state["run_config"].get("loop_detection_window", 10)
        state["recent_action_fingerprints"] = state["recent_action_fingerprints"][-window:]

        emit({
            "type": "step",
            "data": {
                "step": step,
                "action": last_action.get("action_type"),
                "intent": last_action.get("intent"),
                "reasoning": last_action.get("reasoning"),
                "screenshot_id": screenshot_id,
                "url": url,
            },
        })
        await log_event(state, "debug", "Captured state artifacts", f"step={step} screenshot_id={screenshot_id} url={url}")

        return state

    async def check_status(state: AgentState):
        # stop requested?
        session = await get_session(db, state["session_id"])
        if session and session["status"] == "stopped":
            state["status"] = "stopped"
            state["end_reason"] = "Stopped by user"
            await log_event(state, "warning", "Stop requested by user")

        # loop detection
        if state["run_config"].get("loop_detection_enabled", True):
            rules = state["run_config"].get("loop_detection_rules", {})
            if is_looping(state["recent_action_fingerprints"], rules, state["action_history"]):
                state["status"] = "loop_detected"
                state["end_reason"] = "Loop detected"
                await log_event(state, "warning", "Loop detected")

        if state["run_config"].get("stop_on_first_error") and state["action_history"]:
            if not state["action_history"][-1]["success"]:
                state["status"] = "failed"
                state["end_reason"] = "Stopped on first error"

        # max steps
        if state["current_step"] >= state["run_config"].get("max_steps", 50):
            state["status"] = "failed"
            state["end_reason"] = "Max steps reached"
            await log_event(state, "warning", "Max steps reached")

        if state["status"] != "running":
            await update_session_status(db, state["session_id"], state["status"], state["end_reason"])
            emit({"type": "status", "data": {"status": state["status"], "end_reason": state["end_reason"]}})
            await log_event(state, "info", "Session reached terminal status", f"status={state['status']} reason={state['end_reason']}")
        return state

    async def teardown(state: AgentState):
        await browser.close()
        return state

    graph = StateGraph(AgentState)
    graph.add_node("initialize", initialize)
    graph.add_node("think", think)
    graph.add_node("execute", execute)
    graph.add_node("capture", capture)
    graph.add_node("check_status", check_status)
    graph.add_node("teardown", teardown)

    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "think")
    graph.add_edge("think", "execute")
    graph.add_edge("execute", "capture")
    graph.add_edge("capture", "check_status")
    graph.add_conditional_edges(
        "check_status",
        lambda state: "end" if state["status"] != "running" else "continue",
        {"continue": "think", "end": "teardown"},
    )
    graph.add_edge("teardown", END)

    return graph.compile()


def base64_to_bytes(b64: str) -> bytes:
    import base64
    return base64.b64decode(b64.encode("utf-8"))


async def run_test_session(*, db, session_row, user_tier: str, emit: Callable[[dict], None]):
    state: AgentState = {
        "session_id": session_row["id"],
        "user_id": session_row["user_id"],
        "goal": session_row["goal"],
        "start_url": session_row["start_url"],
        "mode": session_row["mode"],
        "provider": session_row["provider"],
        "model": session_row["model"],
        "tier": user_tier,
        "run_config": json.loads(session_row["config_json"]),
        "current_url": session_row["start_url"],
        "current_screenshot": "",
        "current_screenshot_id": 0,
        "current_step": 0,
        "memory": {},
        "action_history": [],
        "recent_action_fingerprints": [],
        "pages_visited": [],
        "status": "running",
        "end_reason": None,
        "next_action": None,
        "postmortem_run_analysis": None,
        "postmortem_html_analysis": None,
        "postmortem_recommendations": None,
    }

    graph = build_graph(db, emit)
    recursion_limit = compute_recursion_limit(state["run_config"].get("max_steps", 50))
    final_state = await graph.ainvoke(state, config={"recursion_limit": recursion_limit})
    return final_state
