"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { listContactInquiries, markInquiryHandled, type ContactInquiry } from "@/lib/api";
import { ui } from "@/lib/ui";

export default function InquiriesPage() {
  const { accessToken } = useAuth();
  const [inquiries, setInquiries] = useState<ContactInquiry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    if (!accessToken) return;
    setLoading(true);
    try {
      setInquiries(await listContactInquiries(accessToken));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load inquiries");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  async function onMarkHandled(id: string) {
    if (!accessToken) return;
    setBusy(id);
    try {
      await markInquiryHandled(accessToken, id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update inquiry");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: "1.8rem", marginBottom: "1rem" }}>Contact inquiries</h1>
      <p style={{ color: "#6b7280", marginBottom: "1rem" }}>
        Submissions from the public contact form, newest unhandled first.
      </p>
      {error && <div style={ui.errorBox}>{error}</div>}

      {loading ? (
        <p style={{ color: "#6b7280" }}>Loading…</p>
      ) : inquiries.length === 0 ? (
        <p style={{ color: "#6b7280" }}>No inquiries yet.</p>
      ) : (
        inquiries.map((inq) => (
          <div key={inq.id} style={ui.card}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
              <div>
                <p style={{ margin: 0, fontWeight: 600 }}>
                  {inq.name} {inq.company ? `· ${inq.company}` : ""}
                </p>
                <p style={{ margin: "0.2rem 0 0.5rem", fontSize: 13, color: "#6b7280" }}>
                  {inq.email}
                  {inq.phone ? ` · ${inq.phone}` : ""} ·{" "}
                  {new Date(inq.created_at).toLocaleString()}
                </p>
                <p style={{ margin: 0, fontSize: 14 }}>{inq.message}</p>
              </div>
              {!inq.handled ? (
                <button disabled={busy === inq.id} onClick={() => onMarkHandled(inq.id)} style={ui.buttonSecondary}>
                  Mark handled
                </button>
              ) : (
                <span style={ui.badge("#059669")}>Handled</span>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
