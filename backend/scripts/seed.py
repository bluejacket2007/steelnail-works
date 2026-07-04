"""Seed the catalog with representative steel-nail SKUs, pricing tiers,
warehouse stock, and a demo SalesManager account.

Run from backend/:  python -m scripts.seed
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.models import (
    BulkPricingTier,
    Finish,
    HeadStyle,
    Product,
    ProductAttribute,
    Role,
    ShankType,
    User,
    WarehouseStock,
)

CATALOG = [
    # (sku, name, length_mm, length_in, awg, gauge_mm, head, shank, finish, base ₹/kg)
    ("NAIL-BRT-50-12", '2" Bright Common Nail', "50", "2.0", 12, "2.77", HeadStyle.FLAT, ShankType.SMOOTH, Finish.BRIGHT, "92"),
    ("NAIL-BRT-63-11", '2.5" Bright Common Nail', "63", "2.5", 11, "3.05", HeadStyle.FLAT, ShankType.SMOOTH, Finish.BRIGHT, "91"),
    ("NAIL-EG-63-11", '2.5" Electro-Galvanized Nail', "63", "2.5", 11, "3.05", HeadStyle.CHECKERED, ShankType.SMOOTH, Finish.ELECTRO_GALVANIZED, "103"),
    ("NAIL-HDG-75-10", '3" Hot-Dip Galvanized Ring Shank', "75", "3.0", 10, "3.40", HeadStyle.FLAT, ShankType.RING, Finish.HOT_DIP_GALVANIZED, "118"),
    ("NAIL-SS-63-11", '2.5" Stainless Steel Screw Shank', "63", "2.5", 11, "3.05", HeadStyle.COUNTERSUNK, ShankType.SCREW, Finish.STAINLESS_STEEL, "245"),
]

# (min_tons, max_tons_or_None, discount vs base)
TIER_SHAPE = [
    (Decimal("1"), Decimal("5"), Decimal("1.00")),
    (Decimal("5"), Decimal("20"), Decimal("0.965")),
    (Decimal("20"), None, Decimal("0.93")),
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for sku, name, l_mm, l_in, awg, g_mm, head, shank, finish, base in CATALOG:
            if db.execute(select(Product).where(Product.sku == sku)).scalar_one_or_none():
                continue
            product = Product(sku=sku, name=name, description=f"{name} — bulk industrial supply")
            db.add(product)
            db.flush()
            db.add(
                ProductAttribute(
                    product_id=product.id,
                    length_mm=Decimal(l_mm),
                    length_inches=Decimal(l_in),
                    wire_gauge_awg=awg,
                    wire_gauge_mm=Decimal(g_mm),
                    head_style=head,
                    shank_type=shank,
                    finish=finish,
                )
            )
            for min_t, max_t, factor in TIER_SHAPE:
                db.add(
                    BulkPricingTier(
                        product_id=product.id,
                        moq_min_tons=min_t,
                        moq_max_tons=max_t,
                        price_per_kg=(Decimal(base) * factor).quantize(Decimal("0.0001")),
                        currency="INR",
                    )
                )
            for wh, tons in (("WH-NORTH", "40"), ("WH-WEST", "25")):
                db.add(
                    WarehouseStock(
                        product_id=product.id,
                        warehouse_code=wh,
                        quantity_tons=Decimal(tons),
                    )
                )

        # This account's password is printed in this file and in the project's
        # own docs — never create it where ENFORCE_HTTPS=true signals a real
        # deployment. Provision real staff accounts through the API instead.
        if settings.enforce_https:
            print(
                "ENFORCE_HTTPS is true (production-like environment) — skipping "
                "the demo SalesManager account with its publicly documented "
                "password. Create real staff accounts through the API."
            )
        elif not db.execute(
            select(User).where(User.email == "manager@nailfactory.example")
        ).scalar_one_or_none():
            db.add(
                User(
                    email="manager@nailfactory.example",
                    hashed_password=hash_password("ChangeMe!Manager1"),
                    full_name="Demo Sales Manager",
                    role=Role.SALES_MANAGER,
                )
            )

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
