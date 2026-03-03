from typing import Literal, Optional, Tuple
from pathlib import Path
import os
from playwright.async_api import async_playwright, Browser, Page
from playwright_stealth import stealth_async

from config import VIEWPORT_DESKTOP, VIEWPORT_MOBILE, USERAGENT_DESKTOP, USERAGENT_MOBILE


class BrowserManager:
    def __init__(self):
        self._pw = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    async def launch(self, mode: Literal["desktop", "mobile"]) -> Tuple[Browser, Page]:
        self._pw = await async_playwright().start()
        launch_kwargs = {"headless": True}
        executable = self._find_chromium_executable()
        if executable:
            launch_kwargs["executable_path"] = executable
        self._browser = await self._pw.chromium.launch(**launch_kwargs)

        if mode == "mobile":
            context = await self._browser.new_context(
                viewport=VIEWPORT_MOBILE,
                user_agent=USERAGENT_MOBILE,
                is_mobile=True,
                has_touch=True,
                device_scale_factor=3,
            )
        else:
            context = await self._browser.new_context(
                viewport=VIEWPORT_DESKTOP,
                user_agent=USERAGENT_DESKTOP,
                is_mobile=False,
                has_touch=False,
                device_scale_factor=1,
            )

        self._page = await context.new_page()
        await stealth_async(self._page)
        return self._browser, self._page

    def _find_chromium_executable(self) -> Optional[str]:
        configured = os.getenv("CHROMIUM_EXECUTABLE_PATH", "").strip()
        if configured and Path(configured).exists():
            return configured

        cache_dir = Path.home() / ".cache" / "ms-playwright"
        if not cache_dir.exists():
            return None

        candidates = sorted(cache_dir.glob("chromium-*/chrome-linux/chrome"), reverse=True)
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    @property
    def page(self) -> Optional[Page]:
        return self._page

    def _require_page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not started")
        return self._page

    async def screenshot(self) -> bytes:
        return await self._require_page().screenshot(full_page=False, type="png")

    async def screenshot_with_markers(self, markers: list[dict]) -> bytes:
        page = self._require_page()
        await page.evaluate(
            """
            (markers) => {
              const old = document.getElementById("__aiuxtester_action_overlay");
              if (old) old.remove();

              const overlay = document.createElement("div");
              overlay.id = "__aiuxtester_action_overlay";
              overlay.style.position = "fixed";
              overlay.style.inset = "0";
              overlay.style.pointerEvents = "none";
              overlay.style.zIndex = "2147483647";

              const ns = "http://www.w3.org/2000/svg";
              const svg = document.createElementNS(ns, "svg");
              svg.setAttribute("width", "100%");
              svg.setAttribute("height", "100%");
              svg.style.position = "absolute";
              svg.style.inset = "0";

              for (const marker of markers) {
                const x = Number(marker.x || 0);
                const y = Number(marker.y || 0);
                const color = marker.color || "#d14343";

                const ring = document.createElement("div");
                ring.style.position = "absolute";
                ring.style.left = `${x - 12}px`;
                ring.style.top = `${y - 12}px`;
                ring.style.width = "24px";
                ring.style.height = "24px";
                ring.style.border = `3px solid ${color}`;
                ring.style.borderRadius = "50%";
                ring.style.boxShadow = "0 0 0 2px rgba(255,255,255,0.85)";
                overlay.appendChild(ring);

                const dot = document.createElement("div");
                dot.style.position = "absolute";
                dot.style.left = `${x - 4}px`;
                dot.style.top = `${y - 4}px`;
                dot.style.width = "8px";
                dot.style.height = "8px";
                dot.style.borderRadius = "50%";
                dot.style.background = color;
                overlay.appendChild(dot);

                const label = document.createElement("div");
                label.textContent = marker.label || `(${Math.round(x)}, ${Math.round(y)})`;
                label.style.position = "absolute";
                label.style.left = `${x + 14}px`;
                label.style.top = `${y - 14}px`;
                label.style.padding = "2px 6px";
                label.style.font = "600 12px monospace";
                label.style.color = "#fff";
                label.style.background = color;
                label.style.borderRadius = "4px";
                overlay.appendChild(label);
              }

              if (markers.length >= 2) {
                for (let i = 0; i < markers.length - 1; i++) {
                  const from = markers[i];
                  const to = markers[i + 1];
                  const line = document.createElementNS(ns, "line");
                  line.setAttribute("x1", String(Number(from.x || 0)));
                  line.setAttribute("y1", String(Number(from.y || 0)));
                  line.setAttribute("x2", String(Number(to.x || 0)));
                  line.setAttribute("y2", String(Number(to.y || 0)));
                  line.setAttribute("stroke", to.color || "#0f766e");
                  line.setAttribute("stroke-width", "3");
                  line.setAttribute("stroke-dasharray", "6 4");
                  svg.appendChild(line);
                }
              }

              overlay.appendChild(svg);
              document.body.appendChild(overlay);
            }
            """,
            markers,
        )
        shot = await page.screenshot(full_page=False, type="png")
        await page.evaluate(
            """
            () => {
              const old = document.getElementById("__aiuxtester_action_overlay");
              if (old) old.remove();
            }
            """
        )
        return shot

    async def get_html(self) -> str:
        return await self._require_page().content()

    async def get_url(self) -> str:
        return self._require_page().url
