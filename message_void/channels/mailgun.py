"""Capture Mailgun HTTP-API mail sends (Laravel mailgun mail driver)."""
from __future__ import annotations

import uuid

from flask import Blueprint, jsonify, request

from ..storage import Message, store
from .base import Channel, register


class MailgunChannel(Channel):
    name = "mailgun"
    description = "Mailgun HTTP API (Laravel mailgun mail driver)"
    endpoints = ["POST /mailgun/v3/<domain>/messages"]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("mailgun", __name__, url_prefix="/mailgun")

        @bp.post("/v3/<domain>/messages")
        @bp.post("/v3/<domain>/messages.mime")
        def messages(domain: str):
            payload = {k: v for k, v in request.form.items()}
            files = [
                {"field": k, "filename": f.filename, "content_type": f.mimetype, "size": _size(f)}
                for k, f in request.files.items()
            ]
            text = payload.get("text") or payload.get("html") or ""
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "from": payload.get("from", ""),
                        "to": payload.get("to", ""),
                        "subject": payload.get("subject", ""),
                    },
                    body={"form": payload, "files": files},
                    headers={k: v for k, v in request.headers if k.lower() != "authorization"},
                    preview=text[:200],
                    extra={"path": request.path, "domain": domain},
                )
            )
            return jsonify(
                {"id": f"<{uuid.uuid4().hex}@{domain}>", "message": "Queued. Thank you."}
            )

        return bp


def _size(file_storage) -> int:
    pos = file_storage.stream.tell()
    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(pos)
    return size


register(MailgunChannel())
