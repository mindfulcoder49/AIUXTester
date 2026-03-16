from typing import TypedDict, Optional, Literal, Dict, List
from pydantic import BaseModel, model_validator


class ActionRecord(TypedDict):
    step: int
    action_type: str
    action_params: dict
    executed_on_url: Optional[str]
    intent: Optional[str]
    reasoning: str
    execution_result: Optional[str]
    action_outcome: Optional[str]
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
    current_html: str
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
    last_action: Optional[dict]

    postmortem_run_analysis: Optional[str]
    postmortem_html_analysis: Optional[str]
    postmortem_recommendations: Optional[str]


class AgentAction(BaseModel):
    action: Literal[
        "execute_js",
        "navigate",
        "save_to_memory",
        "finish",
        "fail",
        "give_up",
    ]
    params: dict
    intent: Optional[str] = None
    reasoning: str
    last_action_result: Optional[str] = None
    memory_update: Optional[Dict[str, str]] = None

    @model_validator(mode="after")
    def validate_params_for_action(self):
        params = self.params or {}
        if self.action == "execute_js" and not isinstance(params.get("script"), str):
            raise ValueError("execute_js requires params.script (string)")
        if self.action == "navigate" and not isinstance(params.get("url"), str):
            raise ValueError("navigate requires params.url (string)")
        if self.action == "save_to_memory":
            if not isinstance(params.get("key"), str) or not isinstance(params.get("value"), str):
                raise ValueError("save_to_memory requires params.key and params.value (strings)")
        if self.action in {"finish"} and not isinstance(params.get("summary"), str):
            raise ValueError("finish requires params.summary (string)")
        if self.action in {"fail", "give_up"} and not isinstance(params.get("reason"), str):
            raise ValueError(f"{self.action} requires params.reason (string)")
        return self
