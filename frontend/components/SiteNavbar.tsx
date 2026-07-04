"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { ui } from "@/lib/ui";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/catalog", label: "Catalog" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
];

export function SiteNavbar() {
  const pathname = usePathname();
  const { user, loading } = useAuth();

  return (
    <header
      style={{
        borderBottom: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        position: "sticky",
        top: 0,
        zIndex: 10,
      }}
    >
      <div
        style={{
          maxWidth: 1080,
          margin: "0 auto",
          padding: "0.9rem 1.5rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <Link href="/" style={{ textDecoration: "none", fontWeight: 700, fontSize: "1.1rem", color: "var(--color-ink)" }}>
          SteelNail<span style={{ color: "var(--color-accent)" }}>Works</span>
        </Link>

        <nav style={{ display: "flex", gap: "1.25rem", fontSize: 14 }}>
          {LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                style={{
                  textDecoration: "none",
                  color: active ? "var(--color-accent)" : "var(--color-ink)",
                  fontWeight: active ? 700 : 400,
                }}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div style={{ display: "flex", gap: "0.6rem" }}>
          {!loading && user ? (
            <Link href="/dashboard" style={{ ...ui.button, textDecoration: "none", display: "inline-block" }}>
              Dashboard
            </Link>
          ) : (
            <>
              <Link href="/login" style={{ ...ui.buttonSecondary, textDecoration: "none", display: "inline-block" }}>
                Sign in
              </Link>
              <Link href="/register" style={{ ...ui.button, textDecoration: "none", display: "inline-block" }}>
                Register
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
