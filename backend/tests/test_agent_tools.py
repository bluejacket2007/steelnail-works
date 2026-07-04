"""The four callable tools handed to the negotiation agent.

Exercised directly (not through the Anthropic tool-calling loop, which needs
a live API key) — this is the layer where the margin floor is actually
enforced, so it's the layer that matters most to test.
"""
import json
from decimal import Decimal

from app.agent.tools import (
    calculate_tiered_price,
    check_warehouse_stock,
    escalate_to_human_sales,
    evaluate_custom_discount,
)
from tests.conftest import make_organization, make_product


def test_check_warehouse_stock_sufficient(db_session):
    make_product(db_session, sku="NAIL-STOCK-1", stock_tons="50")
    result = check_warehouse_stock("NAIL-STOCK-1", 10.0)
    assert result["sufficient"] is True
    assert result["available_tons"] == 50.0
    assert result["warehouses"][0]["warehouse"] == "WH-N1"


def test_check_warehouse_stock_insufficient(db_session):
    make_product(db_session, sku="NAIL-STOCK-2", stock_tons="5")
    result = check_warehouse_stock("NAIL-STOCK-2", 10.0)
    assert result["sufficient"] is False


def test_check_warehouse_stock_unknown_sku():
    result = check_warehouse_stock("NAIL-DOES-NOT-EXIST", 10.0)
    assert "error" in result


def test_calculate_tiered_price_picks_matching_tier(db_session):
    # All three tiers stay comfortably above the ~90.91 Bright-finish floor —
    # this test is about tier selection, not the margin guardrail.
    make_product(
        db_session,
        sku="NAIL-TIER-1",
        tiers=[("1", "5", "100.00"), ("5", "20", "97.00"), ("20", None, "94.00")],
    )
    low_volume = calculate_tiered_price(sku="NAIL-TIER-1", volume_tons=3.0)
    assert low_volume["price_per_kg"] == 100.00

    mid_volume = calculate_tiered_price(sku="NAIL-TIER-1", volume_tons=10.0)
    assert mid_volume["price_per_kg"] == 97.00

    high_volume = calculate_tiered_price(sku="NAIL-TIER-1", volume_tons=25.0)
    assert high_volume["price_per_kg"] == 94.00


def test_calculate_tiered_price_below_moq_returns_error(db_session):
    make_product(db_session, sku="NAIL-TIER-2", tiers=[("1", "5", "95.00")])
    result = calculate_tiered_price(sku="NAIL-TIER-2", volume_tons=0.1)
    assert "error" in result


def test_calculate_tiered_price_blocked_when_tier_is_below_margin_floor(db_session):
    # Deliberately mispriced tier: 5.00/kg is nowhere near the ~90.91 floor
    # for a Bright-finish product at the configured wire-rod cost.
    make_product(db_session, sku="NAIL-TIER-3", tiers=[("1", None, "5.00")])
    result = calculate_tiered_price(sku="NAIL-TIER-3", volume_tons=2.0)
    assert result["allowed"] is False
    assert result["reason"] == "margin_floor_violation"


def test_evaluate_custom_discount_approved_within_cap(db_session):
    make_product(db_session, sku="NAIL-DISC-1", tiers=[("1", None, "150.00")])
    org = make_organization(db_session, legal_name="AAA Rated Co", credit_rating="AAA")
    # AAA cap is 10%; 150 * 0.95 = 142.50, comfortably above the ~90.91 floor.
    result = evaluate_custom_discount(
        client_id=org.id, requested_discount=0.05, sku="NAIL-DISC-1", volume_tons=10.0
    )
    assert result["allowed"] is True
    assert result["approved_price_per_kg"] == 142.50


def test_evaluate_custom_discount_denied_beyond_credit_cap(db_session):
    make_product(db_session, sku="NAIL-DISC-2", tiers=[("1", None, "150.00")])
    org = make_organization(db_session, legal_name="Unrated Co", credit_rating="UNRATED")
    # UNRATED cap is 0% — any discount request should be denied.
    result = evaluate_custom_discount(
        client_id=org.id, requested_discount=0.05, sku="NAIL-DISC-2", volume_tons=10.0
    )
    assert result["allowed"] is False
    assert "credit-based cap" in result["reason"]


def test_evaluate_custom_discount_denied_when_it_would_breach_margin_floor(db_session):
    # Price 100/kg with AAA's 10% cap discount = 90.00, which is just under
    # the ~90.91 floor for a Bright-finish product — must be denied even
    # though 10% is within the credit-rating cap.
    make_product(db_session, sku="NAIL-DISC-3", tiers=[("1", None, "100.00")])
    org = make_organization(db_session, legal_name="AAA Rated Co 2", credit_rating="AAA")
    result = evaluate_custom_discount(
        client_id=org.id, requested_discount=0.10, sku="NAIL-DISC-3", volume_tons=10.0
    )
    assert result["allowed"] is False
    assert "margin floor" in result["reason"]


def test_evaluate_custom_discount_unknown_client(db_session):
    make_product(db_session, sku="NAIL-DISC-4", tiers=[("1", None, "150.00")])
    result = evaluate_custom_discount(
        client_id="not-a-real-org-id", requested_discount=0.05, sku="NAIL-DISC-4", volume_tons=10.0
    )
    assert result["allowed"] is False
    assert "Unknown client" in result["reason"]


def test_escalate_to_human_sales_queues_and_publishes(fake_redis):
    ticket = escalate_to_human_sales(
        chat_history=["buyer: I need 40 tons at 60/kg", "agent: that breaks the margin floor"],
        reason="Buyer demands a sub-floor price and refuses to negotiate further.",
    )
    assert ticket.startswith("ESC-")

    queued_raw = fake_redis.lrange("crm:escalations", 0, -1)
    assert len(queued_raw) == 1
    queued = json.loads(queued_raw[0])
    assert queued["ticket_id"] == ticket
    assert queued["priority"] == "URGENT"
    assert "sub-floor price" in queued["reason"]
