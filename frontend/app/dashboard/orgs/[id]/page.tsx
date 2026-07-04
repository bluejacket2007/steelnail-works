"use client";

import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  getOrganization,
  updateCreditRating,
  type CreditRating,
  type Organization,
} from "@/lib/api";
import { ui } from "@/lib/ui";

const RATINGS: CreditRating[] = ["AAA", "AA", "A", "BBB", "BB", "B", "UNRATED"];

export default function OrganizationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user, accessToken } = useAuth();
  const [org, setOrg] = useState<Organization | null>(null);
  const [rating, setRating] = useState<CreditRating>("UNRATED");
  const [limit, setLimit] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const isManager = user?.role === "SuperAdmin" || user?.role === "SalesManager";

  useEffect(() => {
    if (!accessToken) return;
    getOrganization(accessToken, id)
      .then((o) => {
        setOrg(o);
        setRating(o.credit_rating);
        setLimit(o.credit_limit);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load organization"));
  }, [accessToken, id]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateCreditRating(accessToken, id, {
        credit_rating: rating,
        credit_limit: Number(limit),
      });
      setOrg(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update credit profile");
    } finally {
      setSaving(false);
    }
  }

  if (!org) return <p style={{ color: "#6b7280" }}>{error ?? "Loading…"}</p>;

  return (
    <div>
      <h1 style={{ fontSize: "1.6rem", marginBottom: "1rem" }}>{org.legal_name}</h1>
      {error && <div style={ui.errorBox}>{error}</div>}

      <div style={ui.card}>
        <p style={{ margin: 0, fontSize: 14 }}>
          <strong>GSTIN:</strong> {org.gstin ?? "—"} &nbsp;·&nbsp; <strong>EIN:</strong> {org.ein ?? "—"}
          <br />
          <strong>Country:</strong> {org.country_code} &nbsp;·&nbsp;{" "}
          <strong>Verified:</strong> {org.is_verified ? "Yes" : "No"}
        </p>
      </div>

      <div style={ui.card}>
        <h2 style={{ fontSize: "1.05rem", marginTop: 0 }}>Credit profile</h2>
        <p style={{ fontSize: 12, color: "#6b7280", marginBottom: "0.75rem" }}>
          The credit rating caps how much volume discount the AI negotiation agent may
          extend to this buyer — a higher rating unlocks more headroom, but every discount
          still respects the company&apos;s 12% net-margin floor.
        </p>
        {isManager ? (
          <form onSubmit={onSave} style={{ display: "flex", gap: "0.75rem", alignItems: "end", flexWrap: "wrap" }}>
            <div>
              <label style={ui.label}>Credit rating</label>
              <select
                value={rating}
                onChange={(e) => setRating(e.target.value as CreditRating)}
                style={{ ...ui.input, marginBottom: 0 }}
              >
                {RATINGS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={ui.label}>Credit limit (₹)</label>
              <input
                type="number"
                min="0"
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                style={{ ...ui.input, marginBottom: 0 }}
              />
            </div>
            <button type="submit" disabled={saving} style={ui.button}>
              {saving ? "Saving…" : "Save"}
            </button>
          </form>
        ) : (
          <p style={{ margin: 0 }}>
            <strong>{org.credit_rating}</strong> · limit ₹{org.credit_limit}
          </p>
        )}
      </div>
    </div>
  );
}
