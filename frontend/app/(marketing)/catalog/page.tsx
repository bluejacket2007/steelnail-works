import Link from "next/link";
import { fetchProducts, type Finish, type HeadStyle, type Product, type ShankType } from "@/lib/api";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";
export const metadata = { title: "Catalog" };

const FINISHES: Finish[] = ["Bright", "Electro-Galvanized", "Hot-Dip Galvanized", "Stainless Steel"];
const SHANK_TYPES: ShankType[] = ["Smooth", "Ring", "Screw"];
const HEAD_STYLES: HeadStyle[] = ["Flat", "Checkered", "Countersunk"];

interface SearchParams {
  finish?: string;
  shank_type?: string;
  head_style?: string;
  min_length_mm?: string;
  max_length_mm?: string;
}

export default async function CatalogPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;

  let products: Product[] = [];
  let error: string | null = null;
  try {
    products = await fetchProducts({
      finish: params.finish as Finish | undefined,
      shank_type: params.shank_type as ShankType | undefined,
      head_style: params.head_style as HeadStyle | undefined,
      min_length_mm: params.min_length_mm ? Number(params.min_length_mm) : undefined,
      max_length_mm: params.max_length_mm ? Number(params.max_length_mm) : undefined,
    });
  } catch (err) {
    error = err instanceof Error ? err.message : "Failed to load the catalog";
  }

  return (
    <main style={ui.page}>
      <h1 style={{ fontSize: "1.9rem", marginBottom: "0.25rem" }}>Product catalog</h1>
      <p style={{ color: "var(--color-muted)", marginBottom: "1.5rem" }}>
        Filter by industrial specification — every SKU carries a published tiered price
        matrix from 1 ton to 20+ tons.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "2rem", alignItems: "start" }}>
        <form method="get" style={{ ...ui.card, position: "sticky", top: "5rem" }}>
          <h2 style={{ fontSize: "0.95rem", marginTop: 0 }}>Filters</h2>

          <label style={ui.label}>Finish</label>
          <select name="finish" defaultValue={params.finish ?? ""} style={ui.input}>
            <option value="">Any</option>
            {FINISHES.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>

          <label style={ui.label}>Shank type</label>
          <select name="shank_type" defaultValue={params.shank_type ?? ""} style={ui.input}>
            <option value="">Any</option>
            {SHANK_TYPES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>

          <label style={ui.label}>Head style</label>
          <select name="head_style" defaultValue={params.head_style ?? ""} style={ui.input}>
            <option value="">Any</option>
            {HEAD_STYLES.map((h) => (
              <option key={h} value={h}>
                {h}
              </option>
            ))}
          </select>

          <label style={ui.label}>Min length (mm)</label>
          <input
            type="number"
            name="min_length_mm"
            defaultValue={params.min_length_mm}
            style={ui.input}
          />

          <label style={ui.label}>Max length (mm)</label>
          <input
            type="number"
            name="max_length_mm"
            defaultValue={params.max_length_mm}
            style={ui.input}
          />

          <button type="submit" style={{ ...ui.button, width: "100%" }}>
            Apply filters
          </button>
          {Object.values(params).some(Boolean) && (
            <Link
              href="/catalog"
              style={{ display: "block", textAlign: "center", marginTop: "0.6rem", fontSize: 13, color: "var(--color-accent)" }}
            >
              Clear all
            </Link>
          )}
        </form>

        <div>
          {error && <div style={ui.errorBox}>{error}</div>}
          {!error && products.length === 0 && (
            <p style={{ color: "var(--color-muted)" }}>No products match these filters.</p>
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
                    <ul style={{ fontSize: 13, color: "#374151", paddingLeft: "1.1rem", margin: 0, lineHeight: 1.7 }}>
                      <li>
                        {p.attributes.length_mm} mm / {p.attributes.length_inches}&quot;
                      </li>
                      <li>
                        Gauge {p.attributes.wire_gauge_mm} mm
                        {p.attributes.wire_gauge_awg ? ` (AWG ${p.attributes.wire_gauge_awg})` : ""}
                      </li>
                      <li>
                        {p.attributes.finish} · {p.attributes.shank_type} shank · {p.attributes.head_style} head
                      </li>
                    </ul>
                  )}
                  {p.pricing_tiers.length > 0 && (
                    <p style={{ marginTop: "0.75rem", fontWeight: 600, fontSize: 14, color: "var(--color-accent)" }}>
                      from ₹{Math.min(...p.pricing_tiers.map((t) => Number(t.price_per_kg))).toFixed(2)}/kg at volume
                    </p>
                  )}
                </article>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
