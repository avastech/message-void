"""Capture Vonage (formerly Nexmo) SMS / Verify API requests."""
from __future__ import annotations

import uuid

from flask import Blueprint, jsonify, request

from ..storage import Message, store
from .base import Channel, register


class VonageChannel(Channel):
    name = "vonage"
    description = "Vonage / Nexmo SMS API (laravel-notification-channels/vonage)"
    endpoints = ["POST /vonage/sms/json"]

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


def _payload() -> dict:
    if request.form:
        return {k: v for k, v in request.form.items()}
    if request.is_json:
        return request.get_json(silent=True) or {}
    return {}


register(VonageChannel())
