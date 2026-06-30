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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from flask import Blueprint

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..storage import Message


class ReplyError(Exception):
    """Raised by a channel (or the dispatcher) when a reply can't be built/delivered.

    ``status`` is the HTTP status the API should return to the caller.
    """

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class Setting:
    """A configurable value a channel reads (via :mod:`message_void.config`).

    ``key`` is the environment-variable name. When no env var pins it, the
    Settings UI can supply the value at runtime. ``secret`` masks the value in
    the API/UI (only whether it is set is exposed).
    """

    key: str
    label: str
    secret: bool = False
    help: str = ""


@dataclass
class PushReply:
    """An outbound HTTP request that delivers a *simulated inbound* event to the app.

    A channel's :meth:`Channel.build_reply` returns one of these; the reply
    dispatcher performs the request (so channels stay free of network code) and
    records ``summary``/``preview`` as an inbound :class:`~message_void.storage.Message`.
    """

    url: str
    body: bytes
    content_type: str = "application/x-www-form-urlencoded"
    method: str = "POST"
    headers: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    preview: str = ""


class Channel(ABC):
    name: str = ""
    description: str = ""
    endpoints: list[str] = []  # Human-readable list, surfaced via /api/channels.
    reply_setup: list[str] = []  # How to configure inbound replies; shown in Settings.
    settings: list["Setting"] = []  # Configurable values, editable in the Settings UI.

    @abstractmethod
    def blueprint(self) -> Blueprint:
        """Return the Flask blueprint that exposes capture endpoints."""

    def supports_reply(self) -> bool:
        """Whether this channel can deliver a simulated user reply to the app."""
        return False

    def build_reply(self, original: "Message", text: str, opts: dict) -> PushReply:
        """Build the inbound request that simulates a user replying to ``original``.

        ``opts`` carries per-reply overrides from the API caller (e.g. a target
        ``url``). Raise :class:`ReplyError` for misconfiguration.
        """
        raise ReplyError(f"channel {self.name!r} does not support replies")


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
