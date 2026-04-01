import os
from dataclasses import dataclass
from typing import Dict, List, Literal
from pathlib import Path
from dotenv import load_dotenv

# Load local .env automatically for app/runtime execution.
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

APP_NAME = "AIUXTester"

DATABASE_PATH = os.getenv("DATABASE_PATH", "./aiuxtester.db")
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()  # sqlite | mariadb
DATABASE_URL = os.getenv("DATABASE_URL", "")
QUEUE_MODE = os.getenv("QUEUE_MODE", "inline")  # inline | redis
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
SESSION_WATCHDOG_INTERVAL_SECONDS = int(os.getenv("SESSION_WATCHDOG_INTERVAL_SECONDS", "30"))
SESSION_WATCHDOG_STALE_SECONDS = int(os.getenv("SESSION_WATCHDOG_STALE_SECONDS", "300"))
BROWSER_LAUNCH_TIMEOUT_MS = int(os.getenv("BROWSER_LAUNCH_TIMEOUT_MS", "45000"))
BROWSER_PAGE_TIMEOUT_MS = int(os.getenv("BROWSER_PAGE_TIMEOUT_MS", "60000"))

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

VIEWPORT_DESKTOP = {"width": 1280, "height": 800}
VIEWPORT_MOBILE = {"width": 390, "height": 844}

USERAGENT_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
USERAGENT_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

Tier = Literal["free", "basic", "pro"]
Provider = Literal["openai", "gemini", "claude"]

TIER_LIMITS = {
    "free": {
        "max_steps": 50,
        "max_history_actions": 5,
        "loop_detection_enabled": True,
        "loop_detection_window": 8,
        "postmortem_depth": "standard",
        "screenshot_quality": "png",
    },
    "basic": {
        "max_steps": 150,
        "max_history_actions": 10,
        "loop_detection_enabled": True,
        "loop_detection_window": 12,
        "postmortem_depth": "standard",
        "screenshot_quality": "png",
    },
    "pro": {
        "max_steps": 500,
        "max_history_actions": 20,
        "loop_detection_enabled": True,
        "loop_detection_window": 15,
        "postmortem_depth": "deep",
        "screenshot_quality": "png",
    },
}

PRO_ONLY_KEYS = {
    "loop_detection_rules",
    "memory_injection_format",
    "screenshot_quality",
    "action_retry_policy",
    "postmortem_depth",
    "custom_system_prompt_preamble",
}

BASIC_KEYS = {
    "max_history_actions",
    "loop_detection_enabled",
    "loop_detection_window",
}

FREE_KEYS = {
    "mode",
    "max_steps",
    "stop_on_first_error",
}

DEFAULT_CONFIG = {
    "mode": "desktop",
    "max_steps": 50,
    "stop_on_first_error": False,
    "max_history_actions": 5,
    "loop_detection_enabled": True,
    "loop_detection_window": 8,
    "loop_detection_rules": {
        "repeat_single": 4,
        "repeat_alternating": 3,
        "min_actions_before_loop": 8,
        "passive_actions": ["scroll_down", "scroll_up", "swipe_left", "swipe_right"],
        "passive_repeat_single": 10,
        "passive_repeat_alternating": 5,
        "stale_url_actions": 12,
    },
    "memory_injection_format": "kv_list",
    "screenshot_quality": "png",
    "action_retry_policy": {"retries": 1, "backoff_ms": 500},
    "postmortem_depth": "standard",
    "custom_system_prompt_preamble": "",
}

MODEL_REGISTRY: Dict[str, Dict[str, List[str]]] = {
    "openai": {
        "free": ["gpt-5-mini", "gpt-4o-mini"],
        "basic": ["gpt-4o-mini", "gpt-4o"],
        "pro": ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-5-mini", "gpt-5"],
    },
    "gemini": {
        "free": ["gemini-1.5-flash"],
        "basic": ["gemini-1.5-flash", "gemini-1.5-pro"],
        "pro": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-pro"],
    },
    "claude": {
        "free": ["claude-3-haiku-20240307"],
        "basic": ["claude-3-haiku-20240307", "claude-3-sonnet-20240229"],
        "pro": ["claude-3-haiku-20240307", "claude-3-sonnet-20240229", "claude-3-opus-20240229"],
    },
}
