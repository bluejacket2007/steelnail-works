import Link from "next/link";
import { fetchProducts, type Product } from "@/lib/api";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const HIGHLIGHTS = [
  {
    title: "Tiered bulk pricing",
    body: "Transparent price-per-kg tiers from 1 ton to 20+ tons, published for every SKU.",
  },
  {
    title: "AI-assisted negotiation",
    body: "Our sales agent checks live stock and pricing instantly, and can approve volume discounts on the spot — bound by a hard margin floor.",
  },
  {
    title: "Milestone-secured contracts",
    body: "30% advance releases production; the 70% balance settles only against a verified Bill of Lading.",
  },
];

export default async function HomePage() {
  let products: Product[] = [];
  let backendUp = true;
  try {
    products = (await fetchProducts()).slice(0, 3);
  } catch {
    backendUp = false;
  }

  return (
    <main>
      <section style={{ ...ui.page, paddingTop: "4rem", paddingBottom: "3rem" }}>
        <p style={{ letterSpacing: "0.2em", fontSize: 12, color: "var(--color-accent)", textTransform: "uppercase" }}>
          Industrial B2B Marketplace
        </p>
        <h1 style={{ fontSize: "2.8rem", margin: "0.4rem 0 1rem", maxWidth: 640 }}>
          Bulk steel nails, <em>engineered</em> for construction &amp; distribution scale.
        </h1>
        <p style={{ maxWidth: 560, lineHeight: 1.7, color: "var(--color-muted)", fontSize: 16, marginBottom: "1.75rem" }}>
          Wire nails, ring-shank, and screw-shank in bright, electro-galvanized, hot-dip
          galvanized, and stainless finishes — quoted by volume, negotiated with an AI
          sales agent, and secured with a 30/70 milestone payment contract.
        </p>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <Link href="/catalog" style={{ ...ui.button, textDecoration: "none", display: "inline-block" }}>
            Browse the catalog
          </Link>
          <Link href="/how-it-works" style={{ ...ui.buttonSecondary, textDecoration: "none", display: "inline-block" }}>
            How bulk ordering works
          </Link>
        </div>
      </section>

      <section style={{ background: "var(--color-surface)", borderTop: "1px solid var(--color-border)", borderBottom: "1px solid var(--color-border)" }}>
        <div style={{ ...ui.page, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1.5rem" }}>
          {HIGHLIGHTS.map((h) => (
            <div key={h.title}>
              <h2 style={{ fontSize: "1.05rem", marginBottom: "0.4rem" }}>{h.title}</h2>
              <p style={{ fontSize: 14, color: "var(--color-muted)", lineHeight: 1.6, margin: 0 }}>{h.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section style={ui.page}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1.4rem", margin: 0 }}>Featured products</h2>
          <Link href="/catalog" style={{ fontSize: 14, color: "var(--color-accent)", textDecoration: "none" }}>
            View full catalog →
          </Link>
        </div>

        {!backendUp && (
          <p style={{ padding: "1rem", background: "var(--color-accent-soft)", borderRadius: 8 }}>
            Backend API is not reachable — start it with <code>uvicorn app.main:app</code> (or{" "}
            <code>docker compose up</code>).
          </p>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "1rem" }}>
          {products.map((p) => (
            <Link key={p.sku} href={`/catalog/${p.sku}`} style={{ textDecoration: "none", color: "inherit" }}>
              <article style={ui.card}>
                <h3 style={{ fontSize: "1.05rem", margin: 0 }}>{p.name}</h3>
                <p style={{ fontSize: 12, color: "var(--color-muted)", margin: "0.25rem 0 0.75rem" }}>
                  SKU {p.sku}
                </p>
                {p.attributes && (
                  <p style={{ fontSize: 13, color: "#374151", margin: 0 }}>
                    {p.attributes.length_mm} mm · {p.attributes.finish} · {p.attributes.shank_type} shank
                  </p>
                )}
                {p.pricing_tiers.length > 0 && (
                  <p style={{ marginTop: "0.75rem", fontWeight: 600, fontSize: 14, color: "var(--color-accent)" }}>
                    from ₹{Math.min(...p.pricing_tiers.map((t) => Number(t.price_per_kg))).toFixed(2)}/kg
                  </p>
                )}
              </article>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
