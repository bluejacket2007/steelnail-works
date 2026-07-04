"""Milestone payment endpoints.

All POSTs here sit behind IdempotencyMiddleware — a valid X-Idempotency-Key
is mandatory, and the same key can never initiate two charges. The key is
additionally forwarded to the provider, so even a middleware bypass could
not double-capture.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.rbac import get_current_user, require_roles
from app.models.models import (
    Order,
    OrderMilestone,
    OrderStatus,
    PaymentProvider,
    Role,
    User,
)
from app.payments import milestones as milestone_sm
from app.payments.base import PaymentError
from app.payments.milestones import MilestoneTransitionError
from app.payments.razorpay_provider import get_provider
from app.schemas.schemas import (
    BolUploadRequest,
    MilestoneOut,
    OrderOut,
    PaymentInitiateRequest,
    PaymentInitiateResponse,
)
from app.models.models import MilestoneStatus

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


@router.get("/orders", response_model=list[OrderOut])
def list_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Order).options(joinedload(Order.milestones)).order_by(Order.created_at.desc())
    if user.role == Role.CLIENT_PROCUREMENT:
        stmt = stmt.where(Order.buyer_org_id == user.org_id)
    return db.execute(stmt).unique().scalars().all()


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    order = db.execute(
        select(Order).options(joinedload(Order.milestones)).where(Order.id == order_id)
    ).unique().scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if user.role == Role.CLIENT_PROCUREMENT and order.buyer_org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Not your organization's order")
    return order


@router.post("/initiate", response_model=PaymentInitiateResponse)
def initiate_milestone_payment(
    payload: PaymentInitiateRequest,
    request: Request,
    user: User = Depends(require_roles(Role.CLIENT_PROCUREMENT)),
    db: Session = Depends(get_db),
):
    milestone = db.get(OrderMilestone, payload.milestone_id)
    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")

    order = db.get(Order, milestone.order_id)
    if order.buyer_org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Not your organization's order")

    # State machine gate: enforces PAID advance + verified BoL for the 70%.
    try:
        milestone_sm.assert_can_initiate(db, milestone)
    except MilestoneTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    idempotency_key = request.headers.get("x-idempotency-key", "")
    provider = get_provider(payload.provider)
    try:
        intent = provider.create_payment_intent(
            amount=milestone.amount,
            currency=order.currency,
            idempotency_key=idempotency_key,
            metadata={
                "order_id": order.id,
                "milestone_id": milestone.id,
                "milestone_type": milestone.milestone_type.value,
            },
        )
    except PaymentError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    milestone.status = MilestoneStatus.INITIATED
    milestone.provider = PaymentProvider(payload.provider)
    milestone.provider_payment_id = intent.provider_payment_id
    milestone.idempotency_key = idempotency_key
    db.commit()

    return PaymentInitiateResponse(
        milestone_id=milestone.id,
        provider=intent.provider,
        provider_payment_id=intent.provider_payment_id,
        client_secret=intent.client_secret,
        amount=intent.amount,
        currency=intent.currency,
    )


@router.post("/milestones/{milestone_id}/bol", response_model=MilestoneOut)
def upload_bill_of_lading(
    milestone_id: str,
    payload: BolUploadRequest,
    user: User = Depends(require_roles(Role.CLIENT_PROCUREMENT, Role.SALES_REP)),
    db: Session = Depends(get_db),
):
    """Attach the Bill of Lading reference to the 70% balance milestone."""
    milestone = db.get(OrderMilestone, milestone_id)
    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    milestone.bol_document_ref = payload.document_ref
    milestone.bol_verified = False  # any re-upload resets verification

    order = db.get(Order, milestone.order_id)
    if order.status == OrderStatus.IN_PRODUCTION:
        order.status = OrderStatus.AWAITING_BOL
    db.commit()
    return milestone


@router.post("/milestones/{milestone_id}/bol/verify", response_model=MilestoneOut)
def verify_bill_of_lading(
    milestone_id: str,
    user: User = Depends(require_roles(Role.SALES_MANAGER)),
    db: Session = Depends(get_db),
):
    """SalesManager sign-off that unlocks initiation of the 70% balance."""
    milestone = db.get(OrderMilestone, milestone_id)
    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    if not milestone.bol_document_ref:
        raise HTTPException(status_code=409, detail="No Bill of Lading uploaded yet")

    milestone.bol_verified = True
    milestone.bol_verified_by = user.id

    order = db.get(Order, milestone.order_id)
    if order.status in (OrderStatus.AWAITING_BOL, OrderStatus.IN_PRODUCTION):
        order.status = OrderStatus.AWAITING_BALANCE
    db.commit()
    return milestone
