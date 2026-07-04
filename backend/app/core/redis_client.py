"""Redis connections.

Two clients are exposed:

- ``get_async_redis()`` — asyncio client used inside ASGI middleware
  (rate limiting, idempotency) where the event loop must not block.
- ``get_sync_redis()``  — blocking client used from threadpool code paths
  (agent conversation memory, CRM escalations, catalog caching).
"""
from __future__ import annotations

import redis
import redis.asyncio as aioredis

from app.core.config import settings

_sync_pool = redis.ConnectionPool.from_url(
    settings.redis_url, decode_responses=True, max_connections=50
)
_async_pool = aioredis.ConnectionPool.from_url(
    settings.redis_url, decode_responses=True, max_connections=50
)


def get_sync_redis() -> redis.Redis:
    return redis.Redis(connection_pool=_sync_pool)


def get_async_redis() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=_async_pool)
