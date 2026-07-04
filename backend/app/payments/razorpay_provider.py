"""Razorpay wrapper: Orders API + webhook signature validation.

Webhook scheme (https://razorpay.com/docs/webhooks/validate-test):
  X-Razorpay-Signature = HMAC-SHA256(webhook_secret, raw_body)
"""
from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

from app.core.config import settings
from app.payments.base import (
    PaymentError,
    PaymentIntent,
    PaymentProviderBase,
    SignatureVerificationError,
    WebhookEventData,
)


class RazorpayProvider(PaymentProviderBase):
    name = "razorpay"

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        metadata: dict[str, str],
    ) -> PaymentIntent:
        try:
            import razorpay
            import razorpay.errors
        except ImportError as exc:
            raise PaymentError("razorpay SDK is not installed") from exc
        import requests.exceptions

        client = razorpay.Client(
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
        )
        try:
            # Razorpay dedupes on receipt — reuse the idempotency key as receipt id.
            order = client.order.create(
                {
                    "amount": int(amount * 100),  # paise
                    "currency": currency.upper(),
                    "receipt": idempotency_key[:40],
                    "notes": metadata,
                }
            )
        except (
            razorpay.errors.BadRequestError,
            razorpay.errors.ServerError,
            razorpay.errors.GatewayError,
            requests.exceptions.RequestException,
        ) as exc:
            # Surface as our own PaymentError so the API layer returns a
            # clean 502 instead of an unhandled 500 — misconfigured or
            # temporarily-unreachable Razorpay must not crash the request.
            raise PaymentError(f"Razorpay order creation failed: {exc}") from exc
        return PaymentIntent(
            provider=self.name,
            provider_payment_id=order["id"],
            client_secret=order["id"],
            amount=amount,
            currency=currency,
            raw=dict(order),
        )

    def verify_and_parse_webhook(
        self, raw_body: bytes, headers: dict[str, str]
    ) -> WebhookEventData:
        signature = headers.get("x-razorpay-signature", "")
        if not signature:
            raise SignatureVerificationError("Missing X-Razorpay-Signature header")

        expected = hmac.new(
            settings.razorpay_webhook_secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise SignatureVerificationError("Razorpay signature mismatch")

        event = json.loads(raw_body)
        event_type = event.get("event", "")
        payment_entity = (
            event.get("payload", {}).get("payment", {}).get("entity", {})
        )
        return WebhookEventData(
            provider=self.name,
            event_id=headers.get("x-razorpay-event-id", "")
            or f"{event_type}:{payment_entity.get('id', '')}",
            event_type=event_type,
            provider_payment_id=payment_entity.get("order_id")
            or payment_entity.get("id"),
            succeeded=event_type in ("payment.captured", "order.paid"),
            raw=event,
        )


PROVIDERS: dict[str, PaymentProviderBase] = {}


def get_provider(name: str) -> PaymentProviderBase:
    """Registry accessor shared by the payments API and webhook listeners."""
    if not PROVIDERS:
        from app.payments.stripe_provider import StripeProvider

        PROVIDERS["stripe"] = StripeProvider()
        PROVIDERS["razorpay"] = RazorpayProvider()
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise PaymentError(f"Unknown payment provider: {name}") from exc
