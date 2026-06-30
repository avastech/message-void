"""Runtime configuration overrides for channel settings.

Settings are normally provided via environment variables. For convenience, the
Settings UI can also set a value at runtime *when no environment variable pins
it*. Resolution order for :func:`get` is:

1. environment variable (if set and non-empty) — always wins, and the value is
   considered "locked" so the UI can't change it;
2. a runtime override set through the Settings UI;
3. ``None``.

Overrides live in memory only (a dev tool); environment variables remain the
durable way to configure the service.
"""
from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_overrides: dict[str, str] = {}


def get(key: str) -> str | None:
    """Resolve a setting: env var wins, then a UI-provided override, else ``None``."""
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    with _lock:
        return _overrides.get(key) or None


def is_locked(key: str) -> bool:
    """True when an environment variable pins the value (the UI can't change it)."""
    return bool(os.environ.get(key))


def source(key: str) -> str:
    """Where the effective value comes from: ``env``, ``runtime`` or ``unset``."""
    if os.environ.get(key):
        return "env"
    with _lock:
        return "runtime" if _overrides.get(key) else "unset"


def set_override(key: str, value: str | None) -> None:
    """Set (or clear, when ``value`` is empty/None) a runtime override."""
    with _lock:
        if value:
            _overrides[key] = value
        else:
            _overrides.pop(key, None)


def _reset_for_tests() -> None:
    with _lock:
        _overrides.clear()
