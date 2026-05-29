"""Generic webhook capture for channels that don't have a dedicated handler.

Useful for ad-hoc Laravel notification channels (the
``WebhookChannel``/``WebhookMessage`` from laravel-notification-channels) and
as a quick way to test a new provider before writing a dedicated channel.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..storage import Message, store
from .base import Channel, register


class WebhookChannel(Channel):
    name = "webhook"
    description = "Catch-all webhook capture for arbitrary providers"
    endpoints = ["ANY /webhook/<path:tag>"]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("webhook", __name__, url_prefix="/webhook")

        @bp.route(
            "/<path:tag>",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        )
        def capture(tag: str):
            body, kind = _read_body()
            preview = _preview(body, kind)
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "tag": tag,
                        "method": request.method,
                        "content_type": request.content_type or "",
                        "text": preview[:120],
                    },
                    body={"kind": kind, "data": body, "query": dict(request.args)},
                    headers=dict(request.headers),
                    preview=preview,
                    extra={"path": request.path},
                )
            )
            return jsonify({"ok": True, "tag": tag})

        return bp


def _read_body() -> tuple:
    if request.is_json:
        return request.get_json(silent=True) or {}, "json"
    if request.form:
        return {k: v for k, v in request.form.items()}, "form"
    raw = request.get_data(as_text=True)
    return raw, "raw"


def _preview(body, kind: str) -> str:
    if kind == "json":
        import json

        return json.dumps(body)[:200]
    if kind == "form":
        return ", ".join(f"{k}={v}" for k, v in body.items())[:200]
    return (body or "")[:200]


register(WebhookChannel())
