from llm.registry import get_allowed_models, validate_provider_model, ConfigError
import pytest


def test_gemini_tiers_only_expose_flash_lite_to_basic_users():
    assert get_allowed_models("gemini", "free") == ["gemini-2.5-flash-lite"]
    assert get_allowed_models("gemini", "basic") == ["gemini-2.5-flash-lite"]
    assert get_allowed_models("gemini", "pro") == [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ]


def test_claude_tiers_only_expose_haiku_to_basic_users():
    assert get_allowed_models("claude", "free") == ["claude-haiku-4-5"]
    assert get_allowed_models("claude", "basic") == ["claude-haiku-4-5"]
    assert get_allowed_models("claude", "pro") == [
        "claude-haiku-4-5",
        "claude-sonnet-4-6",
        "claude-opus-4-6",
    ]


def test_basic_users_cannot_pick_large_gemini_or_claude_models():
    with pytest.raises(ConfigError):
        validate_provider_model("gemini", "gemini-2.5-pro", "basic")
    with pytest.raises(ConfigError):
        validate_provider_model("claude", "claude-sonnet-4-6", "basic")


def test_pro_users_can_pick_large_gemini_and_claude_models():
    validate_provider_model("gemini", "gemini-2.5-pro", "pro")
    validate_provider_model("claude", "claude-opus-4-6", "pro")
