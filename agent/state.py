from typing import TypedDict, Optional, Literal, Dict, List
from pydantic import BaseModel


class ActionRecord(TypedDict):
    step: int
    action_type: str
    action_params: dict
    intent: Optional[str]
    reasoning: str
    url: str
    success: bool
    error: Optional[str]


class AgentState(TypedDict):
    session_id: str
    user_id: str
    goal: str
    start_url: str
    mode: Literal["desktop", "mobile"]

    provider: str
    model: str
    tier: Literal["free", "basic", "pro"]
    run_config: Dict

    current_url: str
    current_screenshot: str
    current_screenshot_id: int
    current_step: int

    memory: Dict[str, str]
    action_history: List[ActionRecord]
    recent_action_fingerprints: List[str]
    pages_visited: List[str]

    status: Literal["running", "completed", "failed", "stopped", "loop_detected"]
    end_reason: Optional[str]
    next_action: Optional[dict]

    postmortem_run_analysis: Optional[str]
    postmortem_html_analysis: Optional[str]
    postmortem_recommendations: Optional[str]


class AgentAction(BaseModel):
    action: Literal[
        "scroll_down",
        "scroll_up",
        "swipe_left",
        "swipe_right",
        "click",
        "click_and_drag",
        "type",
        "navigate",
        "save_to_memory",
        "finish",
        "fail",
    ]
    params: dict
    intent: Optional[str] = None
    reasoning: str
    memory_update: Optional[Dict[str, str]] = None
