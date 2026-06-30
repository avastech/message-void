"""Capture Telegram bot API requests.

Real endpoint:  ``https://api.telegram.org/bot<TOKEN>/<method>``

Override Laravel's telegram base URI (``services.telegram-bot-api.base_uri``
in laravel-notification-channels/telegram) to::

    http://message-void:5000/telegram
"""
from __future__ import annotations

import json
import time

from flask import Blueprint, jsonify, request

from .. import config
from ..storage import Message, store
from .base import Channel, PushReply, ReplyError, Setting, register


class TelegramChannel(Channel):
    name = "telegram"
    description = "Telegram bot API (laravel-notification-channels/telegram)"
    endpoints = ["POST /telegram/bot<TOKEN>/<method>"]
    reply_setup = [
        "MESSAGE_VOID_TELEGRAM_INBOUND_URL — your bot's webhook URL",
        "MESSAGE_VOID_TELEGRAM_SECRET_TOKEN (optional) — X-Telegram-Bot-Api-Secret-Token",
        "Webhook mode only — long-polling (getUpdates) apps won't receive it",
    ]
    settings = [
        Setting(
            "MESSAGE_VOID_TELEGRAM_INBOUND_URL",
            "Inbound URL",
            help="Your bot's webhook URL",
        ),
        Setting(
            "MESSAGE_VOID_TELEGRAM_SECRET_TOKEN",
            "Secret token",
            secret=True,
            help="Optional — sent as X-Telegram-Bot-Api-Secret-Token",
        ),
    ]

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

    def supports_reply(self) -> bool:
        return True

    def build_reply(self, original: Message, text: str, opts: dict) -> PushReply:
        """Build a Telegram ``Update`` for a user replying in the same chat.

        Delivers to the bot's **webhook** URL (the app must use ``setWebhook``;
        long-polling ``getUpdates`` apps won't receive this). When a secret token
        is configured it's sent as ``X-Telegram-Bot-Api-Secret-Token``.
        """
        url = opts.get("url") or config.get("MESSAGE_VOID_TELEGRAM_INBOUND_URL")
        if not url:
            raise ReplyError(
                "no Telegram inbound URL configured "
                "(set MESSAGE_VOID_TELEGRAM_INBOUND_URL or pass `url`)",
                400,
            )

        body = original.body or {}
        chat_id = opts.get("chat_id") or body.get("chat_id") or original.summary.get("chat_id")
        try:
            user_id = int(chat_id)
        except (TypeError, ValueError):
            user_id = 0
        now = int(time.time())
        update = {
            "update_id": now,
            "message": {
                "message_id": now % 2**31,
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "first_name": opts.get("first_name", "User"),
                },
                "chat": {"id": chat_id, "type": "private"},
                "date": now,
                "text": text,
            },
        }

        headers = {}
        secret = opts.get("secret_token") or config.get("MESSAGE_VOID_TELEGRAM_SECRET_TOKEN")
        if secret:
            headers["X-Telegram-Bot-Api-Secret-Token"] = secret

        return PushReply(
            url=url,
            body=json.dumps(update).encode(),
            content_type="application/json",
            headers=headers,
            summary={"method": "update", "chat_id": chat_id, "text": text[:120]},
            preview=text,
        )


def _payload() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    if request.form:
        return {k: v for k, v in request.form.items()}
    return {k: v for k, v in request.args.items()}


register(TelegramChannel())
