"""End-to-end tests exercising every registered channel."""
from __future__ import annotations

import json

import pytest

from message_void import storage
from message_void.app import create_app


@pytest.fixture
def client():
    storage.store.clear()
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
