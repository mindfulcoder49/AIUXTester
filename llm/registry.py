from typing import Dict, Any

from config import MODEL_REGISTRY, DEFAULT_CONFIG, FREE_KEYS, BASIC_KEYS, PRO_ONLY_KEYS


class ConfigError(ValueError):
    pass


def get_allowed_models(provider: str, tier: str):
    provider_map = MODEL_REGISTRY.get(provider)
    if not provider_map:
        return []
    return provider_map.get(tier, [])


def validate_provider_model(provider: str, model: str, tier: str) -> None:
    allowed = get_allowed_models(provider, tier)
    if model not in allowed:
        raise ConfigError(f"Model '{model}' not allowed for tier '{tier}' and provider '{provider}'")


def merge_config_with_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    merged = DEFAULT_CONFIG.copy()
    merged.update(config or {})
    return merged


def validate_config_for_tier(config: Dict[str, Any], tier: str) -> Dict[str, Any]:
    config = config or {}

    if tier == "free":
        allowed_keys = FREE_KEYS
    elif tier == "basic":
        allowed_keys = FREE_KEYS | BASIC_KEYS
    elif tier == "pro":
        allowed_keys = FREE_KEYS | BASIC_KEYS | PRO_ONLY_KEYS
    else:
        raise ConfigError("Invalid tier")

    extra_keys = set(config.keys()) - (FREE_KEYS | BASIC_KEYS | PRO_ONLY_KEYS)
    if extra_keys:
        raise ConfigError(f"Unknown config keys: {sorted(extra_keys)}")

    disallowed = set(config.keys()) - allowed_keys
    if disallowed:
        raise ConfigError(f"Config keys not allowed for tier '{tier}': {sorted(disallowed)}")

    merged = merge_config_with_defaults(config)
    # Only keep allowed keys in final config snapshot
    return {k: merged[k] for k in allowed_keys}
