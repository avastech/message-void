"""In-memory ring-buffer message store with subscriber notifications."""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Iterable


class Message:
    __slots__ = (
        "id",
        "channel",
        "received_at",
        "summary",
        "headers",
        "body",
        "preview",
        "extra",
    )

    def __init__(
        self,
        channel: str,
        summary: dict,
        body: Any,
        *,
        headers: dict | None = None,
        preview: str = "",
        extra: dict | None = None,
    ):
        self.id = uuid.uuid4().hex
        self.channel = channel
        self.received_at = time.time()
        self.summary = summary
        self.headers = headers or {}
        self.body = body
        self.preview = preview
        self.extra = extra or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel": self.channel,
            "received_at": self.received_at,
            "summary": self.summary,
            "headers": self.headers,
            "body": self.body,
            "preview": self.preview,
            "extra": self.extra,
        }


Subscriber = Callable[[Message], None]


class MessageStore:
    def __init__(self, max_size: int = 1000):
        self._lock = threading.RLock()
        self._messages: deque[Message] = deque(maxlen=max_size)
        self._index: dict[str, Message] = {}
        self._subscribers: list[Subscriber] = []

    def add(self, message: Message) -> Message:
        with self._lock:
            if self._messages.maxlen and len(self._messages) == self._messages.maxlen:
                evicted = self._messages[0]
                self._index.pop(evicted.id, None)
            self._messages.append(message)
            self._index[message.id] = message
        self._notify(message)
        return message

    def list(
        self,
        channel: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        with self._lock:
            items = list(self._messages)
        items.reverse()
        if channel:
            items = [m for m in items if m.channel == channel]
        return items[offset : offset + limit]

    def get(self, message_id: str) -> Message | None:
        with self._lock:
            return self._index.get(message_id)

    def delete(self, message_id: str) -> bool:
        with self._lock:
            msg = self._index.pop(message_id, None)
            if msg is None:
                return False
            try:
                self._messages.remove(msg)
            except ValueError:
                pass
            return True

    def clear(self, channel: str | None = None) -> int:
        with self._lock:
            if channel is None:
                n = len(self._messages)
                self._messages.clear()
                self._index.clear()
                return n
            kept = [m for m in self._messages if m.channel != channel]
            removed = len(self._messages) - len(kept)
            self._messages = deque(kept, maxlen=self._messages.maxlen)
            self._index = {m.id: m for m in self._messages}
            return removed

    def channel_counts(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for m in self._messages:
                counts[m.channel] = counts.get(m.channel, 0) + 1
            return counts

    def total(self) -> int:
        with self._lock:
            return len(self._messages)

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def _notify(self, message: Message) -> None:
        for cb in list(self._subscribers):
            try:
                cb(message)
            except Exception:
                pass


store = MessageStore()


def configure(max_size: int) -> None:
    """Resize the store; preserves recent messages."""
    global store
    new = MessageStore(max_size=max_size)
    with store._lock:
        for m in list(store._messages)[-max_size:]:
            new._messages.append(m)
            new._index[m.id] = m
    store = new
