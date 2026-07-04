import { ui } from "@/lib/ui";

export const metadata = { title: "About" };

const STATS = [
  { label: "Annual production capacity", value: "18,000+ tons" },
  { label: "SKUs in active production", value: "40+" },
  { label: "Warehouses", value: "2 (North & West)" },
  { label: "Finishes offered", value: "4" },
];

export default function AboutPage() {
  return (
    <main style={ui.page}>
      <p style={{ letterSpacing: "0.2em", fontSize: 12, color: "var(--color-accent)", textTransform: "uppercase" }}>
        About us
      </p>
      <h1 style={{ fontSize: "2.2rem", margin: "0.4rem 0 1rem" }}>
        A steel nail manufacturer built for industrial buyers.
      </h1>
      <p style={{ maxWidth: 640, lineHeight: 1.7, color: "var(--color-muted)", fontSize: 16 }}>
        SteelNail Works manufactures wire nails, ring-shank, and screw-shank fasteners at
        volume for construction contractors, pallet manufacturers, and fastener
        distributors. Every SKU is produced from certified raw wire rod and finished to
        bright, electro-galvanized, hot-dip galvanized, or stainless-steel specification.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "1rem", margin: "2rem 0" }}>
        {STATS.map((s) => (
          <div key={s.label} style={ui.card}>
            <p style={{ fontSize: "1.4rem", fontWeight: 700, margin: 0, color: "var(--color-accent)" }}>{s.value}</p>
            <p style={{ fontSize: 13, color: "var(--color-muted)", margin: "0.25rem 0 0" }}>{s.label}</p>
          </div>
        ))}
      </div>

      <div style={ui.card}>
        <h2 style={{ fontSize: "1.2rem", marginTop: 0 }}>Why buyers work with us</h2>
        <ul style={{ lineHeight: 1.9, paddingLeft: "1.2rem", color: "#374151" }}>
          <li>
            <strong>Transparent, tiered pricing.</strong> Every SKU publishes its 1–5 ton,
            5–20 ton, and 20+ ton price-per-kg — no opaque quote-only pricing.
          </li>
          <li>
            <strong>AI-assisted negotiation.</strong> Our sales agent checks live
            inventory and pricing instantly and can approve volume discounts against your
            organization&apos;s credit profile — always bound by a fixed, non-negotiable
            profit margin, so pricing stays fair and consistent.
          </li>
          <li>
            <strong>Contract-secured milestones.</strong> A 30% advance releases
            production; the remaining 70% settles only once a Bill of Lading has been
            uploaded and verified by our sales team.
          </li>
          <li>
            <strong>Direct factory relationship.</strong> No intermediaries — orders route
            straight to production planning and warehouse dispatch.
          </li>
        </ul>
      </div>
    </main>
  );
}
