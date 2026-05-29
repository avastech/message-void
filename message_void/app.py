"""Flask application entry point."""
from __future__ import annotations

import logging
import os

from flask import Flask, render_template

from . import channels as channels_pkg
from . import storage
from .api import api_bp

log = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)

    max_size = int(os.environ.get("MESSAGE_VOID_MAX_MESSAGES", "1000"))
    if max_size != storage.store._messages.maxlen:  # type: ignore[union-attr]
        storage.configure(max_size)

    app.register_blueprint(api_bp)
    for channel in channels_pkg.all_channels():
        app.register_blueprint(channel.blueprint())

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            channels=channels_pkg.all_channels(),
        )

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "channels": [c.name for c in channels_pkg.all_channels()]}

    return app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("MESSAGE_VOID_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = create_app()
    log.info("Loaded channels: %s", ", ".join(c.name for c in channels_pkg.all_channels()))

    if os.environ.get("MESSAGE_VOID_SMTP_DISABLED") != "1":
        from .smtp_server import start_smtp

        smtp_host = os.environ.get("MESSAGE_VOID_SMTP_HOST", "0.0.0.0")
        smtp_port = int(os.environ.get("MESSAGE_VOID_SMTP_PORT", "1025"))
        start_smtp(smtp_host, smtp_port)
        log.info("SMTP listening on %s:%s", smtp_host, smtp_port)

    host = os.environ.get("MESSAGE_VOID_HOST", "0.0.0.0")
    port = int(os.environ.get("MESSAGE_VOID_PORT", "5000"))
    log.info("HTTP listening on %s:%s", host, port)

    try:
        from waitress import serve

        serve(app, host=host, port=port, threads=8)
    except ImportError:  # pragma: no cover
        app.run(host=host, port=port, use_reloader=False, threaded=True)
