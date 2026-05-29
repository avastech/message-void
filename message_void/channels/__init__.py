"""Channel registry. Channel modules placed in this package self-register."""
from __future__ import annotations

import importlib
import logging
import pkgutil

from .base import Channel, all_channels, register

log = logging.getLogger(__name__)


def autodiscover() -> None:
    """Import every sibling module so each channel can call ``register``."""
    package = importlib.import_module(__name__)
    for _, name, _ in pkgutil.iter_modules(package.__path__):
        if name == "base":
            continue
        try:
            importlib.import_module(f"{__name__}.{name}")
        except Exception:  # pragma: no cover - import-time safety
            log.exception("Failed to load channel module %s", name)


autodiscover()

__all__ = ["Channel", "register", "all_channels", "autodiscover"]
