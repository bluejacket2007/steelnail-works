import Link from "next/link";

export function SiteFooter() {
  return (
    <footer style={{ borderTop: "1px solid var(--color-border)", marginTop: "3rem" }}>
      <div
        style={{
          maxWidth: 1080,
          margin: "0 auto",
          padding: "2rem 1.5rem",
          display: "flex",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "1.5rem",
          fontSize: 13,
          color: "var(--color-muted)",
        }}
      >
        <div style={{ maxWidth: 320 }}>
          <p style={{ fontWeight: 700, color: "var(--color-ink)", marginBottom: "0.35rem" }}>
            SteelNail<span style={{ color: "var(--color-accent)" }}>Works</span>
          </p>
          <p style={{ margin: 0 }}>
            Bulk steel nail manufacturing for construction, pallet, and fastener
            distribution — wire nails, ring-shank, screw-shank, in bright, galvanized,
            and stainless finishes.
          </p>
        </div>

        <div>
          <p style={{ fontWeight: 700, color: "var(--color-ink)", marginBottom: "0.35rem" }}>Company</p>
          <FooterLink href="/about" label="About us" />
          <FooterLink href="/how-it-works" label="How it works" />
          <FooterLink href="/contact" label="Contact" />
        </div>

        <div>
          <p style={{ fontWeight: 700, color: "var(--color-ink)", marginBottom: "0.35rem" }}>Marketplace</p>
          <FooterLink href="/catalog" label="Product catalog" />
          <FooterLink href="/login" label="Buyer sign in" />
          <FooterLink href="/register" label="Register organization" />
        </div>

        <div style={{ fontSize: 12 }}>
          <p style={{ margin: 0 }}>© {new Date().getFullYear()} SteelNail Works.</p>
          <p style={{ margin: 0 }}>All prices in INR unless otherwise agreed.</p>
        </div>
      </div>
    </footer>
  );
}

function FooterLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} style={{ display: "block", textDecoration: "none", marginBottom: "0.3rem" }}>
      {label}
    </Link>
  );
}
