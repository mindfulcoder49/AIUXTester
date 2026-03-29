from utils.loop_detector import fingerprint, is_looping


def _record(
    step: int,
    action: str,
    params: dict | None = None,
    url: str = "https://example.com",
    execution_result: str | None = None,
):
    return {
        "step": step,
        "action_type": action,
        "action_params": params or {},
        "reasoning": "",
        "url": url,
        "success": True,
        "error": None,
        "execution_result": execution_result,
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


def test_does_not_flag_when_form_filling_progress_is_happening():
    history = [
        _record(1, "click", {"x": 500, "y": 210}),
        _record(2, "type", {"text": "John"}),
        _record(3, "click", {"x": 800, "y": 210}),
        _record(4, "type", {"text": "Doe"}),
        _record(5, "click", {"x": 640, "y": 335}),
        _record(6, "click", {"x": 640, "y": 335}),
        _record(7, "click", {"x": 640, "y": 335}),
        _record(8, "click", {"x": 640, "y": 335}),
    ]
    fps = [fingerprint(h["action_type"], h["action_params"]) for h in history]
    assert is_looping(fps, {}, history) is False


def test_register_flow_with_repeated_clicks_gets_extra_runway():
    history = [
        _record(1, "click", {"x": 500, "y": 210}, "https://example.com/register"),
        _record(2, "type", {"text": "Alex"}, "https://example.com/register"),
        _record(3, "click", {"x": 800, "y": 210}, "https://example.com/register"),
        _record(4, "type", {"text": "Smith"}, "https://example.com/register"),
        _record(5, "click", {"x": 640, "y": 320}, "https://example.com/register"),
        _record(6, "click", {"x": 640, "y": 320}, "https://example.com/register"),
        _record(7, "click", {"x": 640, "y": 320}, "https://example.com/register"),
        _record(8, "click", {"x": 640, "y": 320}, "https://example.com/register"),
    ]
    fps = [fingerprint(h["action_type"], h["action_params"]) for h in history]
    assert is_looping(fps, {}, history) is False


def test_flags_repeated_execute_js_inspection_with_no_new_result():
    history = [
        _record(1, "execute_js", {"script": "(() => document.title)()"}, execution_result=None),
        _record(2, "execute_js", {"script": "(() => document.title)()"}, execution_result=None),
        _record(3, "execute_js", {"script": "(() => document.title)()"}, execution_result=None),
    ]
    fps = [fingerprint(h["action_type"], h["action_params"]) for h in history]
    assert is_looping(fps, {}, history) is True


def test_does_not_flag_execute_js_when_results_change():
    history = [
        _record(1, "execute_js", {"script": "(() => document.title)()"}, execution_result='{"title":"A"}'),
        _record(2, "execute_js", {"script": "(() => location.href)()"}, execution_result='{"href":"https://example.com/a"}'),
        _record(3, "execute_js", {"script": "(() => document.body.innerText)()"}, execution_result='{"body":"Next"}'),
    ]
    fps = [fingerprint(h["action_type"], h["action_params"]) for h in history]
    assert is_looping(fps, {}, history) is False
