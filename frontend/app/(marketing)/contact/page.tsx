"use client";

import { useState, type FormEvent } from "react";
import { submitContactInquiry } from "@/lib/api";
import { ui } from "@/lib/ui";

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", company: "", phone: "", message: "" });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await submitContactInquiry({
        name: form.name,
        email: form.email,
        company: form.company || undefined,
        phone: form.phone || undefined,
        message: form.message,
      });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send your message");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main style={{ ...ui.page, maxWidth: 640 }}>
      <p style={{ letterSpacing: "0.2em", fontSize: 12, color: "var(--color-accent)", textTransform: "uppercase" }}>
        Contact
      </p>
      <h1 style={{ fontSize: "2rem", margin: "0.4rem 0 0.75rem" }}>Talk to our sales team</h1>
      <p style={{ color: "var(--color-muted)", marginBottom: "1.5rem" }}>
        For bulk pricing, custom specifications, or anything the AI negotiation agent can&apos;t
        resolve, reach us directly and a sales manager will follow up.
      </p>

      {error && <div style={ui.errorBox}>{error}</div>}

      {submitted ? (
        <div style={{ ...ui.card, background: "#ecfdf5", color: "#065f46" }}>
          Thanks — your message has been received. A member of our sales team will reach
          out shortly.
        </div>
      ) : (
        <form onSubmit={onSubmit} style={ui.card}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label style={ui.label}>Name</label>
              <input required value={form.name} onChange={(e) => set("name", e.target.value)} style={ui.input} />
            </div>
            <div>
              <label style={ui.label}>Email</label>
              <input
                required
                type="email"
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
                style={ui.input}
              />
            </div>
            <div>
              <label style={ui.label}>Company (optional)</label>
              <input value={form.company} onChange={(e) => set("company", e.target.value)} style={ui.input} />
            </div>
            <div>
              <label style={ui.label}>Phone (optional)</label>
              <input value={form.phone} onChange={(e) => set("phone", e.target.value)} style={ui.input} />
            </div>
          </div>
          <label style={ui.label}>Message</label>
          <textarea
            required
            rows={5}
            value={form.message}
            onChange={(e) => set("message", e.target.value)}
            style={{ ...ui.input, resize: "vertical", fontFamily: "inherit" }}
          />
          <button type="submit" disabled={submitting} style={ui.button}>
            {submitting ? "Sending…" : "Send message"}
          </button>
        </form>
      )}
    </main>
  );
}
