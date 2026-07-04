"""The 12% net-margin floor: the one rule the negotiation agent may never
break, enforced in code rather than in a prompt.
"""
from decimal import Decimal

import pytest

from app.agent.guardrails import (
    MarginFloorViolation,
    audit_outbound_offer,
    compute_floor_price,
    margin_guarded,
    validate_offer,
)
from tests.conftest import make_product


def test_floor_price_for_bright_finish(db_session):
    # unit_cost = (62 + 18) * 1.00 = 80; floor = 80 / (1 - 0.12) = 90.9090...
    make_product(db_session, sku="NAIL-BRT-TEST", finish="Bright")
    floor = compute_floor_price("NAIL-BRT-TEST")
    assert floor == Decimal("90.9091")


def test_floor_price_scales_with_finish_premium(db_session):
    # Stainless Steel premium is 2.60x: unit_cost = 80 * 2.60 = 208
    # floor = 208 / 0.88 = 236.3636...
    make_product(db_session, sku="NAIL-SS-TEST", finish="Stainless Steel")
    floor = compute_floor_price("NAIL-SS-TEST")
    assert floor == Decimal("236.3636")


def test_floor_price_falls_back_to_no_premium_for_unknown_sku():
    # Product doesn't exist: no finish multiplier applied, so floor is the
    # bare unit_cost / (1 - margin) with no attributes lookup.
    floor = compute_floor_price("NAIL-DOES-NOT-EXIST")
    assert floor == Decimal("90.9091")


def test_validate_offer_accepts_at_or_above_floor(db_session):
    make_product(db_session, sku="NAIL-VALIDATE-1", finish="Bright")
    assert validate_offer("NAIL-VALIDATE-1", Decimal("95.00")) == Decimal("95.00")


def test_validate_offer_rejects_below_floor(db_session):
    make_product(db_session, sku="NAIL-VALIDATE-2", finish="Bright")
    with pytest.raises(MarginFloorViolation):
        validate_offer("NAIL-VALIDATE-2", Decimal("10.00"))


def test_margin_guarded_blocks_bare_number_return(db_session):
    make_product(db_session, sku="NAIL-GUARD-1", finish="Bright")

    @margin_guarded
    def fake_tool(sku: str) -> float:
        return 5.0  # far below the ~90.91 floor

    result = fake_tool(sku="NAIL-GUARD-1")
    assert isinstance(result, dict)
    assert result["allowed"] is False
    assert result["reason"] == "margin_floor_violation"


def test_margin_guarded_blocks_dict_price_field(db_session):
    make_product(db_session, sku="NAIL-GUARD-2", finish="Bright")

    @margin_guarded
    def fake_tool(sku: str) -> dict:
        return {"price_per_kg": 1.0, "sku": sku}

    result = fake_tool(sku="NAIL-GUARD-2")
    assert result["allowed"] is False


def test_margin_guarded_passes_through_compliant_price(db_session):
    make_product(db_session, sku="NAIL-GUARD-3", finish="Bright")

    @margin_guarded
    def fake_tool(sku: str) -> dict:
        return {"price_per_kg": 120.0, "sku": sku}

    result = fake_tool(sku="NAIL-GUARD-3")
    assert result == {"price_per_kg": 120.0, "sku": "NAIL-GUARD-3"}


def test_audit_outbound_offer_catches_sub_floor_price_in_prose(db_session):
    make_product(db_session, sku="NAIL-AUDIT-1", finish="Bright")
    with pytest.raises(MarginFloorViolation):
        audit_outbound_offer("Sure, I can do ₹10.00/kg for that volume.", "NAIL-AUDIT-1")


def test_audit_outbound_offer_allows_compliant_prose(db_session):
    make_product(db_session, sku="NAIL-AUDIT-2", finish="Bright")
    # Should not raise.
    audit_outbound_offer("I can offer ₹95.00/kg for 10 tons.", "NAIL-AUDIT-2")


def test_audit_outbound_offer_ignores_text_with_no_sku_context():
    # No SKU context (e.g. general chit-chat) — nothing to audit against.
    audit_outbound_offer("Our factory ships nationwide.", None)
