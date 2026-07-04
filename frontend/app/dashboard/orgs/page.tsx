"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { listOrganizations, type Organization } from "@/lib/api";
import { ui } from "@/lib/ui";

export default function OrganizationsListPage() {
  const { accessToken } = useAuth();
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    listOrganizations(accessToken)
      .then(setOrgs)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load organizations"))
      .finally(() => setLoading(false));
  }, [accessToken]);

  return (
    <div>
      <h1 style={{ fontSize: "1.8rem", marginBottom: "1rem" }}>Buyer organizations</h1>
      {error && <div style={ui.errorBox}>{error}</div>}
      {loading ? (
        <p style={{ color: "#6b7280" }}>Loading…</p>
      ) : (
        orgs.map((org) => (
          <Link key={org.id} href={`/dashboard/orgs/${org.id}`} style={{ textDecoration: "none", color: "inherit" }}>
            <div style={{ ...ui.card, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <p style={{ margin: 0, fontWeight: 600 }}>{org.legal_name}</p>
                <p style={{ margin: "0.2rem 0 0", fontSize: 13, color: "#6b7280" }}>
                  {org.gstin ?? org.ein ?? "No tax ID on file"} · limit ₹{org.credit_limit}
                </p>
              </div>
              <span style={ui.badge("#6b7280")}>{org.credit_rating}</span>
            </div>
          </Link>
        ))
      )}
    </div>
  );
}
