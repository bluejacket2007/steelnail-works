"""Quote issuance and acceptance — the bridge between an approved RFQ and a
contract-backed Order with milestone billing.

Flow:
  SalesRep/SalesManager issues a Quote against an RFQ (any pre-Approved
  status) → RFQ is moved through Sales_Review → Approved via the existing
  /rfqs/{id}/transition endpoint → buyer accepts the quote here, which
  atomically creates the Order, splits it into 30/70 milestones, and
  advances the RFQ to Contract_Generated.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.guardrails import MarginFloorViolation, compute_floor_price
from app.core.database import get_db
from app.core.rbac import get_current_user, require_roles
from app.models.models import (
    Order,
    OrderStatus,
    Quote,
    RFQ,
    RFQStatus,
    Role,
    User,
)
from app.payments.milestones import create_order_milestones
from app.schemas.schemas import OrderOut, QuoteCreate, QuoteOut

router = APIRouter(tags=["quotes"])


def _load_rfq_or_404(db: Session, rfq_id: str) -> RFQ:
    rfq = db.get(RFQ, rfq_id)
    if rfq is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return rfq


@router.post("/api/v1/rfqs/{rfq_id}/quotes", response_model=QuoteOut, status_code=201)
def issue_quote(
    rfq_id: str,
    payload: QuoteCreate,
    user: User = Depends(require_roles(Role.SALES_REP, Role.SALES_MANAGER)),
    db: Session = Depends(get_db),
):
    rfq = _load_rfq_or_404(db, rfq_id)
    if rfq.status in (RFQStatus.FULFILLED, RFQStatus.REJECTED, RFQStatus.CONTRACT_GENERATED):
        raise HTTPException(
            status_code=409, detail=f"Cannot quote an RFQ in status {rfq.status.value}"
        )

    # A human quote is still bound by the margin floor — the guardrail is a
    # company policy, not just an AI-agent restriction.
    floor = compute_floor_price_for_rfq(db, rfq)
    if payload.quoted_price_per_kg < floor:
        raise HTTPException(
            status_code=422,
            detail=f"Quoted price {payload.quoted_price_per_kg}/kg is below the "
            f"{floor}/kg net-margin floor.",
        )
    margin_percent = (
        (payload.quoted_price_per_kg - floor) / payload.quoted_price_per_kg
    ).quantize(Decimal("0.0001")) if payload.quoted_price_per_kg else Decimal("0")

    quote = Quote(
        rfq_id=rfq.id,
        quoted_price_per_kg=payload.quoted_price_per_kg,
        quantity_tons=payload.quantity_tons,
        currency=payload.currency,
        margin_percent=margin_percent,
        issued_by_agent=False,
        valid_until=payload.valid_until,
    )
    db.add(quote)
    db.commit()
    return quote


def compute_floor_price_for_rfq(db: Session, rfq: RFQ) -> Decimal:
    from app.models.models import Product

    product = db.get(Product, rfq.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="RFQ references an unknown product")
    return compute_floor_price(product.sku)


@router.get("/api/v1/rfqs/{rfq_id}/quotes", response_model=list[QuoteOut])
def list_quotes(
    rfq_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rfq = _load_rfq_or_404(db, rfq_id)
    if user.role == Role.CLIENT_PROCUREMENT and rfq.buyer_org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Not your organization's RFQ")
    return db.execute(
        select(Quote).where(Quote.rfq_id == rfq_id).order_by(Quote.created_at.desc())
    ).scalars().all()


@router.post("/api/v1/quotes/{quote_id}/accept", response_model=OrderOut, status_code=201)
def accept_quote(
    quote_id: str,
    user: User = Depends(require_roles(Role.CLIENT_PROCUREMENT)),
    db: Session = Depends(get_db),
):
    """Buyer acceptance — generates the contract (Order + milestones)."""
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    rfq = db.get(RFQ, quote.rfq_id)
    if rfq.buyer_org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Not your organization's RFQ")
    if rfq.status != RFQStatus.APPROVED:
        raise HTTPException(
            status_code=409,
            detail="Only quotes on an Approved RFQ can be accepted. "
            f"Current status: {rfq.status.value}",
        )
    if quote.is_accepted:
        raise HTTPException(status_code=409, detail="Quote already accepted")

    existing_order = db.execute(
        select(Order).where(Order.quote_id == quote.id)
    ).scalar_one_or_none()
    if existing_order is not None:
        raise HTTPException(status_code=409, detail="An order already exists for this quote")

    total_amount = (
        quote.quoted_price_per_kg * quote.quantity_tons * Decimal("1000")
    ).quantize(Decimal("0.01"))  # tons → kg

    order = Order(
        quote_id=quote.id,
        buyer_org_id=rfq.buyer_org_id,
        total_amount=total_amount,
        currency=quote.currency,
        status=OrderStatus.AWAITING_ADVANCE,
    )
    db.add(order)
    db.flush()

    create_order_milestones(db, order)

    quote.is_accepted = True
    rfq.status = RFQStatus.CONTRACT_GENERATED

    db.commit()
    db.refresh(order)
    return order
