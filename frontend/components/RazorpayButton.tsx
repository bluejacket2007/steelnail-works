"use client";

import { useState } from "react";
import { ui } from "@/lib/ui";

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void };
  }
}

const CHECKOUT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

function loadCheckoutScript(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  const existing = document.querySelector(`script[src="${CHECKOUT_SRC}"]`);
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("Failed to load Razorpay checkout")));
    });
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = CHECKOUT_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Razorpay checkout"));
    document.body.appendChild(script);
  });
}

export function RazorpayButton({
  orderId,
  amount,
  currency,
  buyerName,
  buyerEmail,
  onSettled,
}: {
  orderId: string;
  amount: string;
  currency: string;
  buyerName?: string;
  buyerEmail?: string;
  onSettled: (message: string, isError: boolean) => void;
}) {
  const [opening, setOpening] = useState(false);
  const keyId = process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID;

  if (!keyId) {
    return (
      <div style={{ ...ui.errorBox, background: "#fef3c7", color: "#92400e", marginTop: "0.75rem" }}>
        Razorpay is not configured on this deployment — set{" "}
        <code>NEXT_PUBLIC_RAZORPAY_KEY_ID</code> to enable this checkout.
      </div>
    );
  }

  async function onOpen() {
    setOpening(true);
    try {
      await loadCheckoutScript();
      const checkout = new window.Razorpay!({
        key: keyId,
        order_id: orderId,
        amount: Math.round(Number(amount) * 100),
        currency: currency.toUpperCase(),
        name: "SteelNail Works",
        description: "Milestone payment",
        prefill: { name: buyerName, email: buyerEmail },
        theme: { color: "#b45309" },
        handler: () => {
          onSettled(
            "Payment submitted to Razorpay — the milestone will settle once our webhook receives confirmation.",
            false,
          );
        },
        modal: {
          ondismiss: () => onSettled("Razorpay checkout closed before completing payment.", true),
        },
      });
      checkout.open();
    } catch (err) {
      onSettled(err instanceof Error ? err.message : "Failed to open Razorpay checkout", true);
    } finally {
      setOpening(false);
    }
  }

  return (
    <button onClick={onOpen} disabled={opening} style={{ ...ui.buttonSecondary, marginTop: "0.75rem" }}>
      {opening ? "Loading Razorpay…" : "Open Razorpay checkout"}
    </button>
  );
}
