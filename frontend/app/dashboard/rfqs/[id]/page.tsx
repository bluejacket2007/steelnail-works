"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AgentChat } from "@/components/AgentChat";
import { useAuth } from "@/lib/auth-context";
import {
  acceptQuote,
  getRfq,
  issueQuote,
  listQuotes,
  transitionRfq,
  type Quote,
  type RFQ,
  type RFQStatus,
} from "@/lib/api";
import { statusColor, ui } from "@/lib/ui";

const STAFF_ROLES = new Set(["SuperAdmin", "SalesManager", "SalesRep"]);

// Mirrors backend RFQ_TRANSITIONS — the server is the source of truth;
// this only decides which buttons to render.
const NEXT_STATUSES: Record<RFQStatus, RFQStatus[]> = {
  RFQ_Submitted: ["AI_Negotiating", "Sales_Review", "Rejected"],
  AI_Negotiating: ["Sales_Review", "Rejected"],
  Sales_Review: ["Approved", "AI_Negotiating", "Rejected"],
  Approved: ["Contract_Generated"],
  Contract_Generated: ["Fulfilled"],
  Fulfilled: [],
  Rejected: [],
};

export default function RfqDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user, accessToken } = useAuth();

  const [rfq, setRfq] = useState<RFQ | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [price, setPrice] = useState("");
  const [qtyTons, setQtyTons] = useState("");

  const isStaff = user ? STAFF_ROLES.has(user.role) : false;
  const isManager = user?.role === "SuperAdmin" || user?.role === "SalesManager";
  const isBuyer = user?.role === "ClientProcurement";

  async function refresh() {
    if (!accessToken) return;
    setLoading(true);
    try {
      const [r, q] = await Promise.all([getRfq(accessToken, id), listQuotes(accessToken, id)]);
      setRfq(r);
      setQuotes(q);
      if (!qtyTons) setQtyTons(r.quantity_tons);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load RFQ");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, id]);

  async function onTransition(newStatus: RFQStatus) {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      await transitionRfq(accessToken, id, newStatus);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Transition failed");
    } finally {
      setBusy(false);
    }
  }

  async function onIssueQuote(e: FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      await issueQuote(accessToken, id, {
        quoted_price_per_kg: Number(price),
        quantity_tons: Number(qtyTons),
      });
      setPrice("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to issue quote");
    } finally {
      setBusy(false);
    }
  }

  async function onAccept(quoteId: string) {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      const order = await acceptQuote(accessToken, quoteId);
      router.push(`/dashboard/orders/${order.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept quote");
      setBusy(false);
    }
  }

  if (loading || !rfq) {
    return <p style={{ color: "#6b7280" }}>{error ?? "Loading…"}</p>;
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
        <h1 style={{ fontSize: "1.6rem", margin: 0 }}>RFQ {rfq.id.slice(0, 8)}</h1>
        <span style={ui.badge(statusColor[rfq.status] ?? "#6b7280")}>{rfq.status}</span>
      </div>
      {error && <div style={ui.errorBox}>{error}</div>}

      <div style={ui.card}>
        <p style={{ margin: 0 }}>
          <strong>SKU:</strong> {rfq.product_sku} &nbsp;·&nbsp; <strong>Volume:</strong>{" "}
          {rfq.quantity_tons} tons
          {rfq.target_price_per_kg && (
            <>
              {" "}
              &nbsp;·&nbsp; <strong>Target:</strong> ₹{rfq.target_price_per_kg}/kg
            </>
          )}
        </p>
      </div>

      {isStaff && NEXT_STATUSES[rfq.status].length > 0 && (
        <div style={ui.card}>
          <h2 style={{ fontSize: "1.05rem", marginTop: 0 }}>Move this RFQ</h2>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {NEXT_STATUSES[rfq.status].map((next) => {
              const managerOnly = ["Approved", "Contract_Generated", "Rejected"].includes(next);
              if (managerOnly && !isManager) return null;
              return (
                <button
                  key={next}
                  disabled={busy}
                  onClick={() => onTransition(next)}
                  style={next === "Rejected" ? ui.buttonDanger : ui.buttonSecondary}
                >
                  → {next.replace(/_/g, " ")}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {isStaff && !["Contract_Generated", "Fulfilled", "Rejected"].includes(rfq.status) && (
        <div style={ui.card}>
          <h2 style={{ fontSize: "1.05rem", marginTop: 0 }}>Issue a quote</h2>
          <form onSubmit={onIssueQuote} style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: "0.75rem", alignItems: "end" }}>
            <div>
              <label style={ui.label}>Price ₹/kg</label>
              <input
                required
                type="number"
                min="0.0001"
                step="0.0001"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                style={{ ...ui.input, marginBottom: 0 }}
              />
            </div>
            <div>
              <label style={ui.label}>Quantity (tons)</label>
              <input
                required
                type="number"
                min="0.001"
                step="0.001"
                value={qtyTons}
                onChange={(e) => setQtyTons(e.target.value)}
                style={{ ...ui.input, marginBottom: 0 }}
              />
            </div>
            <button type="submit" disabled={busy} style={ui.button}>
              Issue quote
            </button>
          </form>
        </div>
      )}

      <div style={ui.card}>
        <h2 style={{ fontSize: "1.05rem", marginTop: 0 }}>Quotes</h2>
        {quotes.length === 0 ? (
          <p style={{ fontSize: 13, color: "#6b7280" }}>No quotes issued yet.</p>
        ) : (
          quotes.map((q) => (
            <div
              key={q.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "0.6rem 0",
                borderBottom: "1px solid #f3f4f6",
              }}
            >
              <div>
                <p style={{ margin: 0, fontWeight: 600 }}>
                  ₹{q.quoted_price_per_kg}/kg × {q.quantity_tons} t ({q.currency})
                </p>
                <p style={{ margin: "0.2rem 0 0", fontSize: 12, color: "#6b7280" }}>
                  {q.issued_by_agent ? "Issued by AI agent" : "Issued by sales"}
                  {q.is_accepted ? " · accepted" : ""}
                </p>
              </div>
              {isBuyer && rfq.status === "Approved" && !q.is_accepted && (
                <button disabled={busy} onClick={() => onAccept(q.id)} style={ui.button}>
                  Accept & generate contract
                </button>
              )}
            </div>
          ))
        )}
      </div>

      {!["Fulfilled", "Rejected"].includes(rfq.status) && (
        <AgentChat sessionId={rfq.agent_session_id ?? rfq.id} skuContext={rfq.product_sku} />
      )}
    </div>
  );
}
