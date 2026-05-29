"""Capture Discord webhook posts and bot-API channel messages."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..storage import Message, store
from .base import Channel, register


class DiscordChannel(Channel):
    name = "discord"
    description = "Discord webhooks and bot API (laravel-notification-channels/discord)"
    endpoints = [
        "POST /discord/api/webhooks/<id>/<token>",
        "POST /discord/api/v<n>/channels/<channel_id>/messages",
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
