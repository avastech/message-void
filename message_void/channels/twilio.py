"""Capture Twilio REST API requests (SMS, WhatsApp, etc.).

Override Twilio's base URL in your Laravel config (``twilio-notification-channel``
or ``laravel-notification-channels/twilio``) so requests go to::

    http://message-void:5000/twilio
"""
from __future__ import annotations

import time
import uuid

from flask import Blueprint, jsonify, request

from ..storage import Message, store
from .base import Channel, register


class TwilioChannel(Channel):
    name = "twilio"
    description = "Twilio REST API (SMS, MMS, WhatsApp, calls)"
    endpoints = [
        "POST /twilio/2010-04-01/Accounts/<sid>/Messages.json",
        "POST /twilio/2010-04-01/Accounts/<sid>/Calls.json",
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


def _payload() -> dict:
    if request.form:
        return {k: v for k, v in request.form.items()}
    if request.is_json:
        return request.get_json(silent=True) or {}
    return {}


register(TwilioChannel())
