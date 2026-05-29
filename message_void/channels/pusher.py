"""Capture Pusher Channels (broadcast) and Pusher Beams (push) requests."""
from __future__ import annotations

import uuid

from flask import Blueprint, jsonify, request

from ..storage import Message, store
from .base import Channel, register


class PusherChannel(Channel):
    name = "pusher"
    description = "Pusher Channels (broadcasting) and Pusher Beams (push)"
    endpoints = [
        "POST /pusher/apps/<app_id>/events",
        "POST /pusher/apps/<app_id>/batch_events",
        "POST /pusher/publish_api/v1/instances/<instance>/publishes",
    ]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("pusher", __name__, url_prefix="/pusher")

        @bp.post("/apps/<app_id>/events")
        def event(app_id: str):
            payload = request.get_json(silent=True) or {}
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "kind": "broadcast",
                        "event": payload.get("name", ""),
                        "channels": ", ".join(payload.get("channels") or [payload.get("channel", "")]),
                        "text": str(payload.get("data", ""))[:120],
                    },
                    body=payload,
                    headers=dict(request.headers),
                    preview=str(payload.get("data", "")),
                    extra={"path": request.path, "app_id": app_id},
                )
            )
            return jsonify({})

        @bp.post("/apps/<app_id>/batch_events")
        def batch(app_id: str):
            payload = request.get_json(silent=True) or {}
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "kind": "broadcast-batch",
                        "count": len(payload.get("batch") or []),
                        "text": "",
                    },
                    body=payload,
                    headers=dict(request.headers),
                    preview="",
                    extra={"path": request.path, "app_id": app_id},
                )
            )
            return jsonify({"batch": []})

        @bp.post("/publish_api/v1/instances/<instance>/publishes")
        @bp.post("/publish_api/v1/instances/<instance>/publishes/users")
        @bp.post("/publish_api/v1/instances/<instance>/publishes/interests")
        def beams(instance: str):
            payload = request.get_json(silent=True) or {}
            interests = payload.get("interests") or payload.get("users") or []
            apns = (payload.get("apns") or {}).get("aps", {}).get("alert", {})
            fcm = (payload.get("fcm") or {}).get("notification", {})
            text = (
                (apns.get("body") if isinstance(apns, dict) else apns)
                or fcm.get("body")
                or ""
            )
            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "kind": "beams",
                        "targets": ", ".join(map(str, interests))[:80],
                        "text": str(text)[:120],
                    },
                    body=payload,
                    headers={k: v for k, v in request.headers if k.lower() != "authorization"},
                    preview=str(text),
                    extra={"path": request.path, "instance_id": instance},
                )
            )
            return jsonify({"publishId": uuid.uuid4().hex})

        return bp


register(PusherChannel())
