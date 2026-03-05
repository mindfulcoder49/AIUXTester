import json
import uuid
import aiosqlite
import config

import agent.test_graph as test_graph
from database import queries


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def generate_action(self, *, system_prompt, user_prompt, images, schema, temperature, model):
        self.calls += 1
        if self.calls == 1:
            return schema.model_validate({
                "action": "click",
                "params": {"x": 10, "y": 10},
                "reasoning": "click",
            })
        return schema.model_validate({
            "action": "finish",
            "params": {"summary": "done"},
            "reasoning": "done",
        })


class FakeLLMGiveUp:
    def generate_action(self, *, system_prompt, user_prompt, images, schema, temperature, model):
        return schema.model_validate({
            "action": "give_up",
            "params": {"reason": "No meaningful progress after repeated attempts"},
            "intent": "Stop safely",
            "reasoning": "Repeated attempts are not making progress.",
        })


class FakeBrowserManager:
    def __init__(self):
        self._page = object()

    async def launch(self, mode):
        return None, self._page

    async def close(self):
        return None

    @property
    def page(self):
        return self._page

    async def screenshot(self):
        return b"png"

    async def screenshot_with_markers(self, markers):
        return b"png"

    async def get_html(self):
        return "<html></html>"

    async def get_url(self):
        return "https://example.com"


async def test_run_graph(monkeypatch, temp_db):
    monkeypatch.setattr(test_graph, "BrowserManager", FakeBrowserManager)
    fake_llm = FakeLLM()
    monkeypatch.setattr(test_graph, "get_llm_client", lambda provider: fake_llm)

    async def ok_action(*args, **kwargs):
        return True, None

    monkeypatch.setattr(test_graph.browser_actions, "click", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "navigate", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "scroll_down", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "scroll_up", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "swipe_left", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "swipe_right", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "click_and_drag", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "type_text", ok_action)

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        user_id = str(uuid.uuid4())
        await queries.create_user(db, user_id=user_id, email="x@example.com", password_hash="x")
        session_id = str(uuid.uuid4())
        await queries.create_session(
            db,
            session_id=session_id,
            user_id=user_id,
            goal="test",
            start_url="https://example.com",
            mode="desktop",
            provider="openai",
            model="gpt-4o-mini",
            config={"mode": "desktop", "max_steps": 3, "stop_on_first_error": False, "max_history_actions": 5, "loop_detection_enabled": True, "loop_detection_window": 5},
        )
        session_row = await queries.get_session(db, session_id)
        state = await test_graph.run_test_session(db=db, session_row=session_row, user_tier="pro", emit=lambda e: None)
        assert state["status"] == "completed"
        actions = await queries.list_actions(db, session_id)
        assert len(actions) >= 1


async def test_run_graph_give_up(monkeypatch, temp_db):
    monkeypatch.setattr(test_graph, "BrowserManager", FakeBrowserManager)
    monkeypatch.setattr(test_graph, "get_llm_client", lambda provider: FakeLLMGiveUp())

    async def ok_action(*args, **kwargs):
        return True, None

    monkeypatch.setattr(test_graph.browser_actions, "click", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "navigate", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "scroll_down", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "scroll_up", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "swipe_left", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "swipe_right", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "click_and_drag", ok_action)
    monkeypatch.setattr(test_graph.browser_actions, "type_text", ok_action)

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        user_id = str(uuid.uuid4())
        await queries.create_user(db, user_id=user_id, email="y@example.com", password_hash="x")
        session_id = str(uuid.uuid4())
        await queries.create_session(
            db,
            session_id=session_id,
            user_id=user_id,
            goal="test",
            start_url="https://example.com",
            mode="desktop",
            provider="openai",
            model="gpt-4o-mini",
            config={"mode": "desktop", "max_steps": 10, "stop_on_first_error": False, "max_history_actions": 5, "loop_detection_enabled": True, "loop_detection_window": 5},
        )
        session_row = await queries.get_session(db, session_id)
        state = await test_graph.run_test_session(db=db, session_row=session_row, user_tier="pro", emit=lambda e: None)
        assert state["status"] == "failed"
        assert "No meaningful progress" in (state["end_reason"] or "")
