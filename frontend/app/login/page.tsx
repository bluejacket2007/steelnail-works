"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth-context";
import { ui } from "@/lib/ui";

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.push(searchParams.get("next") || "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main style={{ ...ui.page, maxWidth: 420 }}>
      <h1 style={{ fontSize: "1.8rem" }}>Sign in</h1>
      <p style={{ color: "var(--color-muted)", marginBottom: "1.5rem" }}>
        Access your organization&apos;s procurement dashboard.
      </p>

      {error && <div style={ui.errorBox}>{error}</div>}

      <form onSubmit={onSubmit} style={ui.card}>
        <label style={ui.label}>Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={ui.input}
        />
        <label style={ui.label}>Password</label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={ui.input}
        />
        <button type="submit" disabled={submitting} style={ui.button}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p style={{ fontSize: 14 }}>
        New buyer organization?{" "}
        <Link href="/register" style={{ color: "var(--color-accent)" }}>
          Register here
        </Link>
      </p>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div style={{ padding: "3rem", textAlign: "center" }}>Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
