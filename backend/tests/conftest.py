"""Test configuration.

Runs the real application code against an in-memory SQLite database
(StaticPool, so every connection shares the same in-process DB — see
app/core/database.py's dialect-aware pooling) instead of PostgreSQL, and
never touches a live Redis server. Environment variables are set before any
``app.*`` module is imported anywhere in the test session, since
``app.core.config.settings`` is a module-level singleton resolved at import
time.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "pytest-secret-not-for-production")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AUTO_CREATE_TABLES", "false")  # tests create tables themselves
os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
os.environ.setdefault("ENFORCE_HTTPS", "false")
os.environ.setdefault("RAW_WIRE_ROD_COST_PER_KG", "62.0")
os.environ.setdefault("PROCESSING_OVERHEAD_PER_KG", "18.0")
os.environ.setdefault("NET_MARGIN_FLOOR", "0.12")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "rzp_whsec_test_secret")

from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("FERNET_KEYS", Fernet.generate_key().decode())

import pytest  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def fake_redis(monkeypatch):
    """Patch every module-level ``get_sync_redis``/``get_async_redis`` import
    with a shared fakeredis instance, so Redis-touching code (refresh-token
    allowlist, escalation queue) is exercised for real without a live server.
    """
    import fakeredis

    import app.agent.tools as tools_module
    import app.core.security as security_module

    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(security_module, "get_sync_redis", lambda: fake)
    monkeypatch.setattr(tools_module, "get_sync_redis", lambda: fake)
    return fake


def make_product(
    db_session,
    *,
    sku: str,
    finish: str = "Bright",
    shank_type: str = "Smooth",
    head_style: str = "Flat",
    length_mm: str = "63.00",
    wire_gauge_mm: str = "3.050",
    wire_gauge_awg: int | None = 11,
    tiers: list[tuple[str, str | None, str]] | None = None,
    stock_tons: str | None = "50",
):
    """Insert a Product + ProductAttribute (+ optional tiers/stock) and commit."""
    from app.models.models import BulkPricingTier, Product, ProductAttribute, WarehouseStock

    product = Product(sku=sku, name=f"Test product {sku}")
    db_session.add(product)
    db_session.flush()

    db_session.add(
        ProductAttribute(
            product_id=product.id,
            length_mm=length_mm,
            length_inches="2.500",
            wire_gauge_awg=wire_gauge_awg,
            wire_gauge_mm=wire_gauge_mm,
            head_style=head_style,
            shank_type=shank_type,
            finish=finish,
        )
    )

    for min_tons, max_tons, price in (
        tiers
        if tiers is not None
        else [("1", "5", "95.00"), ("5", "20", "90.00"), ("20", None, "85.00")]
    ):
        db_session.add(
            BulkPricingTier(
                product_id=product.id,
                moq_min_tons=min_tons,
                moq_max_tons=max_tons,
                price_per_kg=price,
            )
        )

    if stock_tons is not None:
        db_session.add(
            WarehouseStock(product_id=product.id, warehouse_code="WH-N1", quantity_tons=stock_tons)
        )

    db_session.commit()
    return product


def make_organization(db_session, *, legal_name: str = "Acme Fasteners", credit_rating: str = "AA"):
    from app.models.models import Organization

    org = Organization(legal_name=legal_name, credit_rating=credit_rating)
    db_session.add(org)
    db_session.commit()
    return org
