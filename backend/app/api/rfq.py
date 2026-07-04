"""RFQ lifecycle endpoints — the negotiation state machine.

Statuses: RFQ_Submitted → AI_Negotiating → Sales_Review → Approved →
Contract_Generated → Fulfilled (with Rejected as a terminal branch).
Illegal transitions are refused with 409 via RFQ_TRANSITIONS in models.py.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.rbac import get_current_user, require_roles
from app.models.models import (
    Product,
    RFQ,
    RFQStatus,
    Role,
    User,
)
from app.schemas.schemas import RFQCreate, RFQOut, RFQTransition

router = APIRouter(prefix="/api/v1/rfqs", tags=["rfq"])


@router.post("", response_model=RFQOut, status_code=201)
def submit_rfq(
    payload: RFQCreate,
    user: User = Depends(require_roles(Role.CLIENT_PROCUREMENT)),
    db: Session = Depends(get_db),
):
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no organization")

    product = db.execute(
        select(Product).where(Product.sku == payload.product_sku, Product.is_active.is_(True))
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Unknown product SKU")

    rfq = RFQ(
        buyer_org_id=user.org_id,
        created_by_user_id=user.id,
        product_id=product.id,
        quantity_tons=payload.quantity_tons,
        target_price_per_kg=payload.target_price_per_kg,
        agent_session_id=uuid.uuid4().hex,  # pre-provisioned AI negotiation room
    )
    db.add(rfq)
    db.commit()
    return rfq


@router.get("", response_model=list[RFQOut])
def list_rfqs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = (
        select(RFQ)
        .options(joinedload(RFQ.product))
        .order_by(RFQ.created_at.desc())
        .limit(200)
    )
    # Buyers see only their organization's RFQs; factory staff see all.
    if user.role == Role.CLIENT_PROCUREMENT:
        stmt = stmt.where(RFQ.buyer_org_id == user.org_id)
    return db.execute(stmt).unique().scalars().all()


@router.get("/{rfq_id}", response_model=RFQOut)
def get_rfq(rfq_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rfq = db.execute(
        select(RFQ).options(joinedload(RFQ.product)).where(RFQ.id == rfq_id)
    ).unique().scalar_one_or_none()
    if rfq is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if user.role == Role.CLIENT_PROCUREMENT and rfq.buyer_org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Not your organization's RFQ")
    return rfq


@router.post("/{rfq_id}/transition", response_model=RFQOut)
def transition_rfq(
    rfq_id: str,
    payload: RFQTransition,
    user: User = Depends(require_roles(Role.SALES_MANAGER, Role.SALES_REP)),
    db: Session = Depends(get_db),
):
    rfq = db.get(RFQ, rfq_id)
    if rfq is None:
        raise HTTPException(status_code=404, detail="RFQ not found")

    # Approval and contract generation are manager-only authority.
    manager_only = {RFQStatus.APPROVED, RFQStatus.CONTRACT_GENERATED, RFQStatus.REJECTED}
    if payload.new_status in manager_only and user.role not in (
        Role.SALES_MANAGER,
        Role.SUPER_ADMIN,
    ):
        raise HTTPException(status_code=403, detail="Requires SalesManager")

    if not rfq.can_transition_to(payload.new_status):
        raise HTTPException(
            status_code=409,
            detail=f"Illegal transition {rfq.status.value} → {payload.new_status.value}",
        )
    rfq.status = payload.new_status
    db.commit()
    return rfq
