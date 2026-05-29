"""Capture Telegram bot API requests.

Real endpoint:  ``https://api.telegram.org/bot<TOKEN>/<method>``

Override Laravel's telegram base URI (``services.telegram-bot-api.base_uri``
in laravel-notification-channels/telegram) to::

    http://message-void:5000/telegram
"""
from __future__ import annotations

import time

from flask import Blueprint, jsonify, request

from ..storage import Message, store
from .base import Channel, register


class TelegramChannel(Channel):
    name = "telegram"
    description = "Telegram bot API (laravel-notification-channels/telegram)"
    endpoints = ["POST /telegram/bot<TOKEN>/<method>"]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("telegram", __name__, url_prefix="/telegram")

        @bp.route("/bot<token>/<method>", methods=["GET", "POST"])
        def capture(token: str, method: str):
            payload = _payload()
            text = (
                payload.get("text")
                or payload.get("caption")
                or payload.get("question")
                or ""
            )
            chat_id = payload.get("chat_id", "")
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "method": method,
                        "chat_id": chat_id,
                        "text": str(text)[:120],
                    },
                    body=payload,
                    headers=dict(request.headers),
                    preview=str(text),
                    extra={"path": request.path, "token_suffix": token[-4:]},
                )
            )
            return jsonify(
                {
                    "ok": True,
                    "result": {
                        "message_id": int(time.time() * 1000) % 2**31,
                        "from": {"id": 0, "is_bot": True, "first_name": "MessageVoid"},
                        "chat": {"id": chat_id, "type": "private"},
                        "date": int(time.time()),
                        "text": str(text),
                    },
                }
            )

        return bp


def _payload() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    if request.form:
        return {k: v for k, v in request.form.items()}
    return {k: v for k, v in request.args.items()}


register(TelegramChannel())
