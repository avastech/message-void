"""SMTP capture server. Accepts any envelope and stores parsed mail."""
from __future__ import annotations

import email
import logging
from email import policy
from email.message import EmailMessage

from aiosmtpd.controller import Controller

from .storage import Message, store

log = logging.getLogger(__name__)


def _decode_part(part) -> str:
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        return str(payload or "")


def _walk(msg: EmailMessage) -> tuple[str, str, list[dict]]:
    text_body = ""
    html_body = ""
    attachments: list[dict] = []

    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        disp = (part.get("Content-Disposition") or "").lower()
        if "attachment" in disp:
            payload = part.get_payload(decode=True) or b""
            attachments.append(
                {
                    "filename": part.get_filename() or "",
                    "content_type": ctype,
                    "size": len(payload),
                }
            )
        elif ctype == "text/plain":
            text_body += _decode_part(part)
        elif ctype == "text/html":
            html_body += _decode_part(part)

    return text_body, html_body, attachments


class _Handler:
    async def handle_DATA(self, server, session, envelope):
        try:
            msg = email.message_from_bytes(envelope.content, policy=policy.default)
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("Failed to parse SMTP message: %s", exc)
            return "250 Message accepted"

        text_body, html_body, attachments = _walk(msg)

        from_addr = msg.get("From", envelope.mail_from or "")
        to_header = msg.get_all("To") or []
        to_str = ", ".join(to_header) if to_header else ", ".join(envelope.rcpt_tos)

        headers = {k: v for k, v in msg.items()}
        try:
            raw = envelope.content.decode("utf-8")
        except UnicodeDecodeError:
            raw = envelope.content.decode("latin-1", errors="replace")

        store.add(
            Message(
                channel="mail",
                summary={
                    "from": from_addr,
                    "to": to_str,
                    "subject": msg.get("Subject", ""),
                },
                body={
                    "text": text_body,
                    "html": html_body,
                    "attachments": attachments,
                    "raw": raw,
                    "envelope_from": envelope.mail_from,
                    "envelope_to": list(envelope.rcpt_tos),
                },
                headers=headers,
                preview=(text_body or html_body).strip()[:200],
            )
        )
        return "250 Message accepted"


def start_smtp(host: str, port: int) -> Controller:
    controller = Controller(_Handler(), hostname=host, port=port)
    controller.start()
    return controller
