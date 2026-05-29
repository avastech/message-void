"""Channel base class and registry helpers.

A *channel* models the request shape of a notification provider (Slack
webhook, Twilio REST, Telegram bot API, ...). Each channel exposes a Flask
``Blueprint`` that handles the requests Laravel would normally send to the
real provider, normalises them into a :class:`~message_void.storage.Message`,
and pushes them into the central store.

To add a new channel, create ``message_void/channels/<name>.py`` containing a
subclass of :class:`Channel` and call :func:`register` at import time. The
package's ``__init__`` autodiscovers every module so no other wiring is
needed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from flask import Blueprint


class Channel(ABC):
    name: str = ""
    description: str = ""
    endpoints: list[str] = []  # Human-readable list, surfaced via /api/channels.

    @abstractmethod
    def blueprint(self) -> Blueprint:
        """Return the Flask blueprint that exposes capture endpoints."""


_registry: list[Channel] = []


def register(channel: Channel) -> None:
    if not channel.name:
        raise ValueError(f"Channel {channel!r} must define a name")
    if any(c.name == channel.name for c in _registry):
        return  # Idempotent: re-importing a module shouldn't double-register.
    _registry.append(channel)


def all_channels() -> list[Channel]:
    return list(_registry)


def _reset_for_tests() -> None:
    _registry.clear()
