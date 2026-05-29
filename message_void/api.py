"""REST API + SSE stream for retrieving captured messages."""
from __future__ import annotations

import json
import queue
import time
from typing import Iterator

from flask import Blueprint, Response, jsonify, request

from .storage import store

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.get("/messages")
def list_messages():
    channel = request.args.get("channel") or None
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 1000))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400
    messages = store.list(channel=channel, limit=limit, offset=offset)
    return jsonify(
        {
            "total": store.total(),
            "count": len(messages),
            "messages": [m.to_dict() for m in messages],
        }
    )


@api_bp.get("/messages/<message_id>")
def get_message(message_id: str):
    msg = store.get(message_id)
    if msg is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(msg.to_dict())


@api_bp.delete("/messages/<message_id>")
def delete_message(message_id: str):
    if not store.delete(message_id):
        return jsonify({"error": "not found"}), 404
    return jsonify({"deleted": message_id})


@api_bp.delete("/messages")
def clear_messages():
    channel = request.args.get("channel") or None
    removed = store.clear(channel=channel)
    return jsonify({"removed": removed})


@api_bp.get("/channels")
def channels_summary():
    from . import channels as channels_pkg

    counts = store.channel_counts()
    return jsonify(
        {
            "channels": [
                {
                    "name": c.name,
                    "description": c.description,
                    "endpoints": c.endpoints,
                    "count": counts.get(c.name, 0),
                }
                for c in channels_pkg.all_channels()
            ],
            "total": store.total(),
        }
    )


@api_bp.get("/stream")
def stream():
    """Server-Sent Events stream of new messages."""
    q: queue.Queue = queue.Queue(maxsize=128)

    def cb(msg) -> None:
        try:
            q.put_nowait(msg)
        except queue.Full:
            pass

    unsubscribe = store.subscribe(cb)

    def gen() -> Iterator[bytes]:
        try:
            yield b": connected\n\n"
            last_ping = time.time()
            while True:
                try:
                    msg = q.get(timeout=15)
                    payload = json.dumps(msg.to_dict())
                    yield f"event: message\ndata: {payload}\n\n".encode()
                except queue.Empty:
                    yield b": ping\n\n"
                    last_ping = time.time()
        finally:
            unsubscribe()

    return Response(gen(), mimetype="text/event-stream")
