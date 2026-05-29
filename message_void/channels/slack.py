"""Capture Slack incoming-webhook posts.

Point Laravel's ``services.slack.notifications.url`` (or the per-notification
``routeNotificationForSlack``) at::

    http://message-void:5000/slack/services/T000/B000/XXXX
"""
from __future__ import annotations

from flask import Blueprint, request

from ..storage import Message, store
from .base import Channel, register


class SlackChannel(Channel):
    name = "slack"
    description = "Slack incoming webhook (laravel-notification-channels/slack)"
    endpoints = [
        "POST /slack/services/<team>/<bot>/<token>",
        "POST /slack/webhook/<token>",
    ]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("slack", __name__, url_prefix="/slack")

        @bp.post("/services/<team>/<bot>/<token>")
        @bp.post("/webhook/<path:token>")
        def capture(**path_params):
            payload = request.get_json(silent=True) or {}
            if not payload and request.form:
                # Slack legacy: form-encoded with `payload=<json>`.
                import json as _json

                raw = request.form.get("payload", "{}")
                try:
                    payload = _json.loads(raw)
                except _json.JSONDecodeError:
                    payload = {"text": raw}

            text = payload.get("text") or ""
            if not text and payload.get("blocks"):
                text = _flatten_blocks(payload["blocks"])
            if not text and payload.get("attachments"):
                text = " | ".join(
                    a.get("fallback") or a.get("text") or ""
                    for a in payload["attachments"]
                ).strip(" |")

            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "channel": payload.get("channel", "(default)"),
                        "username": payload.get("username", ""),
                        "text": text[:120],
                    },
                    body=payload,
                    headers=dict(request.headers),
                    preview=text,
                    extra={"path": request.path, "params": path_params},
                )
            )
            return "ok"

        return bp


def _flatten_blocks(blocks: list) -> str:
    out: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        text = b.get("text")
        if isinstance(text, dict) and text.get("text"):
            out.append(text["text"])
        elif isinstance(text, str):
            out.append(text)
        for field in b.get("fields", []) or []:
            if isinstance(field, dict) and field.get("text"):
                out.append(field["text"])
    return "\n".join(out)


register(SlackChannel())
