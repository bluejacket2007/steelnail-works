"""Application entrypoint — middleware stack and router wiring.

Middleware execution order (outermost first):
  TrustedHost → [HTTPSRedirect] → CORS → SecurityHeaders → RateLimiter
  → Idempotency → XSSSanitizer → routes

Starlette applies add_middleware() in reverse, so registration below is
innermost-first.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import admin, agent_chat, auth, catalog, contact, payments, quotes, rfq
from app.core.config import settings
from app.core.database import Base, engine
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.rate_limiter import TokenBucketRateLimiter
from app.middleware.sanitizer import XSSSanitizerMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.payments import webhooks

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        # Dev convenience only — production migrations belong to Alembic.
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Steel Nail Factory — B2B Marketplace API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.expose_api_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.expose_api_docs else None,
)

# Innermost-first registration (see module docstring).
app.add_middleware(XSSSanitizerMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(TokenBucketRateLimiter)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,   # strict allowlist — never "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Idempotency-Key"],
    max_age=600,
)
if settings.enforce_https:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(rfq.router)
app.include_router(quotes.router)
app.include_router(payments.router)
app.include_router(admin.router)
app.include_router(contact.router)
app.include_router(agent_chat.router)
app.include_router(webhooks.router)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}
