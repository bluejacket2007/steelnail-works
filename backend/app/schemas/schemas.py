"""Pydantic request/response contracts for the public API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.models import (
    CreditRating,
    Finish,
    HeadStyle,
    MilestoneStatus,
    MilestoneType,
    OrderStatus,
    RFQStatus,
    Role,
    ShankType,
)


# ── Auth ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    organization_name: str = Field(min_length=1, max_length=255)
    gstin: str | None = Field(default=None, max_length=15)
    ein: str | None = Field(default=None, max_length=10)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: str
    role: Role
    org_id: str | None


# ── Catalog ──────────────────────────────────────────────────────────────────

class ProductAttributeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    length_mm: Decimal
    length_inches: Decimal
    wire_gauge_awg: int | None
    wire_gauge_mm: Decimal
    head_style: HeadStyle
    shank_type: ShankType
    finish: Finish


class PricingTierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    moq_min_tons: Decimal
    moq_max_tons: Decimal | None
    price_per_kg: Decimal
    currency: str


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sku: str
    name: str
    description: str | None
    attributes: ProductAttributeOut | None
    pricing_tiers: list[PricingTierOut]


# ── RFQ / Quotes ─────────────────────────────────────────────────────────────

class RFQCreate(BaseModel):
    product_sku: str
    quantity_tons: Decimal = Field(gt=0)
    target_price_per_kg: Decimal | None = Field(default=None, gt=0)


class RFQOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    product_id: str
    product_sku: str
    quantity_tons: Decimal
    target_price_per_kg: Decimal | None
    status: RFQStatus
    agent_session_id: str | None
    created_at: datetime


class RFQTransition(BaseModel):
    new_status: RFQStatus


class QuoteCreate(BaseModel):
    quoted_price_per_kg: Decimal = Field(gt=0)
    quantity_tons: Decimal = Field(gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    valid_until: datetime | None = None


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    rfq_id: str
    quoted_price_per_kg: Decimal
    quantity_tons: Decimal
    currency: str
    margin_percent: Decimal
    issued_by_agent: bool
    valid_until: datetime | None
    is_accepted: bool


# ── Payments ─────────────────────────────────────────────────────────────────

class MilestoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    milestone_type: MilestoneType
    percentage: int
    amount: Decimal
    status: MilestoneStatus
    bol_verified: bool
    paid_at: datetime | None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    total_amount: Decimal
    currency: str
    status: OrderStatus
    milestones: list[MilestoneOut]


class PaymentInitiateRequest(BaseModel):
    milestone_id: str
    provider: str = Field(pattern="^(stripe|razorpay)$")


class PaymentInitiateResponse(BaseModel):
    milestone_id: str
    provider: str
    provider_payment_id: str
    client_secret: str | None
    amount: Decimal
    currency: str


class BolUploadRequest(BaseModel):
    document_ref: str = Field(min_length=1, max_length=255)


# ── Agent chat ───────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=8000)
    sku_context: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tools_called: list[str]
    escalation_ticket: str | None


# ── Org admin ────────────────────────────────────────────────────────────────

class CreditRatingUpdate(BaseModel):
    credit_rating: CreditRating
    credit_limit: Decimal = Field(ge=0)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    legal_name: str
    country_code: str
    gstin: str | None
    ein: str | None
    credit_rating: CreditRating
    credit_limit: Decimal
    parent_org_id: str | None
    is_verified: bool


# ── Public contact form ───────────────────────────────────────────────────────

class ContactInquiryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    company: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    message: str = Field(min_length=1, max_length=4000)


class ContactInquiryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    email: str
    company: str | None
    phone: str | None
    message: str
    handled: bool
    created_at: datetime
