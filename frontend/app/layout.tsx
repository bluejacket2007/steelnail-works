import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: {
    default: "SteelNail Works — Bulk Steel Nail Manufacturing",
    template: "%s · SteelNail Works",
  },
  description:
    "Enterprise B2B marketplace for bulk steel nail procurement — tiered volume pricing, AI-assisted negotiation, and 30/70 milestone payment contracts.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
