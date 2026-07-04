"""Faceted B2B catalog search.

Filter combinations hit the composite indexes on product_attributes
(length_mm, wire_gauge_mm, finish) declared in models.py. Read-heavy list
responses are cached in Redis for 60s keyed by the normalized filter set.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.redis_client import get_sync_redis
from app.models.models import Finish, HeadStyle, Product, ProductAttribute, ShankType
from app.schemas.schemas import ProductOut

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

_CACHE_TTL_SECONDS = 60


@router.get("/products", response_model=list[ProductOut])
def search_products(
    db: Session = Depends(get_db),
    min_length_mm: Decimal | None = Query(default=None, gt=0),
    max_length_mm: Decimal | None = Query(default=None, gt=0),
    wire_gauge_mm: Decimal | None = Query(default=None, gt=0),
    wire_gauge_awg: int | None = Query(default=None, gt=0),
    finish: Finish | None = None,
    shank_type: ShankType | None = None,
    head_style: HeadStyle | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    cache_key = "catalog:" + hashlib.sha256(
        json.dumps(
            [
                str(min_length_mm), str(max_length_mm), str(wire_gauge_mm),
                wire_gauge_awg, finish, shank_type, head_style, limit, offset,
            ],
            default=str,
        ).encode()
    ).hexdigest()

    redis = get_sync_redis()
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)

    stmt = (
        select(Product)
        .join(ProductAttribute)
        .options(
            joinedload(Product.attributes),
            joinedload(Product.pricing_tiers),
        )
        .where(Product.is_active.is_(True))
    )
    if min_length_mm is not None:
        stmt = stmt.where(ProductAttribute.length_mm >= min_length_mm)
    if max_length_mm is not None:
        stmt = stmt.where(ProductAttribute.length_mm <= max_length_mm)
    if wire_gauge_mm is not None:
        stmt = stmt.where(ProductAttribute.wire_gauge_mm == wire_gauge_mm)
    if wire_gauge_awg is not None:
        stmt = stmt.where(ProductAttribute.wire_gauge_awg == wire_gauge_awg)
    if finish is not None:
        stmt = stmt.where(ProductAttribute.finish == finish)
    if shank_type is not None:
        stmt = stmt.where(ProductAttribute.shank_type == shank_type)
    if head_style is not None:
        stmt = stmt.where(ProductAttribute.head_style == head_style)

    products = (
        db.execute(stmt.limit(limit).offset(offset)).unique().scalars().all()
    )
    payload = [ProductOut.model_validate(p).model_dump(mode="json") for p in products]
    redis.set(cache_key, json.dumps(payload), ex=_CACHE_TTL_SECONDS)
    return payload


@router.get("/products/{sku}", response_model=ProductOut)
def get_product(sku: str, db: Session = Depends(get_db)):
    product = db.execute(
        select(Product)
        .options(joinedload(Product.attributes), joinedload(Product.pricing_tiers))
        .where(Product.sku == sku, Product.is_active.is_(True))
    ).unique().scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
