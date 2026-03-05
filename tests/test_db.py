import uuid
import json
import aiosqlite
import config
from database import queries


async def test_db_crud(temp_db):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        user_id = str(uuid.uuid4())
        await queries.create_user(db, user_id=user_id, email="a@example.com", password_hash="x")
        user = await queries.get_user_by_id(db, user_id)
        assert user["email"] == "a@example.com"

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
            config={"mode": "desktop", "max_steps": 5, "stop_on_first_error": False},
        )
        session = await queries.get_session(db, session_id)
        assert session["goal"] == "test"

        screenshot_id = await queries.insert_screenshot(
            db,
            session_id=session_id,
            url="https://example.com",
            image_data=b"png",
            action_taken="initialize",
            step_number=0,
        )
        s = await queries.get_screenshot(db, screenshot_id)
        assert s["id"] == screenshot_id

        html_id = await queries.insert_html_capture(
            db,
            session_id=session_id,
            url="https://example.com",
            html="<html></html>",
            step_number=0,
        )
        assert html_id

        await queries.insert_action(
            db,
            session_id=session_id,
            step_number=1,
            action_type="click",
            action_params={"x": 1, "y": 2},
            intent="Open details panel",
            reasoning="test",
            action_result='{"ok":true}',
            screenshot_id=screenshot_id,
            success=True,
            error_message=None,
        )
        actions = await queries.list_actions(db, session_id)
        assert len(actions) == 1
        assert actions[0]["intent"] == "Open details panel"
        assert actions[0]["action_result"] == '{"ok":true}'

        await queries.upsert_memory(db, session_id=session_id, key="k", value="v")
        await queries.upsert_memory(db, session_id=session_id, key="k", value="v2")
        memory = await queries.get_memory(db, session_id)
        assert memory["k"] == "v2"

        await queries.save_postmortem(db, session_id=session_id, run_analysis="a", html_analysis="b", recommendations=json.dumps({"ok": True}))
        pm = await queries.get_postmortem(db, session_id)
        assert pm["run_analysis"] == "a"
