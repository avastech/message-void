"""Capture Postmark HTTP-API mail sends (Laravel postmark mail driver)."""
from __future__ import annotations

import time

from flask import Blueprint, jsonify, request

from ..storage import Message, store
from .base import Channel, register


class PostmarkChannel(Channel):
    name = "postmark"
    description = "Postmark HTTP API (Laravel postmark mail driver)"
    endpoints = ["POST /postmark/email", "POST /postmark/email/batch"]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("postmark", __name__, url_prefix="/postmark")

        @bp.post("/email")
        def send():
            payload = request.get_json(silent=True) or {}
            text = payload.get("TextBody") or payload.get("HtmlBody") or ""
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "from": payload.get("From", ""),
                        "to": payload.get("To", ""),
                        "subject": payload.get("Subject", ""),
                    },
                    body=payload,
                    headers={k: v for k, v in request.headers if k.lower() != "x-postmark-server-token"},
                    preview=text[:200],
                    extra={"path": request.path},
                )
            )
            return jsonify(
                {
                    "To": payload.get("To"),
                    "SubmittedAt": time.strftime("%Y-%m-%dT%H:%M:%S.0000000Z", time.gmtime()),
                    "MessageID": "00000000-0000-0000-0000-000000000000",
                    "ErrorCode": 0,
                    "Message": "OK",
                }
            )

        @bp.post("/email/batch")
        def batch():
            payload = request.get_json(silent=True) or []
            for item in payload if isinstance(payload, list) else []:
                text = item.get("TextBody") or item.get("HtmlBody") or ""
                store.add(
                    Message(
                        channel="postmark",
                        summary={
                            "from": item.get("From", ""),
                            "to": item.get("To", ""),
                            "subject": item.get("Subject", ""),
                        },
                        body=item,
                        headers={},
                        preview=text[:200],
                        extra={"batch": True},
                    )
                )
            return jsonify(
                [
                    {
                        "To": item.get("To"),
                        "SubmittedAt": time.strftime("%Y-%m-%dT%H:%M:%S.0000000Z", time.gmtime()),
                        "MessageID": "00000000-0000-0000-0000-000000000000",
                        "ErrorCode": 0,
                        "Message": "OK",
                    }
                    for item in (payload if isinstance(payload, list) else [])
                ]
            )

        return bp


register(PostmarkChannel())
