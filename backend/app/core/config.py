"""Central application configuration.

Every security-sensitive value (DB credentials, pool sizing, JWT secret,
Fernet keys, provider secrets) is sourced from the environment so nothing
sensitive is ever committed to the repository.
"""
from __future__ import annotations

import secrets
import warnings
from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── Database / connection pooling ────────────────────────────────────
    database_url: str = (
        "postgresql+psycopg2://nailfactory:nailfactory_dev_only@localhost:5432/nailfactory"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30          # seconds to wait for a pooled connection
    db_pool_recycle: int = 1800        # recycle connections before server-side timeouts
    auto_create_tables: bool = True    # dev convenience; use Alembic in production

    # ── Redis ────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Auth / JWT ───────────────────────────────────────────────────────
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── Field-level encryption ───────────────────────────────────────────
    # Comma-separated Fernet keys. First key encrypts; all keys decrypt,
    # which makes zero-downtime key rotation possible (MultiFernet).
    fernet_keys: str = ""

    # ── Network security ─────────────────────────────────────────────────
    cors_allowed_origins: str = "http://localhost:3000"
    allowed_hosts: str = "localhost,127.0.0.1"
    enforce_https: bool = False
    rate_limit_anonymous_per_minute: int = 60
    rate_limit_authenticated_per_minute: int = 200
    # Interactive Swagger UI documents the entire API surface to anyone who
    # finds the URL — fine for local development, a needless attack-surface
    # hint on a live commercial deployment. Default on for dev convenience;
    # render.yaml sets this to false for production.
    expose_api_docs: bool = True

    # ── Payments ─────────────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    default_currency: str = "INR"
    advance_percentage: int = 30       # 30% deposit to start production
    balance_percentage: int = 70       # 70% cleared against verified Bill of Lading

    # ── AI Agent ─────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    agent_session_ttl_seconds: int = 86_400
    agent_max_tool_iterations: int = 10

    # ── Costing / margin guardrails ──────────────────────────────────────
    raw_wire_rod_cost_per_kg: float = 62.0    # current raw material market cost
    processing_overhead_per_kg: float = 18.0  # drawing, cutting, heading, packing
    net_margin_floor: float = 0.12            # the agent may NEVER quote below this

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def fernet_keys_list(self) -> list[bytes]:
        return [k.strip().encode() for k in self.fernet_keys.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # Fail safe in development: generate ephemeral secrets instead of running
    # with predictable ones. Production deployments MUST set these explicitly —
    # ephemeral secrets invalidate all tokens/ciphertext on restart.
    if not settings.jwt_secret or settings.jwt_secret.startswith("CHANGE_ME"):
        warnings.warn(
            "JWT_SECRET not configured — generated an ephemeral secret. "
            "Set JWT_SECRET in the environment for production.",
            stacklevel=1,
        )
        settings.jwt_secret = secrets.token_urlsafe(64)

    if not settings.fernet_keys or settings.fernet_keys.startswith("CHANGE_ME"):
        warnings.warn(
            "FERNET_KEYS not configured — generated an ephemeral key. "
            "Existing ciphertext will be unreadable after restart. "
            "Set FERNET_KEYS in the environment for production.",
            stacklevel=1,
        )
        settings.fernet_keys = Fernet.generate_key().decode()

    return settings


settings = get_settings()
