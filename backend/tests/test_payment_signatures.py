"""Webhook signature verification — the boundary that decides whether an
inbound "payment succeeded" event is trusted enough to settle a milestone.
"""
import hashlib
import hmac
import json
import time

import pytest

from app.core.config import settings
from app.payments.base import SignatureVerificationError
from app.payments.razorpay_provider import RazorpayProvider
from app.payments.stripe_provider import StripeProvider


def _stripe_signed_headers(raw_body: bytes, *, timestamp: int | None = None) -> dict[str, str]:
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.".encode() + raw_body
    sig = hmac.new(settings.stripe_webhook_secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={ts},v1={sig}"}


def test_stripe_webhook_accepts_valid_signature():
    body = json.dumps(
        {"id": "evt_1", "type": "payment_intent.succeeded", "data": {"object": {"id": "pi_1"}}}
    ).encode()
    headers = _stripe_signed_headers(body)
    event = StripeProvider().verify_and_parse_webhook(body, headers)
    assert event.succeeded is True
    assert event.provider_payment_id == "pi_1"
    assert event.event_id == "evt_1"


def test_stripe_webhook_rejects_tampered_body():
    body = json.dumps({"id": "evt_1", "type": "payment_intent.succeeded", "data": {"object": {}}}).encode()
    headers = _stripe_signed_headers(body)
    tampered_body = json.dumps(
        {"id": "evt_1", "type": "payment_intent.succeeded", "data": {"object": {"amount": 999999}}}
    ).encode()
    with pytest.raises(SignatureVerificationError, match="signature mismatch"):
        StripeProvider().verify_and_parse_webhook(tampered_body, headers)


def test_stripe_webhook_rejects_expired_timestamp():
    body = json.dumps({"id": "evt_1", "type": "payment_intent.succeeded", "data": {"object": {}}}).encode()
    stale_timestamp = int(time.time()) - 999  # beyond the 300s tolerance
    headers = _stripe_signed_headers(body, timestamp=stale_timestamp)
    with pytest.raises(SignatureVerificationError, match="tolerance"):
        StripeProvider().verify_and_parse_webhook(body, headers)


def test_stripe_webhook_rejects_malformed_header():
    body = b"{}"
    with pytest.raises(SignatureVerificationError, match="Malformed"):
        StripeProvider().verify_and_parse_webhook(body, {"stripe-signature": "garbage"})


def _razorpay_signed_headers(raw_body: bytes) -> dict[str, str]:
    sig = hmac.new(settings.razorpay_webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return {"x-razorpay-signature": sig}


def test_razorpay_webhook_accepts_valid_signature():
    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_1", "order_id": "order_1"}}},
        }
    ).encode()
    headers = _razorpay_signed_headers(body)
    event = RazorpayProvider().verify_and_parse_webhook(body, headers)
    assert event.succeeded is True
    assert event.provider_payment_id == "order_1"


def test_razorpay_webhook_rejects_tampered_body():
    body = json.dumps({"event": "payment.captured", "payload": {}}).encode()
    headers = _razorpay_signed_headers(body)
    tampered_body = json.dumps({"event": "payment.failed", "payload": {}}).encode()
    with pytest.raises(SignatureVerificationError, match="signature mismatch"):
        RazorpayProvider().verify_and_parse_webhook(tampered_body, headers)


def test_razorpay_webhook_rejects_missing_signature():
    with pytest.raises(SignatureVerificationError, match="Missing"):
        RazorpayProvider().verify_and_parse_webhook(b"{}", {})


def test_razorpay_webhook_non_payment_event_is_not_succeeded():
    body = json.dumps({"event": "order.created", "payload": {}}).encode()
    headers = _razorpay_signed_headers(body)
    event = RazorpayProvider().verify_and_parse_webhook(body, headers)
    assert event.succeeded is False
