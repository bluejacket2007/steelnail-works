"use client";

import { loadStripe, type Stripe } from "@stripe/stripe-js";
import { Elements, PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";
import { useState } from "react";
import { ui } from "@/lib/ui";

let stripePromise: Promise<Stripe | null> | null = null;

function getStripe(): Promise<Stripe | null> {
  const publishableKey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
  if (!publishableKey) return Promise.resolve(null);
  if (!stripePromise) stripePromise = loadStripe(publishableKey);
  return stripePromise;
}

function ConfirmButton({ onSettled }: { onSettled: (message: string, isError: boolean) => void }) {
  const stripe = useStripe();
  const elements = useElements();
  const [submitting, setSubmitting] = useState(false);

  async function onConfirm() {
    if (!stripe || !elements) return;
    setSubmitting(true);
    const { error, paymentIntent } = await stripe.confirmPayment({
      elements,
      redirect: "if_required",
    });
    setSubmitting(false);
    if (error) {
      onSettled(error.message ?? "Payment failed.", true);
      return;
    }
    if (paymentIntent?.status === "succeeded") {
      onSettled("Payment confirmed — the milestone will settle once our webhook receives Stripe's confirmation.", false);
    } else {
      onSettled(`Payment status: ${paymentIntent?.status ?? "processing"}.`, false);
    }
  }

  return (
    <button
      onClick={onConfirm}
      disabled={!stripe || submitting}
      style={{ ...ui.button, marginTop: "0.75rem" }}
    >
      {submitting ? "Confirming…" : "Confirm payment"}
    </button>
  );
}

export function StripePaymentForm({
  clientSecret,
  onSettled,
}: {
  clientSecret: string;
  onSettled: (message: string, isError: boolean) => void;
}) {
  if (!process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY) {
    return (
      <div style={{ ...ui.errorBox, background: "#fef3c7", color: "#92400e" }}>
        Stripe is not configured on this deployment — set{" "}
        <code>NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY</code> to enable card entry.
      </div>
    );
  }

  return (
    <div style={{ marginTop: "0.75rem" }}>
      <Elements stripe={getStripe()} options={{ clientSecret }}>
        <PaymentElement />
        <ConfirmButton onSettled={onSettled} />
      </Elements>
    </div>
  );
}
