from typing import Tuple
from playwright.async_api import Page


async def scroll_down(page: Page, pixels: int) -> Tuple[bool, str | None]:
    try:
        await page.mouse.wheel(0, pixels)
        return True, None
    except Exception as e:
        return False, str(e)


async def scroll_up(page: Page, pixels: int) -> Tuple[bool, str | None]:
    try:
        await page.mouse.wheel(0, -pixels)
        return True, None
    except Exception as e:
        return False, str(e)


async def swipe_left(page: Page, x: int, y: int, distance: int) -> Tuple[bool, str | None]:
    try:
        await page.touchscreen.tap(x, y)
        await page.mouse.move(x, y)
        await page.mouse.down()
        await page.mouse.move(x - distance, y)
        await page.mouse.up()
        return True, None
    except Exception as e:
        return False, str(e)


async def swipe_right(page: Page, x: int, y: int, distance: int) -> Tuple[bool, str | None]:
    try:
        await page.touchscreen.tap(x, y)
        await page.mouse.move(x, y)
        await page.mouse.down()
        await page.mouse.move(x + distance, y)
        await page.mouse.up()
        return True, None
    except Exception as e:
        return False, str(e)


async def click(page: Page, x: int, y: int) -> Tuple[bool, str | None]:
    try:
        await page.mouse.click(x, y)
        return True, None
    except Exception as e:
        return False, str(e)


async def click_and_drag(page: Page, x1: int, y1: int, x2: int, y2: int) -> Tuple[bool, str | None]:
    try:
        await page.mouse.move(x1, y1)
        await page.mouse.down()
        await page.mouse.move(x2, y2)
        await page.mouse.up()
        return True, None
    except Exception as e:
        return False, str(e)


async def type_text(page: Page, text: str) -> Tuple[bool, str | None]:
    try:
        await page.keyboard.type(text)
        return True, None
    except Exception as e:
        return False, str(e)


async def navigate(page: Page, url: str) -> Tuple[bool, str | None]:
    try:
        await page.goto(url, wait_until="domcontentloaded")
        return True, None
    except Exception as e:
        return False, str(e)


async def execute_javascript(page: Page, script: str) -> Tuple[bool, str | None, str | None]:
    try:
        result = await page.evaluate(
            """
            (jsCode) => {
              const fn = new Function(jsCode);
              const out = fn();
              if (out === undefined || out === null) return null;
              if (typeof out === "string") return out;
              try {
                return JSON.stringify(out);
              } catch (_) {
                return String(out);
              }
            }
            """,
            script,
        )
        return True, None, result
    except Exception as e:
        return False, str(e), None
