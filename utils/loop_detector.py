import hashlib
from typing import List, Dict


def fingerprint(action_type: str, action_params: dict) -> str:
    raw = f"{action_type}:{sorted(action_params.items())}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def _signature(record: dict) -> str:
    return fingerprint(record.get("action_type", ""), record.get("action_params", {}) or {})


def _recent_form_progress(action_history: List[dict], lookback: int = 8) -> bool:
    if not action_history:
        return False
    tail = action_history[-lookback:]
    action_types = [a.get("action_type", "") for a in tail]
    typed = [a for a in tail if a.get("action_type") == "type" and a.get("success", True)]
    # If we are actively entering text and taking varied actions, treat it as progress.
    return bool(typed) and len(set(action_types)) >= 2


def _active_form_flow(action_history: List[dict], lookback: int = 12) -> bool:
    if not action_history:
        return False
    tail = action_history[-lookback:]
    joined_urls = " ".join((a.get("url") or "").lower() for a in tail)
    formy_url = any(token in joined_urls for token in ["/register", "/signup", "/sign-up", "/create-account"])
    typed_recently = any(a.get("action_type") == "type" for a in tail)
    clicked_recently = any(a.get("action_type") == "click" for a in tail)
    return formy_url and typed_recently and clicked_recently


def _repeated_execute_js_inspection(action_history: List[dict], repeat_count: int = 3) -> bool:
    if len(action_history) < repeat_count:
        return False

    tail = action_history[-repeat_count:]
    if any(a.get("action_type") != "execute_js" for a in tail):
        return False
    if not all(a.get("success", True) for a in tail):
        return False
    if len({a.get("url") for a in tail}) != 1:
        return False

    signatures = {_signature(a) for a in tail}
    normalized_results = {
        (a.get("execution_result") or "").strip()
        for a in tail
        if isinstance(a.get("execution_result"), str) or a.get("execution_result") is None
    }
    if len(normalized_results) <= 1:
        return True
    if len(signatures) == 1:
        return True
    return False


def is_looping(fingerprints: List[str], rules: Dict, action_history: List[dict] | None = None) -> bool:
    if not fingerprints:
        return False

    action_history = action_history or []
    if _repeated_execute_js_inspection(action_history):
        return True

    repeat_single = rules.get("repeat_single", 4)
    repeat_alternating = rules.get("repeat_alternating", 3)
    min_actions = rules.get("min_actions_before_loop", 8)
    passive_actions = set(rules.get("passive_actions", ["scroll_down", "scroll_up", "swipe_left", "swipe_right"]))
    passive_repeat_single = rules.get("passive_repeat_single", 10)
    passive_repeat_alternating = rules.get("passive_repeat_alternating", 5)
    stale_url_actions = rules.get("stale_url_actions", 12)

    # Avoid terminating short exploratory runs too early.
    if action_history and len(action_history) < min_actions:
        return False
    if _recent_form_progress(action_history):
        return False
    # Form completion often requires repeated same-page click/focus/type cycles.
    # Give these flows much more runway before declaring a loop.
    if _active_form_flow(action_history) and len(action_history) < 20:
        return False

    # Rule 1: same fingerprint repeated N times in window
    if len(fingerprints) >= repeat_single:
        tail = fingerprints[-repeat_single:]
        if len(set(tail)) == 1:
            if not action_history:
                return True
            history_tail = action_history[-repeat_single:]
            same_url = len({h.get("url") for h in history_tail}) == 1
            action_type = history_tail[-1].get("action_type", "")
            threshold = passive_repeat_single if action_type in passive_actions else repeat_single
            if same_url and len(fingerprints) >= threshold:
                return True

    # Rule 2: alternating pattern A,B,A,B...
    if len(fingerprints) >= repeat_alternating * 2:
        tail = fingerprints[-(repeat_alternating * 2):]
        if len(set(tail[::2])) == 1 and len(set(tail[1::2])) == 1 and tail[0] != tail[1]:
            if not action_history:
                return True
            history_tail = action_history[-(repeat_alternating * 2):]
            same_url = len({h.get("url") for h in history_tail}) == 1
            a_type = history_tail[0].get("action_type", "")
            b_type = history_tail[1].get("action_type", "")
            passive_pair = a_type in passive_actions and b_type in passive_actions
            threshold = passive_repeat_alternating if passive_pair else repeat_alternating
            if same_url and len(fingerprints) >= threshold * 2:
                return True

    # Rule 3: no progress on same URL for too many actions with low action diversity.
    if action_history and len(action_history) >= stale_url_actions:
        tail = action_history[-stale_url_actions:]
        if len({h.get("url") for h in tail}) == 1:
            unique_signatures = {_signature(h) for h in tail}
            if len(unique_signatures) <= 2:
                return True

    return False
