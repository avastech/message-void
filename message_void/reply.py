"""Deliver simulated user replies (inbound events) back to the app under test.

Capture channels are one-directional: the app sends a notification and Message
Void stores it. A *reply* reverses that flow for the first time -- it builds the
provider's inbound webhook payload (via the channel's
:meth:`~message_void.channels.base.Channel.build_reply`) and POSTs it to a URL
the app exposes, so the app receives it exactly as it would a real user reply.

Network code lives here, not in the channels, so each channel only has to
describe *what* to send, not *how* to send it.
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request

from .channels.base import PushReply, ReplyError
from .storage import Message, store

log = logging.getLogger(__name__)

_MAX_RESPONSE_BYTES = 64_000


def dispatch_reply(original: Message, text: str, opts: dict) -> dict:
    """Build and deliver a reply to ``original``; record it as an inbound message.

    Returns a small result dict (delivery URL + the app's response status/body).
    Raises :class:`ReplyError` on any misconfiguration or delivery failure.
    """
    from . import channels as channels_pkg

    channel = next(
        (c for c in channels_pkg.all_channels() if c.name == original.channel), None
    )
    if channel is None or not channel.supports_reply():
        raise ReplyError(f"channel {original.channel!r} does not support replies", 400)

    push = channel.build_reply(original, text, opts)
    if not isinstance(push, PushReply):  # pragma: no cover - defensive
        raise ReplyError(f"channel {original.channel!r} returned an invalid reply", 500)

    status, response_body = _deliver(push)

    inbound = store.add(
        Message(
            channel=original.channel,
            summary={**push.summary, "direction": "inbound"},
            body={
                "text": text,
                "delivered_to": push.url,
                "app_status": status,
            },
            preview=push.preview or text,
            extra={"direction": "inbound", "in_reply_to": original.id},
        )
    )

    return {
        "delivered_to": push.url,
        "app_status": status,
        "app_response": response_body[:2000],
        "message_id": inbound.id,
    }


def _deliver(push: PushReply) -> tuple[int, str]:
    req = urllib.request.Request(
        push.url,
        data=push.body,
        method=push.method,
        headers={"Content-Type": push.content_type, **push.headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(_MAX_RESPONSE_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        # The app was reached but returned an error status -- surface it, don't fail.
        return exc.code, exc.read(_MAX_RESPONSE_BYTES).decode("utf-8", "replace")
    except Exception as exc:
        raise ReplyError(f"could not reach app at {push.url}: {exc}", 502)
