"""Capture Vonage (formerly Nexmo) SMS / Verify API requests."""
from __future__ import annotations

import time
import urllib.parse
import uuid

from flask import Blueprint, jsonify, request

from .. import config
from ..storage import Message, store
from .base import Channel, PushReply, ReplyError, Setting, register


class VonageChannel(Channel):
    name = "vonage"
    description = "Vonage / Nexmo SMS API (laravel-notification-channels/vonage)"
    endpoints = ["POST /vonage/sms/json"]
    reply_setup = [
        "MESSAGE_VOID_VONAGE_INBOUND_URL — your number's inbound-SMS webhook",
        "Sends msisdn/to so the original recipient becomes the sender",
    ]
    settings = [
        Setting(
            "MESSAGE_VOID_VONAGE_INBOUND_URL",
            "Inbound URL",
            help="Your number's inbound-SMS webhook",
        ),
    ]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("vonage", __name__, url_prefix="/vonage")

        @bp.post("/sms/json")
        def sms():
            payload = _payload()
            text = payload.get("text", "")
            to = payload.get("to", "")
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "from": payload.get("from", ""),
                        "to": to,
                        "text": text[:120],
                    },
                    body=payload,
                    headers=dict(request.headers),
                    preview=text,
                    extra={"path": request.path},
                )
            )
            return jsonify(
                {
                    "message-count": "1",
                    "messages": [
                        {
                            "to": to,
                            "message-id": uuid.uuid4().hex,
                            "status": "0",
                            "remaining-balance": "10.00000000",
                            "message-price": "0.00000000",
                            "network": "00000",
                        }
                    ],
                }
            )

        return bp

    def supports_reply(self) -> bool:
        return True

    def build_reply(self, original: Message, text: str, opts: dict) -> PushReply:
        """Build Vonage's inbound-SMS webhook for a user replying to ``original``.

        Vonage delivers inbound messages to the number's configured webhook with
        ``msisdn`` (the sender) and ``to`` (your virtual number). The reply makes
        the original recipient the sender.
        """
        url = opts.get("url") or config.get("MESSAGE_VOID_VONAGE_INBOUND_URL")
        if not url:
            raise ReplyError(
                "no Vonage inbound URL configured "
                "(set MESSAGE_VOID_VONAGE_INBOUND_URL or pass `url`)",
                400,
            )

        body = original.body or {}
        user = opts.get("from") or body.get("to", "")
        app_number = opts.get("to") or body.get("from", "")
        message_id = uuid.uuid4().hex

        params = {
            "msisdn": user,
            "to": app_number,
            "messageId": message_id,
            "text": text,
            "type": "text",
            "keyword": text.split(" ", 1)[0].upper() if text else "",
            "message-timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        }
        return PushReply(
            url=url,
            body=urllib.parse.urlencode(params).encode(),
            summary={"from": user, "to": app_number, "text": text[:120]},
            preview=text,
        )


def _payload() -> dict:
    if request.form:
        return {k: v for k, v in request.form.items()}
    if request.is_json:
        return request.get_json(silent=True) or {}
    return {}


register(VonageChannel())
