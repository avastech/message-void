"""Capture Discord webhook posts and bot-API channel messages."""
from __future__ import annotations

import json
import time
import uuid

from flask import Blueprint, jsonify, request

from .. import config
from ..storage import Message, store
from .base import Channel, PushReply, ReplyError, Setting, register


class DiscordChannel(Channel):
    name = "discord"
    description = "Discord webhooks and bot API (laravel-notification-channels/discord)"
    endpoints = [
        "POST /discord/api/webhooks/<id>/<token>",
        "POST /discord/api/v<n>/channels/<channel_id>/messages",
    ]
    reply_setup = [
        "MESSAGE_VOID_DISCORD_INBOUND_URL — POSTs a MESSAGE_CREATE event",
        "Real Discord uses the gateway websocket; this is an HTTP receiver only",
        "Webhook-origin captures carry no channel — pass channel_id in the reply",
    ]
    settings = [
        Setting(
            "MESSAGE_VOID_DISCORD_INBOUND_URL",
            "Inbound URL",
            help="HTTP receiver for a MESSAGE_CREATE event",
        ),
    ]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("discord", __name__, url_prefix="/discord")

        @bp.post("/api/webhooks/<webhook_id>/<token>")
        def webhook(webhook_id: str, token: str):
            payload = _payload()
            content = payload.get("content") or _embeds_preview(payload.get("embeds"))
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "kind": "webhook",
                        "webhook_id": webhook_id,
                        "username": payload.get("username", ""),
                        "text": content[:120],
                    },
                    body=payload,
                    headers=dict(request.headers),
                    preview=content,
                    extra={"path": request.path, "token": token},
                )
            )
            return jsonify({"id": "0", "type": 0, "content": content}), 204

        @bp.post("/api/v<int:version>/channels/<channel_id>/messages")
        @bp.post("/api/channels/<channel_id>/messages")
        def bot_message(channel_id: str, version: int = 10):
            payload = _payload()
            content = payload.get("content") or _embeds_preview(payload.get("embeds"))
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "kind": "bot",
                        "channel_id": channel_id,
                        "text": content[:120],
                    },
                    body=payload,
                    headers={k: v for k, v in request.headers if k.lower() != "authorization"},
                    preview=content,
                    extra={"path": request.path, "api_version": version},
                )
            )
            return jsonify({"id": "0", "channel_id": channel_id, "content": content})

        return bp

    def supports_reply(self) -> bool:
        return True

    def build_reply(self, original: Message, text: str, opts: dict) -> PushReply:
        """Build a Discord ``MESSAGE_CREATE`` gateway event for a user reply.

        NOTE: real Discord delivers messages over the gateway **websocket**, which
        this dev tool doesn't emulate. This POSTs the same event payload to an HTTP
        receiver you configure — handy if your test setup exposes an HTTP shim for
        inbound Discord events, but it does not match Discord's real transport.
        """
        url = opts.get("url") or config.get("MESSAGE_VOID_DISCORD_INBOUND_URL")
        if not url:
            raise ReplyError(
                "no Discord inbound URL configured "
                "(set MESSAGE_VOID_DISCORD_INBOUND_URL or pass `url`)",
                400,
            )

        channel_id = opts.get("channel_id") or original.summary.get("channel_id")
        if not channel_id:
            raise ReplyError(
                "no Discord channel_id to reply into "
                "(webhook captures carry none — pass `channel_id`)",
                400,
            )

        snowflake = str(int(time.time() * 1000))
        payload = {
            "t": "MESSAGE_CREATE",
            "op": 0,
            "s": None,
            "d": {
                "id": snowflake,
                "channel_id": str(channel_id),
                "content": text,
                "author": {
                    "id": opts.get("user_id", "100000000000000000"),
                    "username": opts.get("username", "user"),
                    "bot": False,
                },
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                "nonce": uuid.uuid4().hex,
            },
        }
        return PushReply(
            url=url,
            body=json.dumps(payload).encode(),
            content_type="application/json",
            summary={"kind": "message", "channel_id": str(channel_id), "text": text[:120]},
            preview=text,
        )


def _payload() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    if request.form:
        return {k: v for k, v in request.form.items()}
    raw = request.get_data(as_text=True)
    return {"_raw": raw} if raw else {}


def _embeds_preview(embeds) -> str:
    if not embeds:
        return ""
    parts: list[str] = []
    for e in embeds:
        if not isinstance(e, dict):
            continue
        if e.get("title"):
            parts.append(str(e["title"]))
        if e.get("description"):
            parts.append(str(e["description"]))
    return " — ".join(parts)


register(DiscordChannel())
