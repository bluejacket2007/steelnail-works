"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { RazorpayButton } from "@/components/RazorpayButton";
import { StripePaymentForm } from "@/components/StripePaymentForm";
import { useAuth } from "@/lib/auth-context";
import {
  getOrder,
  initiatePayment,
  uploadBol,
  verifyBol,
  type Milestone,
  type Order,
} from "@/lib/api";
import { statusColor, ui } from "@/lib/ui";

interface PendingIntent {
  provider: "stripe" | "razorpay";
  provider_payment_id: string;
  client_secret: string | null;
  amount: string;
  currency: string;
}

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user, accessToken } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // milestone id currently acting on
  const [bolRef, setBolRef] = useState("");
  const [paymentNotice, setPaymentNotice] = useState<string | null>(null);
  const [pendingIntents, setPendingIntents] = useState<Record<string, PendingIntent>>({});

  const isBuyer = user?.role === "ClientProcurement";
  const isManager = user?.role === "SuperAdmin" || user?.role === "SalesManager";

  async function refresh() {
    if (!accessToken) return;
    setLoading(true);
    try {
      setOrder(await getOrder(accessToken, id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load order");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, id]);

  async function onInitiate(milestone: Milestone, provider: "stripe" | "razorpay") {
    if (!accessToken) return;
    setBusy(milestone.id);
    setError(null);
    setPaymentNotice(null);
    try {
      const intent = await initiatePayment(accessToken, milestone.id, provider);
      setPendingIntents((prev) => ({
        ...prev,
        [milestone.id]: {
          provider,
          provider_payment_id: intent.provider_payment_id,
          client_secret: intent.client_secret,
          amount: intent.amount,
          currency: intent.currency,
        },
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to initiate payment");
    } finally {
      setBusy(null);
    }
  }

  function onSettled(milestoneId: string, message: string, isError: boolean) {
    if (isError) {
      setError(message);
    } else {
      setPaymentNotice(message);
      setPendingIntents((prev) => {
        const next = { ...prev };
        delete next[milestoneId];
        return next;
      });
    }
    refresh();
  }

  async function onUploadBol(milestoneId: string) {
    if (!accessToken || !bolRef.trim()) return;
    setBusy(milestoneId);
    setError(null);
    try {
      await uploadBol(accessToken, milestoneId, bolRef.trim());
      setBolRef("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to attach Bill of Lading");
    } finally {
      setBusy(null);
    }
  }

  async function onVerifyBol(milestoneId: string) {
    if (!accessToken) return;
    setBusy(milestoneId);
    setError(null);
    try {
      await verifyBol(accessToken, milestoneId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to verify Bill of Lading");
    } finally {
      setBusy(null);
    }
  }

  if (loading || !order) {
    return <p style={{ color: "#6b7280" }}>{error ?? "Loading…"}</p>;
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
        <h1 style={{ fontSize: "1.6rem", margin: 0 }}>Order {order.id.slice(0, 8)}</h1>
        <span style={ui.badge(statusColor[order.status] ?? "#6b7280")}>
          {order.status.replace(/_/g, " ")}
        </span>
      </div>

      {error && <div style={ui.errorBox}>{error}</div>}
      {paymentNotice && (
        <div style={{ ...ui.errorBox, background: "#dbeafe", color: "#1e40af" }}>{paymentNotice}</div>
      )}

      <div style={ui.card}>
        <p style={{ margin: 0 }}>
          <strong>Contract total:</strong> {order.total_amount} {order.currency}
        </p>
      </div>

      {order.milestones.map((m) => {
        const label = m.milestone_type === "Advance_30" ? "30% Advance Deposit" : "70% Balance (post-BoL)";
        const canPay =
          isBuyer &&
          m.status === "Pending" &&
          (m.milestone_type === "Advance_30" || m.bol_verified);
        const canUploadBol =
          isBuyer && m.milestone_type === "Balance_70" && m.status === "Pending" && !m.bol_verified;
        const canVerifyBol =
          isManager && m.milestone_type === "Balance_70" && !m.bol_verified;
        const intent = pendingIntents[m.id];

        return (
          <div key={m.id} style={ui.card}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <p style={{ margin: 0, fontWeight: 600 }}>{label}</p>
                <p style={{ margin: "0.2rem 0 0", fontSize: 13, color: "#6b7280" }}>
                  {m.amount} {order.currency} ({m.percentage}%)
                  {m.paid_at ? ` · paid ${new Date(m.paid_at).toLocaleDateString()}` : ""}
                </p>
              </div>
              <span style={ui.badge(statusColor[m.status] ?? "#6b7280")}>{m.status}</span>
            </div>

            {m.milestone_type === "Balance_70" && (
              <p style={{ fontSize: 12, color: m.bol_verified ? "#059669" : "#d97706", marginTop: "0.5rem" }}>
                {m.bol_verified
                  ? "Bill of Lading verified — balance can be settled."
                  : "Awaiting a verified Bill of Lading before this milestone can be initiated."}
              </p>
            )}

            {canPay && !intent && (
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
                <button disabled={busy === m.id} onClick={() => onInitiate(m, "stripe")} style={ui.button}>
                  Pay via Stripe
                </button>
                <button disabled={busy === m.id} onClick={() => onInitiate(m, "razorpay")} style={ui.buttonSecondary}>
                  Pay via Razorpay
                </button>
              </div>
            )}

            {canPay && intent?.provider === "stripe" && intent.client_secret && (
              <StripePaymentForm
                clientSecret={intent.client_secret}
                onSettled={(message, isError) => onSettled(m.id, message, isError)}
              />
            )}

            {canPay && intent?.provider === "razorpay" && (
              <RazorpayButton
                orderId={intent.provider_payment_id}
                amount={intent.amount}
                currency={intent.currency}
                buyerName={user?.full_name}
                buyerEmail={user?.email}
                onSettled={(message, isError) => onSettled(m.id, message, isError)}
              />
            )}

            {canUploadBol && (
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", alignItems: "end" }}>
                <input
                  placeholder="Bill of Lading document reference / URL"
                  value={bolRef}
                  onChange={(e) => setBolRef(e.target.value)}
                  style={{ ...ui.input, marginBottom: 0, flex: 1 }}
                />
                <button disabled={busy === m.id} onClick={() => onUploadBol(m.id)} style={ui.buttonSecondary}>
                  Attach BoL
                </button>
              </div>
            )}

            {canVerifyBol && (
              <button
                disabled={busy === m.id}
                onClick={() => onVerifyBol(m.id)}
                style={{ ...ui.button, marginTop: "0.75rem" }}
              >
                Verify Bill of Lading
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
