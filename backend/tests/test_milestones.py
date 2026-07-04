"""Milestone split-payment state machine + the hash-chained ledger.

Covers: the 30/70 split arithmetic, the Bill-of-Lading gate that blocks the
balance milestone, the webhook-driven PAID transition (including the RFQ ->
Fulfilled cascade), and the integrity properties of the append-only ledger.
"""
from decimal import Decimal

import pytest

from app.models.models import (
    LedgerEntryType,
    MilestoneStatus,
    MilestoneType,
    Order,
    OrderStatus,
    Quote,
    RFQ,
    RFQStatus,
    Role,
    User,
)
from app.payments.milestones import (
    MilestoneTransitionError,
    append_ledger_entry,
    assert_can_initiate,
    create_order_milestones,
    mark_paid,
    total_settled,
)
from tests.conftest import make_organization, make_product


def _build_order(db_session, *, email: str, total_amount: str = "1300000.00"):
    """RFQ -> Quote -> Order chain, mirroring what quotes.accept_quote builds."""
    org = make_organization(db_session, legal_name=f"Org for {email}")
    product = make_product(db_session, sku=f"SKU-{email}")
    user = User(
        email=email,
        hashed_password="not-a-real-hash",
        full_name="Test Buyer",
        role=Role.CLIENT_PROCUREMENT,
        org_id=org.id,
    )
    db_session.add(user)
    db_session.flush()

    rfq = RFQ(
        buyer_org_id=org.id,
        created_by_user_id=user.id,
        product_id=product.id,
        quantity_tons=Decimal("10"),
        status=RFQStatus.APPROVED,
    )
    db_session.add(rfq)
    db_session.flush()

    quote = Quote(
        rfq_id=rfq.id,
        quoted_price_per_kg=Decimal("130.00"),
        quantity_tons=Decimal("10"),
        margin_percent=Decimal("0.30"),
    )
    db_session.add(quote)
    db_session.flush()

    order = Order(
        quote_id=quote.id,
        buyer_org_id=org.id,
        total_amount=Decimal(total_amount),
        status=OrderStatus.AWAITING_ADVANCE,
    )
    db_session.add(order)
    db_session.flush()
    db_session.commit()
    return rfq, quote, order


def test_milestones_split_30_70_with_no_rounding_drift(db_session):
    _, _, order = _build_order(db_session, email="split@test.example", total_amount="1000000.00")
    milestones = create_order_milestones(db_session, order)
    db_session.commit()

    advance = next(m for m in milestones if m.milestone_type == MilestoneType.ADVANCE_30)
    balance = next(m for m in milestones if m.milestone_type == MilestoneType.BALANCE_70)

    assert advance.amount == Decimal("300000.00")
    assert balance.amount == Decimal("700000.00")
    assert advance.amount + balance.amount == order.total_amount


def test_balance_cannot_initiate_before_advance_is_paid(db_session):
    _, _, order = _build_order(db_session, email="gate1@test.example")
    milestones = create_order_milestones(db_session, order)
    db_session.commit()
    balance = next(m for m in milestones if m.milestone_type == MilestoneType.BALANCE_70)

    with pytest.raises(MilestoneTransitionError, match="advance deposit must be PAID"):
        assert_can_initiate(db_session, balance)


def test_balance_cannot_initiate_without_verified_bol(db_session):
    _, _, order = _build_order(db_session, email="gate2@test.example")
    milestones = create_order_milestones(db_session, order)
    advance = next(m for m in milestones if m.milestone_type == MilestoneType.ADVANCE_30)
    balance = next(m for m in milestones if m.milestone_type == MilestoneType.BALANCE_70)

    advance.status = MilestoneStatus.PAID
    db_session.commit()

    with pytest.raises(MilestoneTransitionError, match="verified Bill of Lading"):
        assert_can_initiate(db_session, balance)

    balance.bol_verified = True
    db_session.commit()
    assert_can_initiate(db_session, balance)  # should not raise now


def test_mark_paid_advance_moves_order_to_in_production(db_session):
    _, _, order = _build_order(db_session, email="paid1@test.example")
    milestones = create_order_milestones(db_session, order)
    advance = next(m for m in milestones if m.milestone_type == MilestoneType.ADVANCE_30)
    advance.status = MilestoneStatus.INITIATED
    db_session.commit()

    mark_paid(db_session, advance)
    db_session.commit()

    assert advance.status == MilestoneStatus.PAID
    assert advance.paid_at is not None
    assert order.status == OrderStatus.IN_PRODUCTION


def test_mark_paid_balance_ships_order_and_fulfills_rfq(db_session):
    rfq, _, order = _build_order(db_session, email="paid2@test.example")
    milestones = create_order_milestones(db_session, order)
    advance = next(m for m in milestones if m.milestone_type == MilestoneType.ADVANCE_30)
    balance = next(m for m in milestones if m.milestone_type == MilestoneType.BALANCE_70)

    advance.status = MilestoneStatus.PAID
    rfq.status = RFQStatus.CONTRACT_GENERATED  # accept_quote's real effect
    balance.status = MilestoneStatus.INITIATED
    balance.bol_verified = True
    db_session.commit()

    mark_paid(db_session, balance)
    db_session.commit()

    assert order.status == OrderStatus.SHIPPED
    assert rfq.status == RFQStatus.FULFILLED


def test_mark_paid_rejects_illegal_source_status(db_session):
    _, _, order = _build_order(db_session, email="illegal@test.example")
    milestones = create_order_milestones(db_session, order)
    advance = next(m for m in milestones if m.milestone_type == MilestoneType.ADVANCE_30)
    # Still PENDING — mark_paid requires INITIATED as the source state.
    with pytest.raises(MilestoneTransitionError):
        mark_paid(db_session, advance)


def test_ledger_entries_form_a_hash_chain(db_session):
    _, _, order = _build_order(db_session, email="ledger1@test.example")
    e1 = append_ledger_entry(
        db_session, order=order, milestone=None,
        entry_type=LedgerEntryType.CREDIT,
        amount=Decimal("100.00"), description="first entry",
    )
    e2 = append_ledger_entry(
        db_session, order=order, milestone=None,
        entry_type=LedgerEntryType.CREDIT,
        amount=Decimal("50.00"), description="second entry",
    )
    db_session.commit()

    assert e1.sequence == 1
    assert e2.sequence == 2
    assert e2.prev_hash == e1.entry_hash
    assert e1.prev_hash == "0" * 64
    assert e1.entry_hash != e2.entry_hash


def test_ledger_hash_is_deterministic_and_detects_tampering(db_session):
    _, _, order = _build_order(db_session, email="ledger2@test.example")
    entry = append_ledger_entry(
        db_session, order=order, milestone=None,
        entry_type=LedgerEntryType.CREDIT, amount=Decimal("100.00"),
        description="genesis-adjacent entry",
    )
    db_session.commit()

    import hashlib

    recomputed = hashlib.sha256(
        "|".join([entry.prev_hash, order.id, str(entry.sequence), entry.entry_type.value,
                  str(entry.amount), entry.description]).encode()
    ).hexdigest()
    assert recomputed == entry.entry_hash

    # Tampering with the recorded amount must produce a different digest —
    # this is what an audit/verification job would use to detect corruption.
    tampered = hashlib.sha256(
        "|".join([entry.prev_hash, order.id, str(entry.sequence), entry.entry_type.value,
                  "999999.99", entry.description]).encode()
    ).hexdigest()
    assert tampered != entry.entry_hash


def test_total_settled_only_counts_paid_milestones(db_session):
    _, _, order = _build_order(db_session, email="settled@test.example")
    milestones = create_order_milestones(db_session, order)
    advance = next(m for m in milestones if m.milestone_type == MilestoneType.ADVANCE_30)
    advance.status = MilestoneStatus.INITIATED
    db_session.commit()

    assert total_settled(db_session, order.id) == Decimal("0")

    mark_paid(db_session, advance)
    db_session.commit()

    assert total_settled(db_session, order.id) == advance.amount
