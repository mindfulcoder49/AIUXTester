import uuid
import aiosqlite
import config

import agent.postmortem_graph as pm
from database import queries


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def generate_action(self, *, system_prompt, user_prompt, images, schema, temperature, model):
        self.calls += 1
        if self.calls == 1:
            return schema.model_validate({"run_analysis": "ok", "recommendations": "rec"})
        return schema.model_validate({"html_analysis": "ok", "recommendations": "rec"})


async def test_postmortem(monkeypatch, temp_db):
    fake_llm = FakeLLM()
    monkeypatch.setattr(pm, "get_llm_client", lambda provider: fake_llm)

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        user_id = str(uuid.uuid4())
        await queries.create_user(db, user_id=user_id, email="x2@example.com", password_hash="x")
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
            config={"mode": "desktop", "max_steps": 3, "stop_on_first_error": False},
        )
        await queries.insert_html_capture(db, session_id=session_id, url="https://example.com", html="<html></html>", step_number=0)

        state = {
            "session_id": session_id,
            "goal": "test",
            "status": "completed",
            "end_reason": "done",
            "memory": {},
            "action_history": [],
            "provider": "openai",
            "model": "gpt-4o-mini",
        }

        await pm.run_postmortem(db=db, state=state, emit=lambda e: None)
        report = await queries.get_postmortem(db, session_id)
        assert report["run_analysis"] == "ok"
