"""Mail channel descriptor.

The actual capture happens in :mod:`message_void.smtp_server` (an SMTP
listener), but we register a thin blueprint so the UI's channel list and
``/api/channels`` describe the mail channel consistently with the others.
"""
from __future__ import annotations

import os

from flask import Blueprint, jsonify

from .base import Channel, register


class MailChannel(Channel):
    name = "mail"
    description = "SMTP capture (point Laravel's MAIL_HOST/MAIL_PORT here)"
    endpoints = [
        "smtp://<host>:1025  (configurable via MESSAGE_VOID_SMTP_PORT)",
    ]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("mail", __name__, url_prefix="/mail")

        @bp.get("/info")
        def info():
            return jsonify(
                {
                    "smtp_host": os.environ.get("MESSAGE_VOID_SMTP_HOST", "0.0.0.0"),
                    "smtp_port": int(os.environ.get("MESSAGE_VOID_SMTP_PORT", "1025")),
                }
            )

        return bp


register(MailChannel())
