"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth-context";
import { createRfq, listRfqs, type RFQ } from "@/lib/api";
import { statusColor, ui } from "@/lib/ui";

function RfqList() {
  const { user, accessToken } = useAuth();
  const searchParams = useSearchParams();
  const [rfqs, setRfqs] = useState<RFQ[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sku, setSku] = useState("");
  const [tons, setTons] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Deep-linked from a product detail page's "Request a bulk quote" CTA.
  useEffect(() => {
    const prefill = searchParams.get("sku");
    if (prefill) setSku(prefill);
  }, [searchParams]);

  async function refresh() {
    if (!accessToken) return;
    setLoading(true);
    try {
      setRfqs(await listRfqs(accessToken));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load RFQs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setError(null);
    setSubmitting(true);
    try {
      await createRfq(accessToken, {
        product_sku: sku,
        quantity_tons: Number(tons),
        target_price_per_kg: targetPrice ? Number(targetPrice) : undefined,
      });
      setSku("");
      setTons("");
      setTargetPrice("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit RFQ");
    } finally {
      setSubmitting(false);
    }
  }

  const isBuyer = user?.role === "ClientProcurement";

  return (
    <div>
      <h1 style={{ fontSize: "1.8rem", marginBottom: "1rem" }}>Requests for Quote</h1>
      {error && <div style={ui.errorBox}>{error}</div>}

      {isBuyer && (
        <form onSubmit={onSubmit} style={ui.card}>
          <h2 style={{ fontSize: "1.05rem", marginTop: 0 }}>Submit a new RFQ</h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label style={ui.label}>Product SKU</label>
              <input required value={sku} onChange={(e) => setSku(e.target.value)} style={ui.input} />
            </div>
            <div>
              <label style={ui.label}>Quantity (tons)</label>
              <input
                required
                type="number"
                min="0.001"
                step="0.001"
                value={tons}
                onChange={(e) => setTons(e.target.value)}
                style={ui.input}
              />
            </div>
            <div>
              <label style={ui.label}>Target price ₹/kg (optional)</label>
              <input
                type="number"
                min="0.0001"
                step="0.0001"
                value={targetPrice}
                onChange={(e) => setTargetPrice(e.target.value)}
                style={ui.input}
              />
            </div>
          </div>
          <button type="submit" disabled={submitting} style={ui.button}>
            {submitting ? "Submitting…" : "Submit RFQ"}
          </button>
        </form>
      )}

      {loading ? (
        <p style={{ color: "#6b7280" }}>Loading…</p>
      ) : rfqs.length === 0 ? (
        <p style={{ color: "#6b7280" }}>No RFQs yet.</p>
      ) : (
        rfqs.map((rfq) => (
          <Link key={rfq.id} href={`/dashboard/rfqs/${rfq.id}`} style={{ textDecoration: "none", color: "inherit" }}>
            <div style={{ ...ui.card, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <p style={{ margin: 0, fontWeight: 600 }}>RFQ {rfq.id.slice(0, 8)}</p>
                <p style={{ margin: "0.2rem 0 0", fontSize: 13, color: "#6b7280" }}>
                  {rfq.product_sku} · {rfq.quantity_tons} tons
                  {rfq.target_price_per_kg ? ` · target ₹${rfq.target_price_per_kg}/kg` : ""}
                </p>
              </div>
              <span style={ui.badge(statusColor[rfq.status] ?? "#6b7280")}>{rfq.status}</span>
            </div>
          </Link>
        ))
      )}
    </div>
  );
}

export default function RfqListPage() {
  return (
    <Suspense fallback={<p style={{ color: "#6b7280" }}>Loading…</p>}>
      <RfqList />
    </Suspense>
  );
}
