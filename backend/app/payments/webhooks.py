"""Webhook ledger system.

Listener endpoints for Stripe and Razorpay:

1. Read the *raw* body (the XSS sanitizer explicitly exempts these routes so
   the bytes are untouched) and verify the provider's HMAC signature —
   an invalid signature is rejected with 400 before anything is stored.
2. Persist the event with a provider-unique ID: redeliveries dedupe to a
   no-op, so a provider retry storm can never double-settle a milestone.
3. Return 200 immediately; the actual side effects (milestone transition,
   hash-chained ledger entry, proforma invoice PDF) run asynchronously in a
   background worker task.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.models import (
    OrderMilestone,
    PaymentProvider,
    WebhookEvent,
)
from app.payments import milestones as milestone_sm
from app.payments.base import SignatureVerificationError, WebhookEventData
from app.payments.invoices import generate_proforma_invoice
from app.payments.razorpay_provider import get_provider

logger = logging.getLogger("payments.webhooks")

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(request: Request, background: BackgroundTasks):
    return await _handle(request, background, provider_name="stripe")


@router.post("/razorpay")
async def razorpay_webhook(request: Request, background: BackgroundTasks):
    return await _handle(request, background, provider_name="razorpay")


async def _handle(request: Request, background: BackgroundTasks, provider_name: str):
    raw_body = await request.body()
    provider = get_provider(provider_name)

    try:
        event = provider.verify_and_parse_webhook(
            raw_body, {k.lower(): v for k, v in request.headers.items()}
        )
    except SignatureVerificationError as exc:
        logger.warning("Rejected %s webhook: %s", provider_name, exc)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(status_code=400, detail="Malformed webhook payload")

    # Dedupe: the (provider, event_id) unique constraint makes redelivery a no-op.
    db = SessionLocal()
    try:
        record = WebhookEvent(
            provider=PaymentProvider(provider_name),
            provider_event_id=event.event_id,
            event_type=event.event_type,
            payload=raw_body.decode("utf-8", errors="replace"),
            signature_valid=True,
        )
        db.add(record)
        db.commit()
        record_id = record.id
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate_ignored"}
    finally:
        db.close()

    background.add_task(_process_event, record_id, event)
    return {"status": "accepted"}


def _process_event(record_id: str, event: WebhookEventData) -> None:
    """Background worker: settle the milestone and write the ledger + invoice."""
    db = SessionLocal()
    try:
        record = db.get(WebhookEvent, record_id)

        milestone = None
        if event.provider_payment_id:
            milestone = db.execute(
                select(OrderMilestone).where(
                    OrderMilestone.provider_payment_id == event.provider_payment_id
                )
            ).scalar_one_or_none()

        if milestone is None:
            record.processed = True
            record.error = "No milestone matches this provider payment reference."
            db.commit()
            return

        if event.succeeded:
            milestone_sm.mark_paid(db, milestone)
            db.flush()
            try:
                invoice_path = generate_proforma_invoice(milestone.order, milestone)
                logger.info("Proforma invoice generated: %s", invoice_path)
            except Exception as exc:  # invoice rendering must not lose the payment
                logger.exception("Invoice generation failed: %s", exc)
        elif event.event_type in (
            "payment_intent.payment_failed",
            "payment.failed",
        ):
            milestone_sm.mark_failed(db, milestone, reason=event.event_type)

        record.processed = True
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Webhook processing failed for %s", record_id)
        try:
            record = db.get(WebhookEvent, record_id)
            record.error = str(exc)[:2000]
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
