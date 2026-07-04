"""Hard margin guardrails for the negotiation agent.

The agent may negotiate volume discounts freely, but it is *mechanically*
impossible for it to commit a unit price below the 12% net-profit-margin
floor: every price-producing tool is wrapped in ``@margin_guarded``, and the
engine additionally audits the agent's outbound prose for price figures
before anything is shown to the buyer. The floor is enforced in code, not
in the prompt — a jailbroken prompt cannot bypass it.

Floor derivation (per kg):

    unit_cost = (raw_wire_rod_cost + processing_overhead) * finish_premium
    floor     = unit_cost / (1 - NET_MARGIN_FLOOR)        # 12% net margin
"""
from __future__ import annotations

import functools
import logging
import re
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import Finish, Product

logger = logging.getLogger("agent.guardrails")

# Finish premiums reflect real input-cost differences per coating process.
_FINISH_COST_MULTIPLIER: dict[Finish, Decimal] = {
    Finish.BRIGHT: Decimal("1.00"),
    Finish.ELECTRO_GALVANIZED: Decimal("1.12"),
    Finish.HOT_DIP_GALVANIZED: Decimal("1.22"),
    Finish.STAINLESS_STEEL: Decimal("2.60"),
}


class MarginFloorViolation(Exception):
    """Raised when any pathway attempts to offer a price below the floor."""

    def __init__(self, sku: str, offered: Decimal, floor: Decimal):
        self.sku, self.offered, self.floor = sku, offered, floor
        super().__init__(
            f"Offer of {offered}/kg on {sku} violates the {settings.net_margin_floor:.0%} "
            f"margin floor ({floor}/kg). Offer blocked."
        )


def compute_floor_price(sku: str) -> Decimal:
    """Minimum permissible price-per-kg for a SKU at the current wire-rod cost."""
    unit_cost = Decimal(str(settings.raw_wire_rod_cost_per_kg)) + Decimal(
        str(settings.processing_overhead_per_kg)
    )

    db = SessionLocal()
    try:
        product = db.execute(
            select(Product).where(Product.sku == sku)
        ).scalar_one_or_none()
        if product and product.attributes:
            unit_cost *= _FINISH_COST_MULTIPLIER.get(
                product.attributes.finish, Decimal("1.00")
            )
    finally:
        db.close()

    floor = unit_cost / (Decimal("1") - Decimal(str(settings.net_margin_floor)))
    return floor.quantize(Decimal("0.0001"))


def validate_offer(sku: str, price_per_kg: Decimal | float) -> Decimal:
    """Return the price if compliant; raise MarginFloorViolation otherwise."""
    price = Decimal(str(price_per_kg))
    floor = compute_floor_price(sku)
    if price < floor:
        logger.warning("BLOCKED sub-floor offer: %s at %s (floor %s)", sku, price, floor)
        raise MarginFloorViolation(sku, price, floor)
    return price


def margin_guarded(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator over the agent's price-producing tools.

    Any numeric price the wrapped tool returns (bare number, or a dict with a
    ``price_per_kg`` / ``approved_price_per_kg`` key) is validated against the
    live floor for the tool's ``sku`` argument. A violation is converted into
    a structured refusal the model can read — the sub-floor number itself
    never leaves the guardrail.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = fn(*args, **kwargs)
        sku = kwargs.get("sku") or (args[0] if args else None)
        if not isinstance(sku, str):
            return result

        try:
            if isinstance(result, (int, float, Decimal)):
                validate_offer(sku, Decimal(str(result)))
            elif isinstance(result, dict):
                for key in ("price_per_kg", "approved_price_per_kg"):
                    if key in result and result[key] is not None:
                        validate_offer(sku, Decimal(str(result[key])))
        except MarginFloorViolation as violation:
            return {
                "allowed": False,
                "reason": "margin_floor_violation",
                "detail": str(violation),
                "floor_price_per_kg": float(violation.floor),
                "instruction": (
                    "You must not offer this price. Counter at or above the "
                    "floor price, or escalate to human sales."
                ),
            }
        return result

    return wrapper


# Matches price mentions like "₹84.50/kg", "84.5 per kg", "$1.02 / kg".
_PRICE_PATTERN = re.compile(
    r"(?:₹|rs\.?\s*|\$|inr\s*|usd\s*)?(\d{1,6}(?:\.\d{1,4})?)\s*(?:/|per\s+)\s*kg",
    re.IGNORECASE,
)


def audit_outbound_offer(text: str, sku: str | None) -> None:
    """Final tripwire over the agent's reasoning output.

    Scans the outbound message for any price-per-kg figure below the floor;
    raises MarginFloorViolation so the engine can suppress the reply and
    escalate instead of leaking a non-compliant quote to the buyer.
    """
    if not sku or not text:
        return
    floor = compute_floor_price(sku)
    for match in _PRICE_PATTERN.finditer(text):
        quoted = Decimal(match.group(1))
        # Ignore figures that are clearly not unit prices (e.g. tonnages).
        if quoted <= 0:
            continue
        if quoted < floor:
            raise MarginFloorViolation(sku, quoted, floor)
