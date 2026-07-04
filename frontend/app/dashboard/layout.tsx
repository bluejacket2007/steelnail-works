"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";

const STAFF_ROLES = new Set(["SuperAdmin", "SalesManager", "SalesRep"]);

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      // Read the query string directly (client-only) instead of
      // useSearchParams() so this redirect effect doesn't force every
      // dashboard route into a Suspense boundary during prerendering.
      const qs = typeof window !== "undefined" ? window.location.search : "";
      const fullPath = qs ? `${pathname}${qs}` : pathname;
      router.replace(`/login?next=${encodeURIComponent(fullPath)}`);
    }
  }, [loading, user, router, pathname]);

  if (loading) {
    return <div style={{ padding: "3rem", textAlign: "center", color: "#6b7280" }}>Loading…</div>;
  }
  if (!user) return null;

  const isStaff = STAFF_ROLES.has(user.role);

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <aside
        style={{
          width: 220,
          background: "#1f2937",
          color: "#f3f4f6",
          padding: "1.5rem 1rem",
          flexShrink: 0,
        }}
      >
        <p style={{ fontWeight: 700, letterSpacing: "0.05em", marginBottom: "0.25rem" }}>
          SteelNail<span style={{ color: "#f59e0b" }}>Works</span>
        </p>
        <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: "1.5rem" }}>
          {user.full_name} · {user.role}
        </p>

        <nav style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          <NavLink href="/dashboard" label="Overview" />
          <NavLink href="/dashboard/rfqs" label="RFQs" />
          <NavLink href="/dashboard/orders" label="Orders" />
          {isStaff && <NavLink href="/dashboard/orgs" label="Organizations" />}
          {isStaff && <NavLink href="/dashboard/inquiries" label="Inquiries" />}
          <NavLink href="/" label="← Public site" />
        </nav>

        <button
          onClick={() => logout().then(() => router.push("/login"))}
          style={{
            marginTop: "2rem",
            background: "transparent",
            border: "1px solid #4b5563",
            color: "#f3f4f6",
            padding: "0.5rem 0.8rem",
            borderRadius: 6,
            cursor: "pointer",
            fontSize: 13,
            width: "100%",
          }}
        >
          Sign out
        </button>
      </aside>
      <main style={{ flex: 1, background: "#f4f1ea", padding: "2rem" }}>{children}</main>
    </div>
  );
}

function NavLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      style={{
        color: "#e5e7eb",
        textDecoration: "none",
        padding: "0.45rem 0.6rem",
        borderRadius: 6,
        fontSize: 14,
      }}
    >
      {label}
    </Link>
  );
}
