"""Redis Token Bucket rate limiter.

- Unauthenticated IPs:        60 requests/minute
- Authenticated corporate users: 200 requests/minute (keyed by JWT ``sub``)

The bucket lives in Redis and is refilled continuously (capacity/60 tokens
per second). Take + refill happen atomically inside a Lua script, so the
limiter is race-free under high concurrency and shared across every backend
replica. Exceeding the limit returns 429 with a Retry-After hint.
"""
from __future__ import annotations

import time

import jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.redis_client import get_async_redis

# KEYS[1] = bucket key
# ARGV: capacity, refill_rate (tokens/sec), now (float seconds), requested
_TOKEN_BUCKET_LUA = """
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])
local want     = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts     = tonumber(bucket[2])
if tokens == nil then tokens = capacity end
if ts == nil then ts = now end

tokens = math.min(capacity, tokens + math.max(0, now - ts) * rate)

local allowed = 0
if tokens >= want then
  tokens = tokens - want
  allowed = 1
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, math.ceil(capacity / rate) * 2)
return {allowed, tostring(tokens)}
"""

# Provider webhooks must never be dropped by our limiter — they are
# authenticated by cryptographic signature instead.
_EXEMPT_PREFIXES = ("/api/v1/webhooks", "/health")


class TokenBucketRateLimiter(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        subject, capacity = self._identify(request)
        redis = get_async_redis()
        try:
            allowed, tokens = await redis.eval(
                _TOKEN_BUCKET_LUA,
                1,
                f"ratelimit:{subject}",
                capacity,
                capacity / 60.0,
                time.time(),
                1,
            )
        except Exception:
            # Redis outage: fail open so a cache failure can't take the API down,
            # but the event is visible in logs via the middleware above us.
            return await call_next(request)

        if int(allowed) != 1:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Slow down."},
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(capacity),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(capacity)
        response.headers["X-RateLimit-Remaining"] = str(int(float(tokens)))
        return response

    @staticmethod
    def _identify(request: Request) -> tuple[str, int]:
        """Return (bucket subject, bucket capacity) for this request.

        A syntactically valid, signed, unexpired access token upgrades the
        caller to the authenticated tier; anything else is treated as an
        anonymous IP. Signature is verified — a forged token cannot buy the
        higher tier.
        """
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                claims = jwt.decode(
                    auth[7:],
                    settings.jwt_secret,
                    algorithms=[settings.jwt_algorithm],
                )
                if claims.get("type") == "access" and claims.get("sub"):
                    return (
                        f"user:{claims['sub']}",
                        settings.rate_limit_authenticated_per_minute,
                    )
            except jwt.InvalidTokenError:
                pass

        client_ip = request.client.host if request.client else "unknown"
        # Honor the first hop of X-Forwarded-For when behind the TLS proxy.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        return f"ip:{client_ip}", settings.rate_limit_anonymous_per_minute
