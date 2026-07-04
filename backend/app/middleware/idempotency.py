"""Idempotency framework for payment initiation.

``POST /api/v1/payments/initiate`` must carry an ``X-Idempotency-Key`` — this
is the one route that calls out to Stripe/Razorpay and can double-charge on
retry. Bill-of-Lading upload/verification live under the same router prefix
but never touch a payment provider, so they're deliberately excluded rather
than matched by a blanket prefix. Semantics (Stripe-compatible):

1. First request with a key  → acquires a Redis lock, executes, caches the
   full response for 24h.
2. Concurrent request, same key → 409 while the original is still in flight
   (this is the double-click / retry-storm case that causes double capture).
3. Later request, same key   → the cached response is replayed byte-for-byte
   with ``X-Idempotency-Replayed: true``; no second charge is ever initiated.
"""
from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.redis_client import get_async_redis

_GUARDED_PATHS = {"/api/v1/payments/initiate"}
_LOCK_TTL_SECONDS = 60           # max time a payment call may be in flight
_RESPONSE_TTL_SECONDS = 86_400   # replay window


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method != "POST" or request.url.path not in _GUARDED_PATHS:
            return await call_next(request)

        key = request.headers.get("x-idempotency-key", "").strip()
        if not key or len(key) > 128:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "X-Idempotency-Key header is required on payment "
                    "endpoints (max 128 chars)."
                },
            )

        redis = get_async_redis()
        cache_key = f"idem:resp:{key}"
        lock_key = f"idem:lock:{key}"

        cached = await redis.get(cache_key)
        if cached:
            stored = json.loads(cached)
            return Response(
                content=stored["body"],
                status_code=stored["status"],
                media_type=stored["media_type"],
                headers={"X-Idempotency-Replayed": "true"},
            )

        acquired = await redis.set(lock_key, "1", nx=True, ex=_LOCK_TTL_SECONDS)
        if not acquired:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "A request with this idempotency key is already "
                    "in flight. Retry after it completes."
                },
            )

        try:
            response = await call_next(request)
            body = b"".join([chunk async for chunk in response.body_iterator])

            # Only cache successful/deterministic outcomes; a 5xx should be
            # retryable with the same key.
            if response.status_code < 500:
                await redis.set(
                    cache_key,
                    json.dumps(
                        {
                            "status": response.status_code,
                            "body": body.decode("utf-8", errors="replace"),
                            "media_type": response.media_type or "application/json",
                        }
                    ),
                    ex=_RESPONSE_TTL_SECONDS,
                )

            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        finally:
            await redis.delete(lock_key)
