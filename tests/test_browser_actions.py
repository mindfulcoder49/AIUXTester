import pytest

from browser.actions import execute_javascript
from browser.manager import BrowserManager


pytestmark = pytest.mark.asyncio


async def _open_blank_page():
    manager = BrowserManager()
    try:
        await manager.launch("desktop")
    except Exception as exc:
        pytest.skip(f"Chromium launch unavailable: {exc}")
    page = manager.page
    assert page is not None
    await page.goto("data:text/html,<html><head><title>Example</title></head><body>Hi</body></html>")
    return manager, page


async def test_execute_javascript_returns_expression_result():
    manager, page = await _open_blank_page()
    try:
        success, error, result = await execute_javascript(
            page,
            "(() => ({ title: document.title, text: document.body.innerText.trim() }))()",
        )
        assert success is True
        assert error is None
        assert result == '{"title":"Example","text":"Hi"}'
    finally:
        await manager.close()


async def test_execute_javascript_returns_statement_result():
    manager, page = await _open_blank_page()
    try:
        success, error, result = await execute_javascript(
            page,
            "const title = document.title; return { title, seen: true };",
        )
        assert success is True
        assert error is None
        assert result == '{"title":"Example","seen":true}'
    finally:
        await manager.close()
