import hashlib
from typing import List, Dict


def fingerprint(action_type: str, action_params: dict) -> str:
    raw = f"{action_type}:{sorted(action_params.items())}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def _signature(record: dict) -> str:
    return fingerprint(record.get("action_type", ""), record.get("action_params", {}) or {})


def is_looping(fingerprints: List[str], rules: Dict, action_history: List[dict] | None = None) -> bool:
    if not fingerprints:
        return False

    action_history = action_history or []
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
