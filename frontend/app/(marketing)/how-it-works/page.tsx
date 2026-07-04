import Link from "next/link";
import { ui } from "@/lib/ui";

export const metadata = { title: "How it works" };

const STEPS = [
  {
    step: "1",
    title: "Submit an RFQ",
    body: "Pick a SKU from the catalog and specify the volume you need. Registration takes a minute — no sales call required to get started.",
  },
  {
    step: "2",
    title: "Negotiate with the AI sales agent",
    body: "Chat directly with our negotiation agent about pricing, delivery volume, and stock availability. It checks live inventory and pricing tiers before responding, and can approve volume discounts on the spot.",
  },
  {
    step: "3",
    title: "Sales review & approval",
    body: "For non-standard terms, or once you're ready to lock in pricing, a sales manager reviews and approves the deal.",
  },
  {
    step: "4",
    title: "Accept the quote — contract generated",
    body: "Accepting an approved quote automatically generates your order and splits billing into the 30/70 milestone structure.",
  },
  {
    step: "5",
    title: "30% advance → production begins",
    body: "Pay the 30% advance deposit via Stripe or Razorpay to release the order into production.",
  },
  {
    step: "6",
    title: "Bill of Lading verification",
    body: "Once your shipment is ready, upload the Bill of Lading. Our sales team verifies it before the balance can be collected.",
  },
  {
    step: "7",
    title: "70% balance → shipped",
    body: "Settle the remaining 70% and your order ships — a proforma invoice is generated automatically the moment payment clears.",
  },
];

export default function HowItWorksPage() {
  return (
    <main style={ui.page}>
      <p style={{ letterSpacing: "0.2em", fontSize: 12, color: "var(--color-accent)", textTransform: "uppercase" }}>
        Process
      </p>
      <h1 style={{ fontSize: "2.2rem", margin: "0.4rem 0 1rem" }}>How bulk ordering works</h1>
      <p style={{ maxWidth: 600, lineHeight: 1.7, color: "var(--color-muted)", marginBottom: "2rem" }}>
        From first request to a shipped, milestone-secured contract — every step is
        tracked through a single dashboard.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {STEPS.map((s) => (
          <div key={s.step} style={{ ...ui.card, display: "flex", gap: "1.25rem", alignItems: "flex-start" }}>
            <div
              style={{
                flexShrink: 0,
                width: 36,
                height: 36,
                borderRadius: "50%",
                background: "var(--color-accent)",
                color: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 700,
              }}
            >
              {s.step}
            </div>
            <div>
              <h2 style={{ fontSize: "1.05rem", margin: 0 }}>{s.title}</h2>
              <p style={{ fontSize: 14, color: "var(--color-muted)", margin: "0.3rem 0 0", lineHeight: 1.6 }}>
                {s.body}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: "2rem", display: "flex", gap: "0.75rem" }}>
        <Link href="/catalog" style={{ ...ui.button, textDecoration: "none", display: "inline-block" }}>
          Browse the catalog
        </Link>
        <Link href="/register" style={{ ...ui.buttonSecondary, textDecoration: "none", display: "inline-block" }}>
          Register your organization
        </Link>
      </div>
    </main>
  );
}
