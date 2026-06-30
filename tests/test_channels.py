"""End-to-end tests exercising every registered channel."""
from __future__ import annotations

import contextlib
import json

import pytest

from message_void import config, storage
from message_void.app import create_app


@pytest.fixture
def client():
    storage.store.clear()
    config._reset_for_tests()
    app = create_app()
    app.testing = True
    with app.test_client() as c:
        yield c


def _sole(channel: str):
    msgs = storage.store.list(channel=channel)
    assert len(msgs) == 1, f"expected one {channel} message, got {len(msgs)}"
    return msgs[0]


def test_channels_listed(client):
    res = client.get("/api/channels")
    assert res.status_code == 200
    names = [c["name"] for c in res.get_json()["channels"]]
    for expected in [
        "mail", "slack", "discord", "telegram", "twilio",
        "vonage", "pusher", "mailgun", "postmark", "webhook",
    ]:
        assert expected in names


def test_slack_webhook(client):
    payload = {"channel": "#alerts", "username": "deploy-bot", "text": "Build green"}
    res = client.post("/slack/services/T1/B2/XYZ", json=payload)
    assert res.status_code == 200
    msg = _sole("slack")
    assert msg.summary["channel"] == "#alerts"
    assert msg.preview == "Build green"


def test_slack_blocks_flatten(client):
    payload = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "*hi*"}}]}
    client.post("/slack/services/T/B/X", json=payload)
    msg = _sole("slack")
    assert "hi" in msg.preview


def test_discord_webhook(client):
    payload = {"username": "bot", "content": "hello world", "embeds": []}
    res = client.post("/discord/api/webhooks/123/abc", json=payload)
    assert res.status_code == 204
    msg = _sole("discord")
    assert msg.summary["webhook_id"] == "123"
    assert msg.preview == "hello world"


def test_discord_bot_message(client):
    res = client.post(
        "/discord/api/v10/channels/9999/messages",
        json={"content": "ping"},
        headers={"Authorization": "Bot secret-token"},
    )
    assert res.status_code == 200
    msg = _sole("discord")
    assert msg.summary["kind"] == "bot"
    assert "Authorization" not in msg.headers
    assert "authorization" not in {k.lower() for k in msg.headers}


def test_telegram_send_message(client):
    res = client.post(
        "/telegram/botABCDEF/sendMessage",
        json={"chat_id": "42", "text": "hello"},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    msg = _sole("telegram")
    assert msg.summary["method"] == "sendMessage"
    assert msg.summary["chat_id"] == "42"


def test_twilio_sms(client):
    res = client.post(
        "/twilio/2010-04-01/Accounts/ACxxx/Messages.json",
        data={"From": "+15551112222", "To": "+15553334444", "Body": "OTP 123456"},
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["sid"].startswith("SM")
    msg = _sole("twilio")
    assert msg.summary["text"] == "OTP 123456"


def test_vonage_sms(client):
    res = client.post(
        "/vonage/sms/json",
        data={"from": "Acme", "to": "447700900000", "text": "hi"},
    )
    assert res.status_code == 200
    assert res.get_json()["message-count"] == "1"
    msg = _sole("vonage")
    assert msg.summary["to"] == "447700900000"


def test_pusher_broadcast(client):
    res = client.post(
        "/pusher/apps/12345/events",
        json={"name": "OrderShipped", "channels": ["orders"], "data": "{\"id\":1}"},
    )
    assert res.status_code == 200
    msg = _sole("pusher")
    assert msg.summary["event"] == "OrderShipped"


def test_pusher_beams(client):
    res = client.post(
        "/pusher/publish_api/v1/instances/inst-1/publishes",
        json={
            "interests": ["debug-test"],
            "apns": {"aps": {"alert": {"title": "T", "body": "ping"}}},
        },
    )
    assert res.status_code == 200
    msg = _sole("pusher")
    assert msg.summary["kind"] == "beams"
    assert msg.preview == "ping"


def test_mailgun(client):
    res = client.post(
        "/mailgun/v3/example.com/messages",
        data={
            "from": "no-reply@example.com",
            "to": "user@example.com",
            "subject": "Welcome",
            "text": "hi there",
        },
    )
    assert res.status_code == 200
    msg = _sole("mailgun")
    assert msg.summary["subject"] == "Welcome"


def test_postmark(client):
    res = client.post(
        "/postmark/email",
        json={
            "From": "no-reply@example.com",
            "To": "user@example.com",
            "Subject": "Welcome",
            "TextBody": "hi",
        },
    )
    assert res.status_code == 200
    msg = _sole("postmark")
    assert msg.preview == "hi"


def test_postmark_batch(client):
    res = client.post(
        "/postmark/email/batch",
        json=[
            {"From": "a@x", "To": "b@x", "Subject": "1", "TextBody": "first"},
            {"From": "a@x", "To": "c@x", "Subject": "2", "TextBody": "second"},
        ],
    )
    assert res.status_code == 200
    assert len(storage.store.list(channel="postmark")) == 2


def test_webhook_catchall_json(client):
    res = client.post("/webhook/custom-channel", json={"foo": "bar"})
    assert res.status_code == 200
    msg = _sole("webhook")
    assert msg.summary["tag"] == "custom-channel"
    assert msg.body["data"] == {"foo": "bar"}


def test_webhook_catchall_form(client):
    client.post("/webhook/sms-driver", data={"to": "+1", "body": "hi"})
    msg = _sole("webhook")
    assert msg.body["data"] == {"to": "+1", "body": "hi"}


def test_api_message_lifecycle(client):
    client.post("/slack/services/T/B/X", json={"text": "first"})
    client.post("/slack/services/T/B/X", json={"text": "second"})

    listing = client.get("/api/messages").get_json()
    assert listing["total"] == 2
    assert listing["messages"][0]["summary"]["text"] == "second"

    msg_id = listing["messages"][0]["id"]
    detail = client.get(f"/api/messages/{msg_id}").get_json()
    assert detail["preview"] == "second"

    assert client.delete(f"/api/messages/{msg_id}").status_code == 200
    assert client.get("/api/messages").get_json()["total"] == 1

    cleared = client.delete("/api/messages").get_json()
    assert cleared["removed"] == 1
    assert client.get("/api/messages").get_json()["total"] == 0


def test_clear_by_channel(client):
    client.post("/slack/services/T/B/X", json={"text": "s"})
    client.post("/discord/api/webhooks/1/2", json={"content": "d"})
    res = client.delete("/api/messages?channel=slack").get_json()
    assert res["removed"] == 1
    counts = storage.store.channel_counts()
    assert counts == {"discord": 1}


@contextlib.contextmanager
def _inbound_receiver(status=200):
    """A one-shot local HTTP server that records the request an app would receive."""
    import socket
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    received = {}

    class Handler(BaseHTTPRequestHandler):
        def _capture(self):
            length = int(self.headers.get("Content-Length", 0))
            received["body"] = self.rfile.read(length).decode() if length else ""
            received["headers"] = {k: v for k, v in self.headers.items()}
            received["path"] = self.path
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b"ok")

        do_POST = _capture
        do_GET = _capture

        def log_message(self, *a):  # silence test server logging
            pass

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}/inbound", received
    finally:
        server.shutdown()


def test_twilio_reply_round_trip(client, monkeypatch):
    """A reply to a captured Twilio SMS is delivered inbound to the app's webhook."""
    import urllib.parse

    with _inbound_receiver() as (url, received):
        monkeypatch.setenv("MESSAGE_VOID_TWILIO_INBOUND_URL", url)
        monkeypatch.setenv("MESSAGE_VOID_TWILIO_AUTH_TOKEN", "secret-token")
        client.post(
            "/twilio/2010-04-01/Accounts/ACxxx/Messages.json",
            data={"From": "+15550000001", "To": "+15550000002", "Body": "Your code is 1234"},
        )
        original = _sole("twilio")

        res = client.post(f"/api/messages/{original.id}/reply", json={"text": "STOP"})
        assert res.status_code == 200, res.get_json()
        assert res.get_json()["app_status"] == 200

        form = urllib.parse.parse_qs(received["body"])
        # From/To are swapped: the original recipient now texts the app number back.
        assert form["From"] == ["+15550000002"]
        assert form["To"] == ["+15550000001"]
        assert form["Body"] == ["STOP"]
        assert received["headers"].get("X-Twilio-Signature")  # signed: auth token configured

        # The simulated inbound is recorded and flagged for the UI.
        inbound = storage.store.list(channel="twilio")[0]
        assert inbound.extra["direction"] == "inbound"
        assert inbound.extra["in_reply_to"] == original.id
        assert inbound.preview == "STOP"


def test_vonage_reply_round_trip(client, monkeypatch):
    import urllib.parse

    with _inbound_receiver() as (url, received):
        monkeypatch.setenv("MESSAGE_VOID_VONAGE_INBOUND_URL", url)
        client.post(
            "/vonage/sms/json",
            data={"from": "Acme", "to": "447700900000", "text": "code 99"},
        )
        original = _sole("vonage")
        res = client.post(f"/api/messages/{original.id}/reply", json={"text": "BALANCE"})
        assert res.status_code == 200, res.get_json()

        form = urllib.parse.parse_qs(received["body"])
        assert form["msisdn"] == ["447700900000"]  # original recipient is now the sender
        assert form["to"] == ["Acme"]
        assert form["text"] == ["BALANCE"]


def test_slack_reply_round_trip(client, monkeypatch):
    import hashlib
    import hmac
    import json

    with _inbound_receiver() as (url, received):
        monkeypatch.setenv("MESSAGE_VOID_SLACK_INBOUND_URL", url)
        monkeypatch.setenv("MESSAGE_VOID_SLACK_SIGNING_SECRET", "shh")
        client.post("/slack/services/T1/B2/XYZ", json={"channel": "#alerts", "text": "deploy?"})
        original = _sole("slack")
        res = client.post(f"/api/messages/{original.id}/reply", json={"text": "yes ship it"})
        assert res.status_code == 200, res.get_json()

        body = received["body"]
        event = json.loads(body)
        assert event["type"] == "event_callback"
        assert event["event"]["channel"] == "#alerts"
        assert event["event"]["text"] == "yes ship it"

        # Signature is valid for the delivered body + timestamp.
        ts = received["headers"]["X-Slack-Request-Timestamp"]
        expected = "v0=" + hmac.new(
            b"shh", f"v0:{ts}:{body}".encode(), hashlib.sha256
        ).hexdigest()
        assert received["headers"]["X-Slack-Signature"] == expected


def test_telegram_reply_round_trip(client, monkeypatch):
    import json

    with _inbound_receiver() as (url, received):
        monkeypatch.setenv("MESSAGE_VOID_TELEGRAM_INBOUND_URL", url)
        monkeypatch.setenv("MESSAGE_VOID_TELEGRAM_SECRET_TOKEN", "hook-secret")
        client.post("/telegram/botABCDEF/sendMessage", json={"chat_id": "42", "text": "hi"})
        original = _sole("telegram")
        res = client.post(f"/api/messages/{original.id}/reply", json={"text": "/start"})
        assert res.status_code == 200, res.get_json()

        update = json.loads(received["body"])
        assert update["message"]["chat"]["id"] == "42"
        assert update["message"]["text"] == "/start"
        assert update["message"]["from"]["is_bot"] is False
        assert received["headers"]["X-Telegram-Bot-Api-Secret-Token"] == "hook-secret"


def test_discord_reply_round_trip(client, monkeypatch):
    import json

    with _inbound_receiver() as (url, received):
        monkeypatch.setenv("MESSAGE_VOID_DISCORD_INBOUND_URL", url)
        client.post("/discord/api/v10/channels/9999/messages", json={"content": "ping"})
        original = _sole("discord")
        res = client.post(f"/api/messages/{original.id}/reply", json={"text": "pong"})
        assert res.status_code == 200, res.get_json()

        event = json.loads(received["body"])
        assert event["t"] == "MESSAGE_CREATE"
        assert event["d"]["channel_id"] == "9999"
        assert event["d"]["content"] == "pong"


def test_discord_reply_webhook_needs_channel_id(client, monkeypatch):
    """Webhook-origin captures carry no channel_id, so a reply must be told one."""
    monkeypatch.setenv("MESSAGE_VOID_DISCORD_INBOUND_URL", "http://127.0.0.1:1/x")
    client.post("/discord/api/webhooks/123/abc", json={"content": "hello"})
    original = _sole("discord")
    res = client.post(f"/api/messages/{original.id}/reply", json={"text": "hi"})
    assert res.status_code == 400
    assert "channel_id" in res.get_json()["error"]


def test_reply_unsupported_channel(client):
    # mailgun is send-only here — no inbound reply path.
    client.post(
        "/mailgun/v3/example.com/messages",
        data={"from": "a@x", "to": "b@x", "subject": "S", "text": "hi"},
    )
    msg = _sole("mailgun")
    res = client.post(f"/api/messages/{msg.id}/reply", json={"text": "hi back"})
    assert res.status_code == 400
    assert "does not support replies" in res.get_json()["error"]


def test_reply_requires_text(client):
    client.post(
        "/twilio/2010-04-01/Accounts/ACxxx/Messages.json",
        data={"From": "+1", "To": "+2", "Body": "hi"},
    )
    msg = _sole("twilio")
    assert client.post(f"/api/messages/{msg.id}/reply", json={"text": "  "}).status_code == 400
    assert client.post("/api/messages/nope/reply", json={"text": "x"}).status_code == 404


def test_settings_listed_with_source(client, monkeypatch):
    """GET /api/settings reports each setting's source; env-pinned ones are locked."""
    monkeypatch.setenv("MESSAGE_VOID_TWILIO_INBOUND_URL", "https://app.test/twilio")
    monkeypatch.delenv("MESSAGE_VOID_TWILIO_AUTH_TOKEN", raising=False)

    res = client.get("/api/settings")
    assert res.status_code == 200
    channels = {c["name"]: c["settings"] for c in res.get_json()["channels"]}
    twilio = {s["key"]: s for s in channels["twilio"]}

    url = twilio["MESSAGE_VOID_TWILIO_INBOUND_URL"]
    assert url["locked"] is True and url["source"] == "env"
    assert url["value"] == "https://app.test/twilio"

    token = twilio["MESSAGE_VOID_TWILIO_AUTH_TOKEN"]
    assert token["locked"] is False and token["source"] == "unset"
    assert token["secret"] is True and token["value"] == "" and token["set"] is False


def test_settings_update_then_reply_uses_override(client, monkeypatch):
    """A URL set via the Settings API (no env var) drives a real reply."""
    monkeypatch.delenv("MESSAGE_VOID_TWILIO_INBOUND_URL", raising=False)

    with _inbound_receiver() as (url, received):
        put = client.put("/api/settings", json={"MESSAGE_VOID_TWILIO_INBOUND_URL": url})
        assert put.status_code == 200
        assert put.get_json()["applied"] == ["MESSAGE_VOID_TWILIO_INBOUND_URL"]

        # It now reads back as a runtime-sourced value.
        res = client.get("/api/settings")
        twilio = {s["key"]: s for c in res.get_json()["channels"] if c["name"] == "twilio" for s in c["settings"]}
        assert twilio["MESSAGE_VOID_TWILIO_INBOUND_URL"]["source"] == "runtime"

        client.post(
            "/twilio/2010-04-01/Accounts/ACxxx/Messages.json",
            data={"From": "+15550000001", "To": "+15550000002", "Body": "hi"},
        )
        original = _sole("twilio")
        reply = client.post(f"/api/messages/{original.id}/reply", json={"text": "yo"})
        assert reply.status_code == 200, reply.get_json()
        assert received["body"]  # delivered to the override URL


def test_settings_update_rejects_env_pinned(client, monkeypatch):
    """A value pinned by an env var can't be overridden through the API."""
    monkeypatch.setenv("MESSAGE_VOID_SLACK_INBOUND_URL", "https://env.example/slack")
    res = client.put("/api/settings", json={"MESSAGE_VOID_SLACK_INBOUND_URL": "https://evil/x"})
    assert res.status_code == 400
    rejected = res.get_json()["rejected"]
    assert rejected and rejected[0]["key"] == "MESSAGE_VOID_SLACK_INBOUND_URL"
    assert config.get("MESSAGE_VOID_SLACK_INBOUND_URL") == "https://env.example/slack"


def test_settings_update_rejects_unknown_key(client):
    res = client.put("/api/settings", json={"NOT_A_REAL_SETTING": "x"})
    assert res.status_code == 400
    assert res.get_json()["rejected"][0]["reason"] == "unknown setting"


def test_smtp_capture():
    """Round-trip an email through the embedded SMTP server."""
    import smtplib
    import socket
    from email.message import EmailMessage

    from message_void.smtp_server import start_smtp

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    storage.store.clear()
    controller = start_smtp("127.0.0.1", port)
    try:

        msg = EmailMessage()
        msg["From"] = "app@example.com"
        msg["To"] = "user@example.com"
        msg["Subject"] = "Receipt"
        msg.set_content("Thanks for your order")
        msg.add_alternative("<p>Thanks for your <b>order</b></p>", subtype="html")

        with smtplib.SMTP("127.0.0.1", port) as s:
            s.send_message(msg)

        # aiosmtpd handles asynchronously; poll briefly.
        import time as _t
        for _ in range(20):
            if storage.store.list(channel="mail"):
                break
            _t.sleep(0.05)

        captured = _sole("mail")
        assert captured.summary["subject"] == "Receipt"
        assert "Thanks for your order" in captured.body["text"]
        assert "<b>order</b>" in captured.body["html"]
    finally:
        controller.stop()
