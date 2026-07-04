"""Milestone Split-Payment State Machine.

Enforces the contractual B2B billing structure:

  30% ADVANCE  — must be paid before the order enters production.
  70% BALANCE  — may only be *initiated* after a Bill of Lading has been
                 uploaded AND verified by a SalesManager.

Milestone status transitions and the order status they drive:

  PENDING ──initiate──▶ INITIATED ──webhook:succeeded──▶ PAID
                             │
                             └──webhook:failed──▶ FAILED (re-initiable)

  ADVANCE PAID        → order: AWAITING_ADVANCE → IN_PRODUCTION
  BALANCE PAID        → order: AWAITING_BALANCE → SHIPPED
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import (
    LedgerEntry,
    LedgerEntryType,
    MilestoneStatus,
    MilestoneType,
    Order,
    OrderMilestone,
    OrderStatus,
    Quote,
    RFQ,
    RFQStatus,
)

_ALLOWED_TRANSITIONS: dict[MilestoneStatus, set[MilestoneStatus]] = {
    MilestoneStatus.PENDING: {MilestoneStatus.INITIATED},
    MilestoneStatus.INITIATED: {MilestoneStatus.PAID, MilestoneStatus.FAILED},
    MilestoneStatus.FAILED: {MilestoneStatus.INITIATED},
    MilestoneStatus.PAID: {MilestoneStatus.REFUNDED},
    MilestoneStatus.REFUNDED: set(),
}

_GENESIS_HASH = "0" * 64


class MilestoneTransitionError(Exception):
    pass


def create_order_milestones(db: Session, order: Order) -> list[OrderMilestone]:
    """Split the order total into the contractual 30/70 structure."""
    advance_amount = (
        order.total_amount * Decimal(settings.advance_percentage) / Decimal(100)
    ).quantize(Decimal("0.01"))
    balance_amount = order.total_amount - advance_amount  # no rounding drift

    milestones = [
        OrderMilestone(
            order_id=order.id,
            milestone_type=MilestoneType.ADVANCE_30,
            percentage=settings.advance_percentage,
            amount=advance_amount,
        ),
        OrderMilestone(
            order_id=order.id,
            milestone_type=MilestoneType.BALANCE_70,
            percentage=settings.balance_percentage,
            amount=balance_amount,
        ),
    ]
    db.add_all(milestones)
    db.flush()
    return milestones


def assert_can_initiate(db: Session, milestone: OrderMilestone) -> None:
    """Gatekeeper called before any payment intent is created."""
    if MilestoneStatus.INITIATED not in _ALLOWED_TRANSITIONS[milestone.status]:
        raise MilestoneTransitionError(
            f"Milestone is {milestone.status.value}; cannot initiate payment."
        )

    if milestone.milestone_type == MilestoneType.BALANCE_70:
        advance = db.execute(
            select(OrderMilestone).where(
                OrderMilestone.order_id == milestone.order_id,
                OrderMilestone.milestone_type == MilestoneType.ADVANCE_30,
            )
        ).scalar_one()
        if advance.status != MilestoneStatus.PAID:
            raise MilestoneTransitionError(
                "The 30% advance deposit must be PAID before the balance "
                "can be initiated."
            )
        if not milestone.bol_verified:
            raise MilestoneTransitionError(
                "The 70% balance requires a verified Bill of Lading. "
                "Upload the BoL and have it verified by a Sales Manager first."
            )


def mark_paid(db: Session, milestone: OrderMilestone) -> None:
    """Webhook-driven transition INITIATED → PAID; advances the order."""
    from datetime import datetime, timezone

    if MilestoneStatus.PAID not in _ALLOWED_TRANSITIONS[milestone.status]:
        raise MilestoneTransitionError(
            f"Cannot mark a {milestone.status.value} milestone as PAID."
        )
    milestone.status = MilestoneStatus.PAID
    milestone.paid_at = datetime.now(timezone.utc)

    order = db.get(Order, milestone.order_id)
    if milestone.milestone_type == MilestoneType.ADVANCE_30:
        order.status = OrderStatus.IN_PRODUCTION
    else:
        order.status = OrderStatus.SHIPPED
        _fulfill_linked_rfq(db, order)

    append_ledger_entry(
        db,
        order=order,
        milestone=milestone,
        entry_type=LedgerEntryType.CREDIT,
        amount=milestone.amount,
        description=(
            f"{milestone.milestone_type.value} milestone settled via "
            f"{milestone.provider.value if milestone.provider else 'unknown'} "
            f"({milestone.provider_payment_id})"
        ),
    )


def _fulfill_linked_rfq(db: Session, order: Order) -> None:
    """Once the 70% balance ships the order, the originating RFQ is complete."""
    quote = db.get(Quote, order.quote_id)
    if quote is None:
        return
    rfq = db.get(RFQ, quote.rfq_id)
    if rfq is not None and rfq.can_transition_to(RFQStatus.FULFILLED):
        rfq.status = RFQStatus.FULFILLED


def mark_failed(db: Session, milestone: OrderMilestone, reason: str) -> None:
    if MilestoneStatus.FAILED not in _ALLOWED_TRANSITIONS[milestone.status]:
        return  # late failure event for an already-settled milestone: ignore
    milestone.status = MilestoneStatus.FAILED
    append_ledger_entry(
        db,
        order=db.get(Order, milestone.order_id),
        milestone=milestone,
        entry_type=LedgerEntryType.DEBIT,
        amount=Decimal("0.00"),
        description=f"Payment attempt failed: {reason[:400]}",
    )


def append_ledger_entry(
    db: Session,
    *,
    order: Order,
    milestone: OrderMilestone | None,
    entry_type: LedgerEntryType,
    amount: Decimal,
    description: str,
) -> LedgerEntry:
    """Append a hash-chained, immutable ledger record for the order."""
    last = db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.order_id == order.id)
        .order_by(LedgerEntry.sequence.desc())
        .limit(1)
    ).scalar_one_or_none()

    prev_hash = last.entry_hash if last else _GENESIS_HASH
    sequence = (last.sequence + 1) if last else 1

    digest_input = "|".join(
        [prev_hash, order.id, str(sequence), entry_type.value, str(amount), description]
    )
    entry = LedgerEntry(
        order_id=order.id,
        milestone_id=milestone.id if milestone else None,
        sequence=sequence,
        entry_type=entry_type,
        amount=amount,
        currency=order.currency,
        description=description,
        prev_hash=prev_hash,
        entry_hash=hashlib.sha256(digest_input.encode()).hexdigest(),
    )
    db.add(entry)
    db.flush()
    return entry


def total_settled(db: Session, order_id: str) -> Decimal:
    return db.execute(
        select(func.coalesce(func.sum(OrderMilestone.amount), 0)).where(
            OrderMilestone.order_id == order_id,
            OrderMilestone.status == MilestoneStatus.PAID,
        )
    ).scalar_one()
