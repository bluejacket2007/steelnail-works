"""Callable tools exposed to the negotiation agent.

Each tool is a plain Python function plus an Anthropic tool schema. Price-
producing tools are wrapped in @margin_guarded, so the 12% net-margin floor
is enforced at the execution layer regardless of what the model asks for.
"""
from __future__ import annotations

import json
import time
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.agent.guardrails import compute_floor_price, margin_guarded
from app.core.database import SessionLocal
from app.core.redis_client import get_sync_redis
from app.models.models import (
    BulkPricingTier,
    CreditRating,
    Organization,
    Product,
    WarehouseStock,
)

# Better credit → more discount headroom, but never through the margin floor.
_CREDIT_DISCOUNT_CAP: dict[CreditRating, Decimal] = {
    CreditRating.AAA: Decimal("0.10"),
    CreditRating.AA: Decimal("0.08"),
    CreditRating.A: Decimal("0.06"),
    CreditRating.BBB: Decimal("0.04"),
    CreditRating.BB: Decimal("0.02"),
    CreditRating.B: Decimal("0.01"),
    CreditRating.UNRATED: Decimal("0.00"),
}


def check_warehouse_stock(sku: str, quantity_tons: float) -> dict[str, Any]:
    """Live inventory check across all warehouses for a SKU."""
    db = SessionLocal()
    try:
        product = db.execute(select(Product).where(Product.sku == sku)).scalar_one_or_none()
        if product is None:
            return {"error": f"Unknown SKU: {sku}"}

        rows = db.execute(
            select(WarehouseStock).where(WarehouseStock.product_id == product.id)
        ).scalars().all()
        available = sum((r.quantity_tons for r in rows), Decimal("0"))
        return {
            "sku": sku,
            "requested_tons": quantity_tons,
            "available_tons": float(available),
            "sufficient": float(available) >= quantity_tons,
            "warehouses": [
                {"warehouse": r.warehouse_code, "tons": float(r.quantity_tons)}
                for r in rows
            ],
        }
    finally:
        db.close()


@margin_guarded
def calculate_tiered_price(sku: str, volume_tons: float) -> dict[str, Any]:
    """Base price-per-kg from the MOQ tier matrix for the requested volume."""
    db = SessionLocal()
    try:
        product = db.execute(select(Product).where(Product.sku == sku)).scalar_one_or_none()
        if product is None:
            return {"error": f"Unknown SKU: {sku}"}

        volume = Decimal(str(volume_tons))
        tier = db.execute(
            select(BulkPricingTier)
            .where(
                BulkPricingTier.product_id == product.id,
                BulkPricingTier.moq_min_tons <= volume,
                (BulkPricingTier.moq_max_tons.is_(None))
                | (BulkPricingTier.moq_max_tons > volume),
            )
            .order_by(BulkPricingTier.moq_min_tons.desc())
            .limit(1)
        ).scalar_one_or_none()

        if tier is None:
            return {
                "error": f"No pricing tier covers {volume_tons} tons for {sku}. "
                "The volume may be below the minimum order quantity."
            }

        return {
            "sku": sku,
            "volume_tons": volume_tons,
            "price_per_kg": float(tier.price_per_kg),
            "currency": tier.currency,
            "tier": {
                "min_tons": float(tier.moq_min_tons),
                "max_tons": float(tier.moq_max_tons) if tier.moq_max_tons else None,
            },
        }
    finally:
        db.close()


@margin_guarded
def evaluate_custom_discount(
    client_id: str, requested_discount: float, sku: str, volume_tons: float
) -> dict[str, Any]:
    """Judge a requested discount against client credit history + margin floor.

    Approval requires BOTH:
      1. discount ≤ the client's credit-rating discount cap, and
      2. the resulting price ≥ the 12% net-margin floor (enforced again by
         the @margin_guarded wrapper on the returned price).
    """
    db = SessionLocal()
    try:
        org = db.get(Organization, client_id)
        if org is None:
            return {"allowed": False, "reason": f"Unknown client: {client_id}"}

        base = calculate_tiered_price(sku=sku, volume_tons=volume_tons)
        if "error" in base or base.get("allowed") is False:
            return {"allowed": False, "reason": base.get("error") or base.get("detail")}

        discount = Decimal(str(requested_discount))
        cap = _CREDIT_DISCOUNT_CAP[org.credit_rating]
        discounted_price = (
            Decimal(str(base["price_per_kg"])) * (Decimal("1") - discount)
        ).quantize(Decimal("0.0001"))
        floor = compute_floor_price(sku)

        allowed = discount <= cap and discounted_price >= floor
        result: dict[str, Any] = {
            "allowed": bool(allowed),
            "client_credit_rating": org.credit_rating.value,
            "credit_discount_cap": float(cap),
            "requested_discount": requested_discount,
            "floor_price_per_kg": float(floor),
        }
        if allowed:
            result["approved_price_per_kg"] = float(discounted_price)
        else:
            result["reason"] = (
                "Requested discount exceeds the client's credit-based cap."
                if discount > cap
                else "Requested discount would breach the 12% net-margin floor."
            )
            result["max_permissible_price_discount"] = float(
                min(cap, (Decimal(str(base["price_per_kg"])) - floor)
                    / Decimal(str(base["price_per_kg"])))
            )
        return result
    finally:
        db.close()


def escalate_to_human_sales(chat_history: list, reason: str) -> str:
    """Flash an urgent CRM notification and return the escalation ticket id."""
    ticket_id = f"ESC-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"
    payload = json.dumps(
        {
            "ticket_id": ticket_id,
            "reason": reason,
            "chat_history": chat_history[-20:],  # recent context only
            "created_at": time.time(),
            "priority": "URGENT",
        }
    )
    redis = get_sync_redis()
    redis.lpush("crm:escalations", payload)          # work queue for the dashboard
    redis.publish("crm:escalations:live", payload)   # real-time flash
    return ticket_id


# ── Anthropic tool schemas ────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "check_warehouse_stock",
        "description": (
            "Check live warehouse inventory for a steel nail SKU. Call this "
            "before promising any delivery volume or timeline — never assume "
            "stock exists."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {"type": "string", "description": "Product SKU, e.g. NAIL-HDG-63-11"},
                "quantity_tons": {"type": "number", "description": "Volume the buyer needs, in metric tons"},
            },
            "required": ["sku", "quantity_tons"],
        },
    },
    {
        "name": "calculate_tiered_price",
        "description": (
            "Fetch the official base price-per-kg for a SKU at a given order "
            "volume from the bulk pricing tier matrix. Call this before "
            "quoting any number — never invent a price."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "volume_tons": {"type": "number", "description": "Order volume in metric tons"},
            },
            "required": ["sku", "volume_tons"],
        },
    },
    {
        "name": "evaluate_custom_discount",
        "description": (
            "Evaluate whether a specific discount can be approved for a client, "
            "based on their credit history and the non-negotiable margin floor. "
            "Call this whenever the buyer pushes below the tier price. Only an "
            "'allowed: true' result authorizes you to offer the discounted price."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "Buyer organization id"},
                "requested_discount": {
                    "type": "number",
                    "description": "Fractional discount off the tier price, e.g. 0.05 for 5%",
                },
                "sku": {"type": "string"},
                "volume_tons": {"type": "number"},
            },
            "required": ["client_id", "requested_discount", "sku", "volume_tons"],
        },
    },
    {
        "name": "escalate_to_human_sales",
        "description": (
            "Escalate the negotiation to a human sales manager. Call this when "
            "the buyer demands terms below the margin floor, requests contract "
            "changes you cannot authorize, the negotiation is deadlocked, or "
            "the buyer explicitly asks for a human."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "chat_history": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recent conversation turns, oldest first",
                },
                "reason": {"type": "string", "description": "Why this needs a human"},
            },
            "required": ["chat_history", "reason"],
        },
    },
]

TOOL_IMPLEMENTATIONS = {
    "check_warehouse_stock": check_warehouse_stock,
    "calculate_tiered_price": calculate_tiered_price,
    "evaluate_custom_discount": evaluate_custom_discount,
    "escalate_to_human_sales": escalate_to_human_sales,
}
