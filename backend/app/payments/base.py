"""Unified payment-provider interface.

Both Stripe and Razorpay are wrapped behind the same three-method contract,
so milestone logic and webhook plumbing stay provider-agnostic. Signature
verification is implemented locally with HMAC-SHA256 + constant-time compare,
so it works (and is auditable) without the vendor SDKs installed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


class PaymentError(Exception):
    pass


class SignatureVerificationError(PaymentError):
    pass


@dataclass
class PaymentIntent:
    provider: str
    provider_payment_id: str
    client_secret: str | None       # Stripe client_secret / Razorpay order id
    amount: Decimal
    currency: str
    raw: dict[str, Any]


@dataclass
class WebhookEventData:
    provider: str
    event_id: str
    event_type: str
    provider_payment_id: str | None
    succeeded: bool
    raw: dict[str, Any]


class PaymentProviderBase(ABC):
    name: str

    @abstractmethod
    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        metadata: dict[str, str],
    ) -> PaymentIntent:
        """Create a charge/order at the provider. Must forward the idempotency
        key so retries can never double-capture at the provider either."""

    @abstractmethod
    def verify_and_parse_webhook(
        self, raw_body: bytes, headers: dict[str, str]
    ) -> WebhookEventData:
        """Validate the cryptographic signature and normalize the event.
        Raises SignatureVerificationError on any mismatch."""
