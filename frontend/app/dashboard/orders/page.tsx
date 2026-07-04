"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { listOrders, type Order } from "@/lib/api";
import { statusColor, ui } from "@/lib/ui";

export default function OrdersListPage() {
  const { accessToken } = useAuth();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    listOrders(accessToken)
      .then(setOrders)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load orders"))
      .finally(() => setLoading(false));
  }, [accessToken]);

  return (
    <div>
      <h1 style={{ fontSize: "1.8rem", marginBottom: "1rem" }}>Orders</h1>
      {error && <div style={ui.errorBox}>{error}</div>}
      {loading ? (
        <p style={{ color: "#6b7280" }}>Loading…</p>
      ) : orders.length === 0 ? (
        <p style={{ color: "#6b7280" }}>
          No orders yet — accept a quote on an approved RFQ to generate a contract.
        </p>
      ) : (
        orders.map((order) => (
          <Link key={order.id} href={`/dashboard/orders/${order.id}`} style={{ textDecoration: "none", color: "inherit" }}>
            <div style={{ ...ui.card, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <p style={{ margin: 0, fontWeight: 600 }}>Order {order.id.slice(0, 8)}</p>
                <p style={{ margin: "0.2rem 0 0", fontSize: 13, color: "#6b7280" }}>
                  {order.total_amount} {order.currency}
                </p>
              </div>
              <span style={ui.badge(statusColor[order.status] ?? "#6b7280")}>
                {order.status.replace(/_/g, " ")}
              </span>
            </div>
          </Link>
        ))
      )}
    </div>
  );
}
