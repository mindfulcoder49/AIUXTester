import json

import agent.test_graph as test_graph


def test_compute_recursion_limit_scales_with_max_steps():
    assert test_graph.compute_recursion_limit(1) == 50
    assert test_graph.compute_recursion_limit(10) == 80
    assert test_graph.compute_recursion_limit(50) == 320


async def test_run_test_session_passes_recursion_limit(monkeypatch):
    seen = {}

    class FakeGraph:
        async def ainvoke(self, state, config=None):
            seen["config"] = config or {}
            return state

    monkeypatch.setattr(test_graph, "build_graph", lambda db, emit: FakeGraph())

    session_row = {
        "id": "s1",
        "user_id": "u1",
        "goal": "g",
        "start_url": "https://example.com",
        "mode": "desktop",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "config_json": json.dumps({"max_steps": 42}),
    }

    await test_graph.run_test_session(db=None, session_row=session_row, user_tier="pro", emit=lambda _e: None)

    assert seen["config"]["recursion_limit"] == test_graph.compute_recursion_limit(42)
