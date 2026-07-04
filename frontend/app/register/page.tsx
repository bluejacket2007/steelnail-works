"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth-context";
import { ui } from "@/lib/ui";

function RegisterForm() {
  const { register } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
    organization_name: "",
    gstin: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register({
        email: form.email,
        password: form.password,
        full_name: form.full_name,
        organization_name: form.organization_name,
        gstin: form.gstin || undefined,
      });
      router.push(searchParams.get("next") || "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main style={{ ...ui.page, maxWidth: 480 }}>
      <h1 style={{ fontSize: "1.8rem" }}>Register your organization</h1>
      <p style={{ color: "var(--color-muted)", marginBottom: "1.5rem" }}>
        Creates a buyer procurement account. Sales staff accounts are provisioned internally.
      </p>

      {error && <div style={ui.errorBox}>{error}</div>}

      <form onSubmit={onSubmit} style={ui.card}>
        <label style={ui.label}>Organization legal name</label>
        <input
          required
          value={form.organization_name}
          onChange={(e) => set("organization_name", e.target.value)}
          style={ui.input}
        />
        <label style={ui.label}>GSTIN (optional)</label>
        <input value={form.gstin} onChange={(e) => set("gstin", e.target.value)} style={ui.input} />
        <label style={ui.label}>Your full name</label>
        <input
          required
          value={form.full_name}
          onChange={(e) => set("full_name", e.target.value)}
          style={ui.input}
        />
        <label style={ui.label}>Email</label>
        <input
          type="email"
          required
          value={form.email}
          onChange={(e) => set("email", e.target.value)}
          style={ui.input}
        />
        <label style={ui.label}>Password (min. 12 characters)</label>
        <input
          type="password"
          required
          minLength={12}
          value={form.password}
          onChange={(e) => set("password", e.target.value)}
          style={ui.input}
        />
        <button type="submit" disabled={submitting} style={ui.button}>
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p style={{ fontSize: 14 }}>
        Already registered?{" "}
        <Link href="/login" style={{ color: "var(--color-accent)" }}>
          Sign in
        </Link>
      </p>
    </main>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div style={{ padding: "3rem", textAlign: "center" }}>Loading…</div>}>
      <RegisterForm />
    </Suspense>
  );
}
