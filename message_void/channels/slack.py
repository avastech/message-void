"""Capture Slack incoming-webhook posts.

Point Laravel's ``services.slack.notifications.url`` (or the per-notification
``routeNotificationForSlack``) at::

    http://message-void:5000/slack/services/T000/B000/XXXX
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from flask import Blueprint, request

from .. import config
from ..storage import Message, store
from .base import Channel, PushReply, ReplyError, Setting, register


class SlackChannel(Channel):
    name = "slack"
    description = "Slack incoming webhook (laravel-notification-channels/slack)"
    endpoints = [
        "POST /slack/services/<team>/<bot>/<token>",
        "POST /slack/webhook/<token>",
    ]
    reply_setup = [
        "MESSAGE_VOID_SLACK_INBOUND_URL — your app's Events API request URL",
        "MESSAGE_VOID_SLACK_SIGNING_SECRET (optional) — adds a valid X-Slack-Signature",
        "Reply lands in the same channel the original notification went to",
    ]
    settings = [
        Setting(
            "MESSAGE_VOID_SLACK_INBOUND_URL",
            "Inbound URL",
            help="Your app's Events API request URL",
        ),
        Setting(
            "MESSAGE_VOID_SLACK_SIGNING_SECRET",
            "Signing secret",
            secret=True,
            help="Optional — adds a valid X-Slack-Signature",
        ),
    ]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("slack", __name__, url_prefix="/slack")

        @bp.post("/services/<team>/<bot>/<token>")
        @bp.post("/webhook/<path:token>")
        def capture(**path_params):
            payload = request.get_json(silent=True) or {}
            if not payload and request.form:
                # Slack legacy: form-encoded with `payload=<json>`.
                import json as _json

                raw = request.form.get("payload", "{}")
                try:
                    payload = _json.loads(raw)
                except _json.JSONDecodeError:
                    payload = {"text": raw}

            text = payload.get("text") or ""
            if not text and payload.get("blocks"):
                text = _flatten_blocks(payload["blocks"])
            if not text and payload.get("attachments"):
                text = " | ".join(
                    a.get("fallback") or a.get("text") or ""
                    for a in payload["attachments"]
                ).strip(" |")

            store.add(
                Message(
                    channel=self.name,
                    summary={
                        "channel": payload.get("channel", "(default)"),
                        "username": payload.get("username", ""),
                        "text": text[:120],
                    },
                    body=payload,
                    headers=dict(request.headers),
                    preview=text,
                    extra={"path": request.path, "params": path_params},
                )
            )
            return "ok"

        return bp

    def supports_reply(self) -> bool:
        return True

    def build_reply(self, original: Message, text: str, opts: dict) -> PushReply:
        """Build a Slack Events API ``message`` callback for a user reply.

        Slack POSTs ``event_callback`` JSON to the app's configured Request URL,
        signed with ``X-Slack-Signature``. The reply lands in the same channel the
        original notification went to.
        """
        url = opts.get("url") or config.get("MESSAGE_VOID_SLACK_INBOUND_URL")
        if not url:
            raise ReplyError(
                "no Slack inbound URL configured "
                "(set MESSAGE_VOID_SLACK_INBOUND_URL or pass `url`)",
                400,
            )

        params = (original.extra or {}).get("params", {})
        channel = opts.get("channel") or original.summary.get("channel") or "(default)"
        now = time.time()
        ts = f"{now:.6f}"
        payload = {
            "token": "message-void",
            "team_id": params.get("team", "T000000"),
            "api_app_id": "A000000",
            "type": "event_callback",
            "event_id": "Ev" + uuid.uuid4().hex[:16].upper(),
            "event_time": int(now),
            "event": {
                "type": "message",
                "channel": channel,
                "user": opts.get("user", "U000USER"),
                "text": text,
                "ts": ts,
                "event_ts": ts,
                "channel_type": "channel",
            },
        }
        body = json.dumps(payload, separators=(",", ":")).encode()

        headers = {}
        signing_secret = opts.get("signing_secret") or config.get(
            "MESSAGE_VOID_SLACK_SIGNING_SECRET"
        )
        if signing_secret:
            timestamp = str(int(now))
            base = f"v0:{timestamp}:{body.decode()}".encode()
            digest = hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
            headers["X-Slack-Request-Timestamp"] = timestamp
            headers["X-Slack-Signature"] = "v0=" + digest

        return PushReply(
            url=url,
            body=body,
            content_type="application/json",
            headers=headers,
            summary={"channel": channel, "user": payload["event"]["user"], "text": text[:120]},
            preview=text,
        )


def _flatten_blocks(blocks: list) -> str:
    out: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        text = b.get("text")
        if isinstance(text, dict) and text.get("text"):
            out.append(text["text"])
        elif isinstance(text, str):
            out.append(text)
        for field in b.get("fields", []) or []:
            if isinstance(field, dict) and field.get("text"):
                out.append(field["text"])
    return "\n".join(out)


register(SlackChannel())
