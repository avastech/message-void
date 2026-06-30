# Message Void

A MailHog-style **notification capture service** for Laravel applications, with first-class support for the channels published under [laravel-notification-channels](https://github.com/orgs/laravel-notification-channels/repositories).

## Purpose

When developing or testing a Laravel application that sends notifications, you typically don't want real emails, SMS messages, Slack posts, or push notifications going out. Message Void runs as a single Docker container that pretends to be every notification provider Laravel might call: SMTP for mail, the Slack incoming-webhook URL, the Telegram bot API, the Twilio REST API, the Vonage SMS API, the Pusher Channels and Beams APIs, the Mailgun and Postmark HTTP APIs, and a generic catch-all webhook for anything else.

Captured messages are stored in an in-memory ring buffer and shown in a live web UI (modeled on MailHog) and exposed through a small REST + Server-Sent-Events API. Nothing is forwarded to real providers, so it's safe to point staging, CI, or local development at it.

The channel system is plug-in based: each provider is a small Python module in `message_void/channels/`. New channels are autodiscovered on startup, so adding support for another `laravel-notification-channels` package is a single self-contained file (see [Adding a new channel](#adding-a-new-channel)).

### Channels included

| Channel    | Endpoint(s)                                                                                |
| ---------- | ------------------------------------------------------------------------------------------ |
| `mail`     | SMTP on port `1025`                                                                        |
| `slack`    | `POST /slack/services/<team>/<bot>/<token>`, `POST /slack/webhook/<token>`                 |
| `discord`  | `POST /discord/api/webhooks/<id>/<token>`, `POST /discord/api/v<n>/channels/<id>/messages` |
| `telegram` | `POST /telegram/bot<TOKEN>/<method>`                                                       |
| `twilio`   | `POST /twilio/2010-04-01/Accounts/<sid>/Messages.json` (and `Calls.json`)                  |
| `vonage`   | `POST /vonage/sms/json`                                                                    |
| `pusher`   | `POST /pusher/apps/<app_id>/events`, `POST /pusher/publish_api/v1/instances/<i>/publishes` |
| `mailgun`  | `POST /mailgun/v3/<domain>/messages`                                                       |
| `postmark` | `POST /postmark/email`, `POST /postmark/email/batch`                                       |
| `webhook`  | `ANY /webhook/<tag>` — generic catch-all                                                   |

## Usage

### Run the service

```sh
docker compose up --build
```

Three things start:

| Port   | What it serves                                            |
| ------ | --------------------------------------------------------- |
| `5000` | Web UI **and** REST/SSE API                               |
| `1025` | SMTP listener (point Laravel's `MAIL_HOST`/`MAIL_PORT` here) |

Open <http://localhost:5000> for the UI. The sidebar lists every loaded channel with live message counts; the **Settings** button (top right) shows each channel's exact capture endpoints and its reply/inbound setup.

### Point Laravel at it

Add Message Void to your application's `docker-compose.yml` (so the Laravel container can resolve it as `message-void`) and set the relevant env / config values:

```dotenv
# Mail (drop-in replacement for MailHog)
MAIL_MAILER=smtp
MAIL_HOST=message-void
MAIL_PORT=1025
MAIL_USERNAME=null
MAIL_PASSWORD=null
MAIL_ENCRYPTION=null

# Slack incoming webhook
SLACK_WEBHOOK_URL=http://message-void:5000/slack/services/T0/B0/XYZ

# Mailgun mail driver (config/services.php → mailgun.endpoint)
MAILGUN_ENDPOINT=message-void:5000/mailgun

# Postmark mail driver (config/services.php → postmark.base_url)
POSTMARK_BASE_URL=http://message-void:5000/postmark
```

For Telegram, Discord, Twilio, Vonage, Pusher, etc., override the channel package's `base_uri` (every package exposes one) and use the matching path under `http://message-void:5000/`. The full list is in the UI's **Settings** panel and at `/api/channels`.

### REST + SSE API

| Method | Path                            | Purpose                                  |
| ------ | ------------------------------- | ---------------------------------------- |
| GET    | `/api/messages`                 | List captured messages (newest first); `?channel=`, `?limit=`, `?offset=` |
| GET    | `/api/messages/<id>`            | Fetch one message                        |
| DELETE | `/api/messages/<id>`            | Delete one message                       |
| POST   | `/api/messages/<id>/reply`      | Simulate a user reply — deliver an inbound event to your app (see [Replies](#replying-simulating-an-inbound-user-reply)) |
| DELETE | `/api/messages`                 | Clear all messages; `?channel=` to clear one channel only |
| GET    | `/api/channels`                 | Channels with descriptions and counts    |
| GET    | `/api/settings`                 | Per-channel settings, their values and source (env/runtime/unset) |
| PUT    | `/api/settings`                 | Set/clear runtime overrides for settings not pinned by an env var |
| GET    | `/api/stream`                   | Server-Sent-Events stream of new messages |
| GET    | `/healthz`                      | Liveness probe                           |

### Replying (simulating an inbound user reply)

Capture is one-directional: your app sends a notification and Message Void stores
it. A **reply** reverses that flow — it builds the provider's *inbound* webhook
payload and delivers it to a URL your app exposes, so the app receives it exactly
as it would a real reply from the recipient. Use it to exercise the full
round trip (e.g. an SMS auto-responder, a `STOP` opt-out, a chatbot flow).

In the web UI, open a captured message from a reply-capable channel and use the
**Simulate a user reply** box. Or call the API directly:

```sh
curl -X POST http://localhost:5000/api/messages/<id>/reply \
  -H 'Content-Type: application/json' \
  -d '{"text": "STOP"}'
```

The recorded inbound message appears in the UI tagged `inbound`, and the response
reports the status your app returned:

```json
{ "delivered_to": "http://app/twilio/inbound", "app_status": 200, "message_id": "…" }
```

Because Message Void must now reach *out* to your app, reply-capable channels need
to know where inbound goes. Currently implemented:

| Channel    | Config                                                                                  |
| ---------- | --------------------------------------------------------------------------------------- |
| `twilio`   | `MESSAGE_VOID_TWILIO_INBOUND_URL` — your number's "A message comes in" webhook. Optional `MESSAGE_VOID_TWILIO_AUTH_TOKEN` adds a valid `X-Twilio-Signature`. Swaps `From`/`To`. |
| `vonage`   | `MESSAGE_VOID_VONAGE_INBOUND_URL` — your number's inbound-SMS webhook. Sends `msisdn`/`to` (original recipient becomes the sender). |
| `slack`    | `MESSAGE_VOID_SLACK_INBOUND_URL` — your app's Events API Request URL. Optional `MESSAGE_VOID_SLACK_SIGNING_SECRET` adds a valid `X-Slack-Signature`. Replies into the original channel. |
| `telegram` | `MESSAGE_VOID_TELEGRAM_INBOUND_URL` — your bot's **webhook** URL. Optional `MESSAGE_VOID_TELEGRAM_SECRET_TOKEN` sets `X-Telegram-Bot-Api-Secret-Token`. ⚠️ Webhook mode only — long-polling (`getUpdates`) apps won't receive it. |
| `discord`  | `MESSAGE_VOID_DISCORD_INBOUND_URL` — POSTs a `MESSAGE_CREATE` event. ⚠️ Real Discord delivers over the gateway **websocket**, which this tool doesn't emulate; use only if your test setup exposes an HTTP receiver. Webhook-origin captures carry no channel, so pass `channel_id`. |

These values are read through a small config layer: an environment variable always
wins. When one is **not** set via env, you can supply it at runtime from the
**Settings** panel (the "Configuration" section under each channel) — handy for
trying replies without editing your env/compose. Env-pinned values appear locked
("set via env var") and can't be changed from the UI; secrets are write-only
(never echoed back). Runtime overrides live in memory only — environment variables
remain the durable way to configure the service. The same data is available at:

```
GET /api/settings                       # current settings, sources, locked flags
PUT /api/settings  {"KEY": "value"}     # set/clear runtime overrides (env-pinned rejected)
```

Per-reply overrides can also be passed in the POST body alongside `text` (e.g. `url`,
`from`/`to`, `channel`, `chat_id`, `channel_id`, signing secrets). Channels that
can't push inbound (SMTP, Mailgun, Postmark, Pusher) omit the capability and show
no reply box.

To add replies to another channel, override `supports_reply()` and `build_reply()`
on its `Channel` subclass (see [Adding a new channel](#adding-a-new-channel)),
returning a `PushReply` describing the inbound request; the dispatcher sends it
and records the inbound message.

### Adding a new channel

Each channel is one Python file in `message_void/channels/`. The package autodiscovers them on startup — no other wiring is needed:

```python
# message_void/channels/pushover.py
from flask import Blueprint, request, jsonify
from ..storage import Message, store
from .base import Channel, register


class PushoverChannel(Channel):
    name = "pushover"
    description = "Pushover push notifications"
    endpoints = ["POST /pushover/1/messages.json"]

    def blueprint(self) -> Blueprint:
        bp = Blueprint("pushover", __name__, url_prefix="/pushover")

        @bp.post("/1/messages.json")
        def capture():
            payload = {**request.form.to_dict(), **(request.get_json(silent=True) or {})}
            store.add(Message(
                channel=self.name,
                summary={"to": payload.get("user", ""), "text": (payload.get("message") or "")[:120]},
                body=payload,
                headers=dict(request.headers),
                preview=payload.get("message", ""),
            ))
            return jsonify({"status": 1, "request": "00000000000000000000000000000000"})

        return bp


register(PushoverChannel())
```

Restart the container and Pushover appears in the UI sidebar with its own counter and `/api/channels` entry.

### Tests

```sh
pip install -r requirements.txt pytest
pytest -q
```

The suite spins the Flask app and the embedded SMTP server up in-process and exercises every channel.

## Configuration

All configuration is via environment variables; defaults are tuned for local development inside Docker.

| Env var                      | Default   | Purpose                                                       |
| ---------------------------- | --------- | ------------------------------------------------------------- |
| `MESSAGE_VOID_HOST`          | `0.0.0.0` | HTTP bind host                                                |
| `MESSAGE_VOID_PORT`          | `5000`    | HTTP bind port (UI + API)                                     |
| `MESSAGE_VOID_SMTP_HOST`     | `0.0.0.0` | SMTP bind host                                                |
| `MESSAGE_VOID_SMTP_PORT`     | `1025`    | SMTP bind port                                                |
| `MESSAGE_VOID_SMTP_DISABLED` | unset     | Set to `1` to skip starting the SMTP listener                 |
| `MESSAGE_VOID_MAX_MESSAGES`  | `1000`    | Ring-buffer capacity (oldest messages evicted on overflow)    |
| `MESSAGE_VOID_LOG_LEVEL`     | `INFO`    | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)    |

### Docker Compose example

```yaml
services:
  message-void:
    build: .
    image: message-void:latest
    container_name: message-void
    restart: unless-stopped
    ports:
      - "5000:5000"   # UI + API
      - "1025:1025"   # SMTP
    environment:
      MESSAGE_VOID_MAX_MESSAGES: "1000"
```

To share the service across multiple Laravel projects, attach it to an external Docker network and reference it by container name (`message-void`) from each Laravel app's compose file.

## Building & publishing the image

To distribute Message Void as a pre-built image (Docker Hub, GitHub Container Registry, GitLab, AWS ECR, etc.) build it once and push the tagged result. Replace `your-org` / `youruser` with your actual namespace.

### Single-architecture build (quickest)

Use this when the consumers of the image will run the same CPU architecture as the build host.

```sh
# Build and tag
docker build -t your-org/message-void:0.1.0 -t your-org/message-void:latest .

# Log in once (Docker Hub; for GHCR use ghcr.io, for ECR use the AWS CLI)
docker login

# Push both tags
docker push your-org/message-void:0.1.0
docker push your-org/message-void:latest
```

### Multi-architecture build (recommended for public images)

Docker Hub consumers commonly run a mix of `linux/amd64` (Intel/AMD servers, older Macs) and `linux/arm64` (Apple Silicon, AWS Graviton, Raspberry Pi 4+). Use Buildx to publish a single tag that resolves to the right architecture for each puller:

```sh
# One-time setup: create and select a builder that supports cross-platform builds
docker buildx create --name message-void-builder --use
docker buildx inspect --bootstrap

# Build for both architectures and push in one step (--push uploads each arch
# and assembles a multi-arch manifest under the tag)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t your-org/message-void:0.1.0 \
  -t your-org/message-void:latest \
  --push .
```

Verify the manifest:

```sh
docker buildx imagetools inspect your-org/message-void:latest
```

### Pushing to alternative registries

| Registry              | Login command                                              | Tag prefix                                       |
| --------------------- | ---------------------------------------------------------- | ------------------------------------------------ |
| Docker Hub            | `docker login`                                             | `your-org/message-void`                          |
| GitHub Container Reg. | `echo $GH_TOKEN \| docker login ghcr.io -u <user> --password-stdin` | `ghcr.io/your-org/message-void`                  |
| GitLab Container Reg. | `docker login registry.gitlab.com`                         | `registry.gitlab.com/your-group/your-project/message-void` |
| AWS ECR               | `aws ecr get-login-password \| docker login --password-stdin <acct>.dkr.ecr.<region>.amazonaws.com` | `<acct>.dkr.ecr.<region>.amazonaws.com/message-void` |

### Versioning

Tag every release with both an immutable version and `latest`, so consumers can pin if they want stability:

```sh
VERSION=$(python3 -c "import message_void; print(message_void.__version__)")
docker buildx build --platform linux/amd64,linux/arm64 \
  -t your-org/message-void:${VERSION} \
  -t your-org/message-void:latest \
  --push .
```

Bumping the version is a one-line change to `message_void/__init__.py`.

### Consuming the published image

Downstream projects (or other developers) can then drop the build step from their compose file and just pull:

```yaml
services:
  message-void:
    image: your-org/message-void:latest
    ports:
      - "5000:5000"
      - "1025:1025"
```
