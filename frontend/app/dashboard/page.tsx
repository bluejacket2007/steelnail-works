"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { ui } from "@/lib/ui";

export default function DashboardOverview() {
  const { user } = useAuth();
  if (!user) return null;

  const isBuyer = user.role === "ClientProcurement";

  return (
    <div>
      <h1 style={{ fontSize: "1.8rem", marginBottom: "0.25rem" }}>Overview</h1>
      <p style={{ color: "#6b7280", marginBottom: "1.5rem" }}>
        Welcome back, {user.full_name.split(" ")[0]}.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "1rem" }}>
        <Link href="/dashboard/rfqs" style={{ textDecoration: "none", color: "inherit" }}>
          <div style={ui.card}>
            <h2 style={{ fontSize: "1.1rem", margin: 0 }}>
              {isBuyer ? "Submit or track an RFQ" : "Manage RFQs"}
            </h2>
            <p style={{ fontSize: 13, color: "#6b7280", marginTop: "0.4rem" }}>
              {isBuyer
                ? "Request a bulk quote and negotiate volume pricing with the AI agent."
                : "Review buyer RFQs, issue quotes, and move deals through approval."}
            </p>
          </div>
        </Link>
        <Link href="/dashboard/orders" style={{ textDecoration: "none", color: "inherit" }}>
          <div style={ui.card}>
            <h2 style={{ fontSize: "1.1rem", margin: 0 }}>Orders & milestones</h2>
            <p style={{ fontSize: 13, color: "#6b7280", marginTop: "0.4rem" }}>
              Track the 30% advance / 70% balance payment structure and Bill of Lading status.
            </p>
          </div>
        </Link>
      </div>
    </div>
  );
}
