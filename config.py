"""
Feature flags for the GPU-Pool portal.

Source of truth is `config.yaml` in the app root (mounted to /app/config.yaml
in Docker). Every flag has an environment-variable override so a deployment can
flip behaviour without editing the file — useful for containers where the image
is immutable.

Read access is deliberately cheap: the file is parsed once at import time and
cached in a module-level dict. Call `reload_config()` if you change the file at
runtime (the test suite does this to exercise both flag positions).

Flags
-----
credits_enabled (bool, default True)
    Master switch for the credits/billing system.

    * True  — legacy behaviour: `/v1/chat/completions` refuses with HTTP 402
      when the caller's balance is below the minimum, and every request books a
      `CreditTransaction`. Revenue distribution still runs.
    * False — the portal is free to use. No 402, no balance floor, no credit
      deduction. Usage rows and node earnings are still recorded so the data is
      complete if credits are switched back on. The schema is untouched; only
      the enforcement is bypassed.

Override: CREDITS_ENABLED=0|1|true|false (env wins over config.yaml).
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger("gpu-pool.config")

# Same resolution order as nodes.py: explicit env path, then /app (Docker),
# then the repo root next to this file (host / test runs).
_here = Path(__file__).resolve().parent
CONFIG_PATH = os.environ.get("CONFIG_PATH") or (
    "/app/config.yaml" if Path("/app/config.yaml").exists() else str(_here / "config.yaml")
)

# Defaults — what the app falls back to when the key is absent.
DEFAULTS: Dict[str, Any] = {
    "supply_check_threshold": 20,
    "credits_enabled": True,
}

_cache: Dict[str, Any] = {}


def _truthy(value: Any, default: bool = True) -> bool:
    """Parse a YAML/env scalar into a bool. Unknown values fall back to default."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y", "ja")


def _env_override(key: str) -> Any:
    """Return the env override for a flag, if one is set ('' means unset)."""
    raw = os.environ.get(key.upper(), "").strip()
    return raw if raw != "" else None


def reload_config() -> Dict[str, Any]:
    """(Re-)read config.yaml and merge env overrides. Safe to call any time."""
    global _cache
    data: Dict[str, Any] = {}
    try:
        import yaml  # imported lazily so a missing pyyaml cannot break startup
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        log.info(f"config.yaml not found at {CONFIG_PATH}; using defaults")
    except Exception as e:  # malformed YAML should degrade, not crash
        log.warning(f"Could not load config from {CONFIG_PATH}: {e}")

    merged = {**DEFAULTS, **data}
    for key in ("credits_enabled", "supply_check_threshold"):
        override = _env_override(key)
        if override is not None:
            merged[key] = override
    _cache = merged
    return _cache


def get_config() -> Dict[str, Any]:
    """Cached config dict (parsed on first access)."""
    if not _cache:
        reload_config()
    return _cache


def credits_enabled() -> bool:
    """True when the credits/billing system enforces balances and charges usage."""
    return _truthy(get_config().get("credits_enabled"), default=True)


def supply_check_threshold() -> int:
    """Toner/supply alert threshold in percent (informational)."""
    try:
        return int(get_config().get("supply_check_threshold", 20))
    except (TypeError, ValueError):
        return 20
