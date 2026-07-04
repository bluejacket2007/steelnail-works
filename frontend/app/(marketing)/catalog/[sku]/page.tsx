import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getProduct } from "@/lib/api";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ sku: string }> }) {
  const { sku } = await params;
  try {
    const product = await getProduct(sku);
    return { title: product.name };
  } catch {
    return { title: "Product" };
  }
}

export default async function ProductDetailPage({ params }: { params: Promise<{ sku: string }> }) {
  const { sku } = await params;

  let product;
  try {
    product = await getProduct(sku);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const attrs = product.attributes;

  return (
    <main style={ui.page}>
      <Link href="/catalog" style={{ fontSize: 13, color: "var(--color-accent)", textDecoration: "none" }}>
        ← Back to catalog
      </Link>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
        <div>
          <p style={{ fontSize: 12, color: "var(--color-muted)", margin: 0 }}>SKU {product.sku}</p>
          <h1 style={{ fontSize: "2rem", margin: "0.25rem 0 0.5rem" }}>{product.name}</h1>
          {product.description && (
            <p style={{ color: "var(--color-muted)", maxWidth: 560, lineHeight: 1.6 }}>{product.description}</p>
          )}
        </div>
        <Link
          href={`/dashboard/rfqs?sku=${encodeURIComponent(product.sku)}`}
          style={{ ...ui.button, textDecoration: "none", display: "inline-block", whiteSpace: "nowrap" }}
        >
          Request a bulk quote
        </Link>
      </div>

      {attrs && (
        <div style={ui.card}>
          <h2 style={{ fontSize: "1.05rem", marginTop: 0 }}>Specification</h2>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <tbody>
              <SpecRow label="Length" value={`${attrs.length_mm} mm (${attrs.length_inches}")`} />
              <SpecRow
                label="Wire gauge"
                value={`${attrs.wire_gauge_mm} mm${attrs.wire_gauge_awg ? ` (AWG ${attrs.wire_gauge_awg})` : ""}`}
              />
              <SpecRow label="Head style" value={attrs.head_style} />
              <SpecRow label="Shank type" value={attrs.shank_type} />
              <SpecRow label="Finish" value={attrs.finish} last />
            </tbody>
          </table>
        </div>
      )}

      <div style={ui.card}>
        <h2 style={{ fontSize: "1.05rem", marginTop: 0 }}>Tiered bulk pricing</h2>
        {product.pricing_tiers.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--color-muted)" }}>
            No published tiers — request a quote for custom volume pricing.
          </p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid var(--color-border)" }}>
                <th style={{ padding: "0.4rem 0" }}>Volume (tons)</th>
                <th style={{ padding: "0.4rem 0" }}>Price per kg</th>
              </tr>
            </thead>
            <tbody>
              {product.pricing_tiers.map((tier, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                  <td style={{ padding: "0.5rem 0" }}>
                    {tier.moq_min_tons} – {tier.moq_max_tons ?? "∞"}
                  </td>
                  <td style={{ padding: "0.5rem 0", fontWeight: 600, color: "var(--color-accent)" }}>
                    ₹{tier.price_per_kg}/kg ({tier.currency})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p style={{ fontSize: 13, color: "var(--color-muted)" }}>
        Need a custom length, gauge, or finish not listed here? Submit an RFQ and our AI
        sales agent — or a sales manager for non-standard specs — will work out volume
        pricing and delivery timelines with you.
      </p>
    </main>
  );
}

function SpecRow({ label, value, last }: { label: string; value: string; last?: boolean }) {
  return (
    <tr style={{ borderBottom: last ? "none" : "1px solid #f3f4f6" }}>
      <td style={{ padding: "0.45rem 0", color: "var(--color-muted)", width: 160 }}>{label}</td>
      <td style={{ padding: "0.45rem 0", fontWeight: 600 }}>{value}</td>
    </tr>
  );
}
