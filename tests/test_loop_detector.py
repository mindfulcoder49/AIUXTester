from utils.loop_detector import fingerprint, is_looping


def _record(step: int, action: str, params: dict | None = None, url: str = "https://example.com"):
    return {
        "step": step,
        "action_type": action,
        "action_params": params or {},
        "reasoning": "",
        "url": url,
        "success": True,
        "error": None,
    }


def test_does_not_flag_short_scroll_sequence():
    history = [
        _record(1, "scroll_down", {"pixels": 300}),
        _record(2, "scroll_down", {"pixels": 300}),
        _record(3, "scroll_down", {"pixels": 300}),
        _record(4, "scroll_down", {"pixels": 300}),
    ]
    fps = [fingerprint(h["action_type"], h["action_params"]) for h in history]
    assert is_looping(fps, {}, history) is False


def test_flags_long_repeated_passive_actions():
    history = [_record(i, "scroll_down", {"pixels": 300}) for i in range(1, 11)]
    fps = [fingerprint(h["action_type"], h["action_params"]) for h in history]
    assert is_looping(fps, {}, history) is True


def test_flags_repeated_non_passive_actions_earlier():
    history = [_record(i, "click", {"x": 10, "y": 10}) for i in range(1, 9)]
    fps = [fingerprint(h["action_type"], h["action_params"]) for h in history]
    assert is_looping(fps, {}, history) is True


def test_requires_same_url_for_repeat_detection():
    history = [
        _record(1, "click", {"x": 10, "y": 10}, "https://example.com"),
        _record(2, "click", {"x": 10, "y": 10}, "https://example.com/a"),
        _record(3, "click", {"x": 10, "y": 10}, "https://example.com/b"),
        _record(4, "click", {"x": 10, "y": 10}, "https://example.com/c"),
        _record(5, "click", {"x": 10, "y": 10}, "https://example.com/d"),
        _record(6, "click", {"x": 10, "y": 10}, "https://example.com/e"),
        _record(7, "click", {"x": 10, "y": 10}, "https://example.com/f"),
        _record(8, "click", {"x": 10, "y": 10}, "https://example.com/g"),
    ]
    fps = [fingerprint(h["action_type"], h["action_params"]) for h in history]
    assert is_looping(fps, {}, history) is False
