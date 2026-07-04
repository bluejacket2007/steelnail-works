"""Automated XSS sanitization for inbound JSON payloads.

Every string value in mutating JSON requests (POST/PUT/PATCH) is HTML-escaped
before it reaches route handlers, so stored payloads can never round-trip as
executable markup (stored XSS, OWASP A03).

Deliberately exempt:
- /api/v1/webhooks/*  — signature verification needs the byte-exact raw body.
- /api/v1/auth/*      — credentials must not be transformed.
"""
from __future__ import annotations

import html
import json
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_EXEMPT_PREFIXES = ("/api/v1/webhooks", "/api/v1/auth")
_MUTATING_METHODS = {"POST", "PUT", "PATCH"}


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return html.escape(value, quote=True)
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    return value


class XSSSanitizerMiddleware:
    """Pure-ASGI middleware: buffers the JSON body, escapes it, replays it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in _MUTATING_METHODS
            or any(scope["path"].startswith(p) for p in _EXEMPT_PREFIXES)
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if "application/json" not in headers.get("content-type", ""):
            await self.app(scope, receive, send)
            return

        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        try:
            payload = json.loads(body) if body else None
            if payload is not None:
                body = json.dumps(_sanitize(payload)).encode("utf-8")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # malformed JSON — let request validation reject it downstream

        # Body length may have changed; keep content-length consistent.
        mutable_headers = MutableHeaders(scope=scope)
        mutable_headers["content-length"] = str(len(body))

        replayed = False

        async def sanitized_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, sanitized_receive, send)
