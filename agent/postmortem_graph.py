import json
from typing import Callable

from langgraph.graph import StateGraph, END
from pydantic import BaseModel

from agent.state import AgentState
from llm.openai_client import OpenAIClient
from llm.gemini_client import GeminiClient
from llm.claude_client import ClaudeClient
from database.queries import list_html_captures, save_postmortem, insert_run_log, list_run_logs


class PostmortemRunOutput(BaseModel):
    run_analysis: str
    recommendations: str


class PostmortemHtmlOutput(BaseModel):
    html_analysis: str
    recommendations: str


def get_llm_client(provider: str):
    if provider == "openai":
        return OpenAIClient()
    if provider == "gemini":
        return GeminiClient()
    if provider == "claude":
        return ClaudeClient()
    raise ValueError("Unknown provider")


def build_postmortem_graph(db, emit: Callable[[dict], None]):
    def format_run_facts(run_facts: dict) -> str:
        lines = [
            f"Goal: {run_facts.get('goal')}",
            f"Final Status: {run_facts.get('final_status')}",
            f"End Reason: {run_facts.get('end_reason')}",
            f"Total Actions: {run_facts.get('total_actions')}",
            f"Action Counts: {run_facts.get('action_counts')}",
            f"Status Counts: {run_facts.get('status_counts')}",
            f"Unique URLs Visited: {', '.join(run_facts.get('unique_urls_visited', [])) or 'none'}",
            f"Error Count: {run_facts.get('error_count')}",
        ]
        return "Run Facts:\n" + "\n".join(lines)

    def build_run_facts(state: AgentState, logs: list[dict]) -> dict:
        actions = state.get("action_history", [])
        status_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        errors = []
        for a in actions:
            action_type = a.get("action_type", "unknown")
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
            key = "success" if a.get("success") else "failed"
            status_counts[key] = status_counts.get(key, 0) + 1
            if a.get("error"):
                errors.append({"step": a.get("step"), "error": a.get("error")})

        unique_urls = []
        for a in actions:
            u = a.get("url")
            if u and u not in unique_urls:
                unique_urls.append(u)

        return {
            "goal": state.get("goal"),
            "final_status": state.get("status"),
            "end_reason": state.get("end_reason"),
            "total_actions": len(actions),
            "action_counts": action_counts,
            "status_counts": status_counts,
            "unique_urls_visited": unique_urls,
            "error_count": len(errors),
            "recent_errors": errors[-5:],
            "log_tail": logs[-20:],
        }

    def heuristic_run_analysis(state: AgentState) -> tuple[str, str]:
        actions = state.get("action_history", [])
        total = len(actions)
        success_count = sum(1 for a in actions if a.get("success"))
        urls = []
        for a in actions:
            u = a.get("url")
            if u and u not in urls:
                urls.append(u)
        recent = actions[-5:]
        recent_text = "; ".join(
            f"step {a.get('step')}: {a.get('action_type')} @ {a.get('url')}"
            for a in recent
        ) or "No actions recorded."
        run = (
            f"Goal: {state.get('goal')}\n"
            f"Status: {state.get('status')} ({state.get('end_reason')})\n"
            f"Actions executed: {total}, successful actions: {success_count}\n"
            f"Unique URLs visited: {len(urls)}\n"
            f"Recent path: {recent_text}\n"
            "Note: This report is heuristic because the postmortem LLM call was unavailable."
        )
        recs = (
            "1. Add stronger navigation targeting in prompts (prefer explicit link text before repeated scrolling).\n"
            "2. Add recovery heuristics after 2 failed/unchanged page interactions (try alternate nav path).\n"
            "3. Log and surface click coordinates and observed destination URL deltas for debugging.\n"
            "4. Consider reducing postmortem token usage with deduplicated pages and shorter HTML excerpts."
        )
        return run, recs

    def heuristic_html_analysis(goal: str, pages: list[dict]) -> tuple[str, str]:
        if not pages:
            return (
                "No HTML captures were available for analysis.",
                "Capture HTML at each step and retry postmortem.",
            )
        lines = []
        for page in pages:
            html = page.get("html", "") or ""
            url = page.get("url", "")
            has_header = "<header" in html.lower()
            has_nav = "<nav" in html.lower()
            has_main = "<main" in html.lower()
            lines.append(
                f"{url}: semantic header/nav/main present={has_header}/{has_nav}/{has_main}, "
                f"html_len={len(html)}"
            )
        analysis = (
            f"Heuristic HTML analysis for goal '{goal}':\n"
            + "\n".join(lines[:10])
            + "\nNote: LLM HTML review was unavailable, so this is a structural fallback."
        )
        recs = (
            "1. Ensure semantic landmarks (`header`, `nav`, `main`) on key pages.\n"
            "2. Add clear researcher/help entry points in global navigation.\n"
            "3. Include page-level headings that map to user intents (e.g., trends methodology).\n"
            "4. Provide direct links to methodology explanations from report/subscription pages."
        )
        return analysis, recs

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

    async def pm_analyze_run(state: AgentState):
        await log_event(state, "info", "Postmortem run analysis started")
        log_rows = await list_run_logs(db, state["session_id"])
        logs = [dict(r) for r in log_rows]
        run_facts = build_run_facts(state, logs)
        try:
            llm = get_llm_client(state["provider"])
            prompt = (
                "You are a post-mortem analyst for a web testing agent. "
                "Analyze the run outcome, highlight success/failure points, and produce actionable recommendations. "
                "You MUST ground analysis in the provided RUN_FACTS and should not contradict them. "
                "Return JSON: {run_analysis: string, recommendations: string}."
            )
            user = json.dumps(
                {
                    "RUN_FACTS": run_facts,
                    "memory": state.get("memory", {}),
                    "actions": state.get("action_history", []),
                }
            )
            result = llm.generate_action(
                system_prompt=prompt,
                user_prompt=user,
                images=[],
                schema=PostmortemRunOutput,
                temperature=0.2,
                model=state["model"],
            )
            state["postmortem_run_analysis"] = (
                format_run_facts(run_facts)
                + "\n\nAnalysis:\n"
                + result.run_analysis
            )
            state["postmortem_recommendations"] = result.recommendations
            await log_event(state, "info", "Postmortem run analysis complete")
        except Exception as exc:
            run, recs = heuristic_run_analysis(state)
            state["postmortem_run_analysis"] = run
            state["postmortem_recommendations"] = recs
            await log_event(state, "warning", "Postmortem run analysis fallback used", str(exc))
        return state

    async def pm_analyze_html(state: AgentState):
        await log_event(state, "info", "Postmortem HTML analysis started")
        html_rows = await list_html_captures(db, state["session_id"])
        dedup_pages: dict[str, str] = {}
        for row in html_rows:
            dedup_pages[row["url"]] = row["html"]
        pages = [{"url": u, "html": h} for u, h in dedup_pages.items()]
        try:
            llm = get_llm_client(state["provider"])
            prompt = (
                "You are a UX + technical reviewer. Analyze each page's HTML in order and provide detailed "
                "design and technical recommendations. Return JSON: {html_analysis: string, recommendations: string}."
            )
            user = json.dumps({"goal": state["goal"], "pages": pages})
            result = llm.generate_action(
                system_prompt=prompt,
                user_prompt=user,
                images=[],
                schema=PostmortemHtmlOutput,
                temperature=0.2,
                model=state["model"],
            )
            state["postmortem_html_analysis"] = result.html_analysis
            state["postmortem_recommendations"] = result.recommendations
            await log_event(state, "info", "Postmortem HTML analysis complete", f"pages={len(pages)}")
        except Exception as exc:
            html_analysis, recs = heuristic_html_analysis(state["goal"], pages)
            state["postmortem_html_analysis"] = html_analysis
            if not state.get("postmortem_recommendations"):
                state["postmortem_recommendations"] = recs
            await log_event(state, "warning", "Postmortem HTML analysis fallback used", str(exc))
        return state

    async def save(state: AgentState):
        await save_postmortem(
            db,
            session_id=state["session_id"],
            run_analysis=state.get("postmortem_run_analysis") or "",
            html_analysis=state.get("postmortem_html_analysis") or "",
            recommendations=state.get("postmortem_recommendations") or "",
        )
        emit({
            "type": "postmortem",
            "data": {
                "run_analysis": state.get("postmortem_run_analysis"),
                "html_analysis": state.get("postmortem_html_analysis"),
                "recommendations": state.get("postmortem_recommendations"),
            },
        })
        await log_event(state, "info", "Postmortem report saved")
        return state

    graph = StateGraph(AgentState)
    graph.add_node("pm_analyze_run", pm_analyze_run)
    graph.add_node("pm_analyze_html", pm_analyze_html)
    graph.add_node("save", save)
    graph.set_entry_point("pm_analyze_run")
    graph.add_edge("pm_analyze_run", "pm_analyze_html")
    graph.add_edge("pm_analyze_html", "save")
    graph.add_edge("save", END)

    return graph.compile()


async def run_postmortem(*, db, state: AgentState, emit: Callable[[dict], None]):
    graph = build_postmortem_graph(db, emit)
    await graph.ainvoke(state)
