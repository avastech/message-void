"""Capture Twilio REST API requests (SMS, WhatsApp, etc.).

Override Twilio's base URL in your Laravel config (``twilio-notification-channel``
or ``laravel-notification-channels/twilio``) so requests go to::

    http://message-void:5000/twilio
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
import uuid

from flask import Blueprint, jsonify, request

from .. import config
from ..storage import Message, store
from .base import Channel, PushReply, ReplyError, Setting, register


class TwilioChannel(Channel):
    name = "twilio"
    description = "Twilio REST API (SMS, MMS, WhatsApp, calls)"
    endpoints = [
        "POST /twilio/2010-04-01/Accounts/<sid>/Messages.json",
        "POST /twilio/2010-04-01/Accounts/<sid>/Calls.json",
    ]
    reply_setup = [
        "MESSAGE_VOID_TWILIO_INBOUND_URL — your number's \"A message comes in\" webhook",
        "MESSAGE_VOID_TWILIO_AUTH_TOKEN (optional) — adds a valid X-Twilio-Signature",
        "Reply swaps From/To so the original recipient becomes the sender",
    ]
    settings = [
        Setting(
            "MESSAGE_VOID_TWILIO_INBOUND_URL",
            "Inbound URL",
            help='Your number\'s "A message comes in" webhook',
        ),
        Setting(
            "MESSAGE_VOID_TWILIO_AUTH_TOKEN",
            "Auth token",
            secret=True,
            help="Optional — adds a valid X-Twilio-Signature",
        ),
    ]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("twilio", __name__, url_prefix="/twilio")

        @bp.post("/2010-04-01/Accounts/<sid>/Messages.json")
        def messages(sid: str):
            payload = _payload()
            sms_sid = "SM" + uuid.uuid4().hex[:32]
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "kind": "sms",
                        "from": payload.get("From", ""),
                        "to": payload.get("To", ""),
                        "text": (payload.get("Body") or "")[:120],
                    },
                    body=payload,
                    headers={k: v for k, v in request.headers if k.lower() != "authorization"},
                    preview=payload.get("Body", ""),
                    extra={"path": request.path, "account_sid": sid},
                )
            )
            return jsonify(
                {
                    "sid": sms_sid,
                    "account_sid": sid,
                    "from": payload.get("From"),
                    "to": payload.get("To"),
                    "body": payload.get("Body"),
                    "status": "queued",
                    "date_created": time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime()),
                    "uri": f"/2010-04-01/Accounts/{sid}/Messages/{sms_sid}.json",
                }
            ), 201

        @bp.post("/2010-04-01/Accounts/<sid>/Calls.json")
        def calls(sid: str):
            payload = _payload()
            call_sid = "CA" + uuid.uuid4().hex[:32]
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "kind": "call",
                        "from": payload.get("From", ""),
                        "to": payload.get("To", ""),
                        "text": payload.get("Url", ""),
                    },
                    body=payload,
                    headers={k: v for k, v in request.headers if k.lower() != "authorization"},
                    preview=f"call {payload.get('From')} -> {payload.get('To')}",
                    extra={"path": request.path, "account_sid": sid},
                )
            )
            return jsonify(
                {
                    "sid": call_sid,
                    "account_sid": sid,
                    "from": payload.get("From"),
                    "to": payload.get("To"),
                    "status": "queued",
                }
            ), 201

        return bp

    def supports_reply(self) -> bool:
        return True

    def build_reply(self, original: Message, text: str, opts: dict) -> PushReply:
        """Build Twilio's inbound-SMS webhook for a user replying to ``original``.

        Twilio POSTs ``application/x-www-form-urlencoded`` to the number's
        "A message comes in" webhook. The reply swaps ``From``/``To`` (the
        original recipient is now the sender) and signs the request when an auth
        token is available, matching Twilio's request validation.
        """
        url = opts.get("url") or config.get("MESSAGE_VOID_TWILIO_INBOUND_URL")
        if not url:
            raise ReplyError(
                "no Twilio inbound URL configured "
                "(set MESSAGE_VOID_TWILIO_INBOUND_URL or pass `url`)",
                400,
            )

        body = original.body or {}
        # The user who received the original message is now the one texting back.
        user = opts.get("from") or body.get("To", "")
        app_number = opts.get("to") or body.get("From", "")
        account_sid = (original.extra or {}).get("account_sid") or body.get("AccountSid", "")
        sms_sid = "SM" + uuid.uuid4().hex[:32]

        params = {
            "ToCountry": "",
            "ToState": "",
            "SmsMessageSid": sms_sid,
            "NumMedia": "0",
            "ToCity": "",
            "From": user,
            "To": app_number,
            "MessageSid": sms_sid,
            "AccountSid": account_sid,
            "Body": text,
            "NumSegments": "1",
            "SmsSid": sms_sid,
            "SmsStatus": "received",
            "ApiVersion": "2010-04-01",
        }

        headers = {}
        auth_token = opts.get("auth_token") or config.get("MESSAGE_VOID_TWILIO_AUTH_TOKEN")
        if auth_token:
            headers["X-Twilio-Signature"] = _twilio_signature(auth_token, url, params)

        return PushReply(
            url=url,
            body=urllib.parse.urlencode(params).encode(),
            headers=headers,
            summary={"kind": "sms", "from": user, "to": app_number, "text": text[:120]},
            preview=text,
        )


def _twilio_signature(auth_token: str, url: str, params: dict) -> str:
    """X-Twilio-Signature for a form POST: HMAC-SHA1 over URL + sorted params."""
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _payload() -> dict:
    if request.form:
        return {k: v for k, v in request.form.items()}
    if request.is_json:
        return request.get_json(silent=True) or {}
    return {}


register(TwilioChannel())
