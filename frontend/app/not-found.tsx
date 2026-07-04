import Link from "next/link";
import { ui } from "@/lib/ui";

export default function NotFound() {
  return (
    <main style={{ ...ui.page, textAlign: "center", paddingTop: "5rem" }}>
      <p style={{ letterSpacing: "0.2em", fontSize: 12, color: "var(--color-accent)", textTransform: "uppercase" }}>
        404
      </p>
      <h1 style={{ fontSize: "2rem", margin: "0.5rem 0" }}>Page not found</h1>
      <p style={{ color: "var(--color-muted)", marginBottom: "1.5rem" }}>
        The page you&apos;re looking for doesn&apos;t exist or has moved.
      </p>
      <Link href="/" style={{ ...ui.button, textDecoration: "none", display: "inline-block" }}>
        Back to home
      </Link>
    </main>
  );
}
