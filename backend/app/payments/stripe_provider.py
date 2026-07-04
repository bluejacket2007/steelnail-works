"""Stripe wrapper: PaymentIntents + webhook signature validation.

Webhook scheme (https://stripe.com/docs/webhooks/signatures):
  Stripe-Signature: t=<unix>,v1=<hmac>,...
  signed_payload = f"{t}.{raw_body}"
  v1 = HMAC-SHA256(webhook_secret, signed_payload)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal

from app.core.config import settings
from app.payments.base import (
    PaymentError,
    PaymentIntent,
    PaymentProviderBase,
    SignatureVerificationError,
    WebhookEventData,
)

_TOLERANCE_SECONDS = 300  # reject replayed webhooks older than 5 minutes


class StripeProvider(PaymentProviderBase):
    name = "stripe"

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        metadata: dict[str, str],
    ) -> PaymentIntent:
        try:
            import stripe
        except ImportError as exc:
            raise PaymentError("stripe SDK is not installed") from exc

        stripe.api_key = settings.stripe_secret_key
        try:
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # minor units
                currency=currency.lower(),
                metadata=metadata,
                automatic_payment_methods={"enabled": True},
                idempotency_key=idempotency_key,
            )
        except stripe.error.StripeError as exc:
            # Surface as our own PaymentError so the API layer returns a
            # clean 502 instead of an unhandled 500 — misconfigured or
            # temporarily-unreachable Stripe must not crash the request.
            raise PaymentError(f"Stripe payment intent creation failed: {exc.user_message or exc}") from exc
        return PaymentIntent(
            provider=self.name,
            provider_payment_id=intent["id"],
            client_secret=intent.get("client_secret"),
            amount=amount,
            currency=currency,
            raw=dict(intent),
        )

    def verify_and_parse_webhook(
        self, raw_body: bytes, headers: dict[str, str]
    ) -> WebhookEventData:
        header = headers.get("stripe-signature", "")
        parts = dict(
            item.split("=", 1) for item in header.split(",") if "=" in item
        )
        timestamp = parts.get("t")
        signature = parts.get("v1")
        if not timestamp or not signature:
            raise SignatureVerificationError("Malformed Stripe-Signature header")

        if abs(time.time() - int(timestamp)) > _TOLERANCE_SECONDS:
            raise SignatureVerificationError("Webhook timestamp outside tolerance")

        signed_payload = f"{timestamp}.".encode() + raw_body
        expected = hmac.new(
            settings.stripe_webhook_secret.encode(), signed_payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise SignatureVerificationError("Stripe signature mismatch")

        event = json.loads(raw_body)
        obj = event.get("data", {}).get("object", {})
        event_type = event.get("type", "")
        return WebhookEventData(
            provider=self.name,
            event_id=event.get("id", ""),
            event_type=event_type,
            provider_payment_id=obj.get("id"),
            succeeded=event_type == "payment_intent.succeeded",
            raw=event,
        )
