"""Relational schema for the steel-nail B2B marketplace.

Modules
-------
1. Users & Organizations        — corporate profiles, tax IDs, credit ratings,
                                  parent-company relations, RBAC roles.
2. Products & Attributes        — heavily normalized industrial dimensions
                                  (length, wire gauge, head, shank, finish)
                                  with composite indexes for faceted search.
3. Tiered Bulk Pricing          — SKU × MOQ-range × price-per-kg matrix.
4. RFQ & Quote State Machine    — negotiation lifecycle tracking.
5. Orders, Milestones & Ledger  — 30/70 split billing, Bill-of-Lading
                                  verification, hash-chained ledger entries,
                                  webhook event dedupe, warehouse stock.
6. Contact Inquiries            — public marketing-site lead capture.

Sensitive columns (banking details, PII, negotiation transcripts) use the
``EncryptedString`` type — Fernet ciphertext at rest.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.security import EncryptedString


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ═══════════════════════ 1. Users & Organizations ════════════════════════════


class Role(str, enum.Enum):
    SUPER_ADMIN = "SuperAdmin"
    SALES_MANAGER = "SalesManager"
    SALES_REP = "SalesRep"
    CLIENT_PROCUREMENT = "ClientProcurement"


class CreditRating(str, enum.Enum):
    AAA = "AAA"
    AA = "AA"
    A = "A"
    BBB = "BBB"
    BB = "BB"
    B = "B"
    UNRATED = "UNRATED"


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    legal_name: Mapped[str] = mapped_column(String(255), index=True)
    country_code: Mapped[str] = mapped_column(String(2), default="IN")

    # Tax identifiers — searchable, so stored plaintext; uniqueness enforced.
    gstin: Mapped[str | None] = mapped_column(String(15), unique=True, nullable=True)
    ein: Mapped[str | None] = mapped_column(String(10), unique=True, nullable=True)

    credit_rating: Mapped[CreditRating] = mapped_column(
        Enum(CreditRating), default=CreditRating.UNRATED
    )
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))

    # Parent-company relation (self-referential, supports conglomerate trees).
    parent_org_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    parent: Mapped[Organization | None] = relationship(
        remote_side="Organization.id", back_populates="subsidiaries"
    )
    subsidiaries: Mapped[list[Organization]] = relationship(back_populates="parent")

    # Encrypted at rest: corporate banking + billing PII.
    bank_account_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    bank_ifsc_swift: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    billing_address: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    users: Mapped[list[User]] = relationship(back_populates="organization")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.CLIENT_PROCUREMENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Encrypted PII.
    phone: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)

    org_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    organization: Mapped[Organization | None] = relationship(back_populates="users")


# ═══════════════════ 2. Products & Industrial Attributes ═════════════════════


class HeadStyle(str, enum.Enum):
    FLAT = "Flat"
    CHECKERED = "Checkered"
    COUNTERSUNK = "Countersunk"


class ShankType(str, enum.Enum):
    SMOOTH = "Smooth"
    RING = "Ring"
    SCREW = "Screw"


class Finish(str, enum.Enum):
    BRIGHT = "Bright"
    ELECTRO_GALVANIZED = "Electro-Galvanized"
    HOT_DIP_GALVANIZED = "Hot-Dip Galvanized"
    STAINLESS_STEEL = "Stainless Steel"


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    attributes: Mapped[ProductAttribute | None] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
    )
    pricing_tiers: Mapped[list[BulkPricingTier]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    stock: Mapped[list[WarehouseStock]] = relationship(back_populates="product")


class ProductAttribute(TimestampMixin, Base):
    """Normalized industrial dimensions — one row per product.

    Dual units are stored precomputed (inches↔mm, AWG↔mm) so the catalog can
    be filtered in either system without conversion at query time.
    """

    __tablename__ = "product_attributes"
    __table_args__ = (
        # Composite indexes covering the dominant multi-faceted catalog
        # searches: "2.5in / 11-gauge / hot-dip galvanized ring shank".
        Index("ix_attr_len_gauge_finish", "length_mm", "wire_gauge_mm", "finish"),
        Index("ix_attr_finish_shank_head", "finish", "shank_type", "head_style"),
        CheckConstraint("length_mm > 0", name="ck_attr_length_positive"),
        CheckConstraint("wire_gauge_mm > 0", name="ck_attr_gauge_positive"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), unique=True
    )

    length_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    length_inches: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    wire_gauge_awg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wire_gauge_mm: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    head_style: Mapped[HeadStyle] = mapped_column(Enum(HeadStyle))
    shank_type: Mapped[ShankType] = mapped_column(Enum(ShankType))
    finish: Mapped[Finish] = mapped_column(Enum(Finish))

    product: Mapped[Product] = relationship(back_populates="attributes")


class WarehouseStock(TimestampMixin, Base):
    __tablename__ = "warehouse_stock"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_code", name="uq_stock_product_wh"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    warehouse_code: Mapped[str] = mapped_column(String(16))
    quantity_tons: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))

    product: Mapped[Product] = relationship(back_populates="stock")


# ═══════════════════════ 3. Tiered Bulk Pricing ══════════════════════════════


class BulkPricingTier(TimestampMixin, Base):
    """SKU × MOQ-range → price-per-kg.

    ``moq_max_tons IS NULL`` denotes an open-ended top tier (e.g. "20+ tons").
    """

    __tablename__ = "bulk_pricing_tiers"
    __table_args__ = (
        UniqueConstraint("product_id", "moq_min_tons", name="uq_tier_product_min"),
        Index("ix_tier_product_range", "product_id", "moq_min_tons", "moq_max_tons"),
        CheckConstraint("moq_min_tons >= 0", name="ck_tier_min_nonnegative"),
        CheckConstraint(
            "moq_max_tons IS NULL OR moq_max_tons > moq_min_tons",
            name="ck_tier_range_valid",
        ),
        CheckConstraint("price_per_kg > 0", name="ck_tier_price_positive"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    moq_min_tons: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    moq_max_tons: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    price_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    currency: Mapped[str] = mapped_column(String(3), default="INR")

    product: Mapped[Product] = relationship(back_populates="pricing_tiers")


# ═══════════════════ 4. RFQ & Quote State Machine ════════════════════════════


class RFQStatus(str, enum.Enum):
    RFQ_SUBMITTED = "RFQ_Submitted"
    AI_NEGOTIATING = "AI_Negotiating"
    SALES_REVIEW = "Sales_Review"
    APPROVED = "Approved"
    CONTRACT_GENERATED = "Contract_Generated"
    FULFILLED = "Fulfilled"
    REJECTED = "Rejected"


# Legal transitions — enforced by the API layer before any status write.
RFQ_TRANSITIONS: dict[RFQStatus, set[RFQStatus]] = {
    RFQStatus.RFQ_SUBMITTED: {RFQStatus.AI_NEGOTIATING, RFQStatus.SALES_REVIEW, RFQStatus.REJECTED},
    RFQStatus.AI_NEGOTIATING: {RFQStatus.SALES_REVIEW, RFQStatus.REJECTED},
    RFQStatus.SALES_REVIEW: {RFQStatus.APPROVED, RFQStatus.AI_NEGOTIATING, RFQStatus.REJECTED},
    RFQStatus.APPROVED: {RFQStatus.CONTRACT_GENERATED},
    RFQStatus.CONTRACT_GENERATED: {RFQStatus.FULFILLED},
    RFQStatus.FULFILLED: set(),
    RFQStatus.REJECTED: set(),
}


class RFQ(TimestampMixin, Base):
    __tablename__ = "rfqs"
    __table_args__ = (
        Index("ix_rfq_status_created", "status", "created_at"),
        CheckConstraint("quantity_tons > 0", name="ck_rfq_qty_positive"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    buyer_org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))

    quantity_tons: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    target_price_per_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    status: Mapped[RFQStatus] = mapped_column(Enum(RFQStatus), default=RFQStatus.RFQ_SUBMITTED)

    # Proprietary negotiation transcript — encrypted at rest (JSON string).
    negotiation_history: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    agent_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    buyer_org: Mapped[Organization] = relationship()
    product: Mapped[Product] = relationship()
    quotes: Mapped[list[Quote]] = relationship(back_populates="rfq")

    def can_transition_to(self, new_status: RFQStatus) -> bool:
        return new_status in RFQ_TRANSITIONS[self.status]

    @property
    def product_sku(self) -> str:
        """Convenience accessor so API responses can surface the SKU without
        the caller having to make a second round trip to the catalog."""
        return self.product.sku


class Quote(TimestampMixin, Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    rfq_id: Mapped[str] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"))
    quoted_price_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    quantity_tons: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    margin_percent: Mapped[Decimal] = mapped_column(Numeric(6, 4))  # audit trail
    issued_by_agent: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False)

    rfq: Mapped[RFQ] = relationship(back_populates="quotes")


# ═══════════════ 5. Orders, Milestones & Financial Ledger ════════════════════


class OrderStatus(str, enum.Enum):
    AWAITING_ADVANCE = "Awaiting_Advance"
    IN_PRODUCTION = "In_Production"
    AWAITING_BOL = "Awaiting_BOL"
    AWAITING_BALANCE = "Awaiting_Balance"
    SHIPPED = "Shipped"
    CLOSED = "Closed"
    CANCELLED = "Cancelled"


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    buyer_org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.AWAITING_ADVANCE)

    quote: Mapped[Quote] = relationship()
    buyer_org: Mapped[Organization] = relationship()
    milestones: Mapped[list[OrderMilestone]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    ledger_entries: Mapped[list[LedgerEntry]] = relationship(back_populates="order")


class MilestoneType(str, enum.Enum):
    ADVANCE_30 = "Advance_30"    # deposit that releases production
    BALANCE_70 = "Balance_70"    # cleared against verified Bill of Lading


class MilestoneStatus(str, enum.Enum):
    PENDING = "Pending"
    INITIATED = "Initiated"
    PAID = "Paid"
    FAILED = "Failed"
    REFUNDED = "Refunded"


class PaymentProvider(str, enum.Enum):
    STRIPE = "stripe"
    RAZORPAY = "razorpay"


class OrderMilestone(TimestampMixin, Base):
    """One financial clearance stage of an order (30% advance / 70% balance)."""

    __tablename__ = "order_milestones"
    __table_args__ = (
        UniqueConstraint("order_id", "milestone_type", name="uq_milestone_order_type"),
        Index("ix_milestone_provider_ref", "provider", "provider_payment_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    milestone_type: Mapped[MilestoneType] = mapped_column(Enum(MilestoneType))
    percentage: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[MilestoneStatus] = mapped_column(Enum(MilestoneStatus), default=MilestoneStatus.PENDING)

    provider: Mapped[PaymentProvider | None] = mapped_column(Enum(PaymentProvider), nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)

    # Bill of Lading gate for the 70% balance milestone.
    bol_document_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bol_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    bol_verified_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[Order] = relationship(back_populates="milestones")


class LedgerEntryType(str, enum.Enum):
    DEBIT = "Debit"
    CREDIT = "Credit"


class LedgerEntry(Base):
    """Append-only, hash-chained financial ledger.

    Each entry stores the SHA-256 of the previous entry plus its own payload,
    so any retroactive tampering with the money trail breaks the chain and is
    detectable by a linear audit walk. Rows are never updated or deleted.
    """

    __tablename__ = "ledger_entries"
    __table_args__ = (Index("ix_ledger_order_seq", "order_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    milestone_id: Mapped[str | None] = mapped_column(ForeignKey("order_milestones.id"), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer)
    entry_type: Mapped[LedgerEntryType] = mapped_column(Enum(LedgerEntryType))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    description: Mapped[str] = mapped_column(String(512))
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    order: Mapped[Order] = relationship(back_populates="ledger_entries")


class WebhookEvent(Base):
    """Dedupe + audit store for inbound payment webhooks.

    ``provider_event_id`` is unique, so redelivered webhooks are processed
    exactly once regardless of provider retry behavior.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_webhook_provider_event"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    provider: Mapped[PaymentProvider] = mapped_column(Enum(PaymentProvider))
    provider_event_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(128))
    payload: Mapped[str] = mapped_column(Text)  # raw JSON, for replay/audit
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ═══════════════════ 6. Public Contact Inquiries ═════════════════════════════


class ContactInquiry(TimestampMixin, Base):
    """Lead-capture form submitted from the public marketing site.

    Publicly writable (no auth) but still passes through the global XSS
    sanitizer and rate limiter like every other mutating endpoint.
    """

    __tablename__ = "contact_inquiries"
    __table_args__ = (Index("ix_contact_handled_created", "handled", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    handled: Mapped[bool] = mapped_column(Boolean, default=False)
    handled_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
