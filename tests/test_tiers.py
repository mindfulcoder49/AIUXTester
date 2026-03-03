import pytest
from llm.registry import validate_config_for_tier, ConfigError


def test_free_tier_config():
    cfg = validate_config_for_tier({"mode": "desktop", "max_steps": 10}, "free")
    assert "mode" in cfg
    with pytest.raises(ConfigError):
        validate_config_for_tier({"loop_detection_enabled": True}, "free")


def test_basic_tier_config():
    cfg = validate_config_for_tier({"loop_detection_enabled": True, "max_history_actions": 8}, "basic")
    assert "loop_detection_enabled" in cfg
    with pytest.raises(ConfigError):
        validate_config_for_tier({"postmortem_depth": "deep"}, "basic")


def test_pro_tier_config():
    cfg = validate_config_for_tier({"postmortem_depth": "deep"}, "pro")
    assert "postmortem_depth" in cfg
