"""Proforma invoice PDF generation (triggered from webhook workers)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.models.models import Order, OrderMilestone

INVOICE_DIR = Path("var/invoices")


def generate_proforma_invoice(order: Order, milestone: OrderMilestone) -> Path:
    """Render a proforma invoice PDF for a settled milestone.

    Uses ReportLab when available; the file lands in var/invoices/ and its
    path is recorded by the webhook worker. Falls back to a plaintext stub
    so the pipeline never hard-fails on a rendering dependency.
    """
    INVOICE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    pdf_path = INVOICE_DIR / f"proforma_{order.id}_{milestone.milestone_type.value}_{stamp}.pdf"

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError:
        fallback = pdf_path.with_suffix(".txt")
        fallback.write_text(
            f"PROFORMA INVOICE\nOrder: {order.id}\n"
            f"Milestone: {milestone.milestone_type.value} ({milestone.percentage}%)\n"
            f"Amount: {milestone.amount} {order.currency}\n",
            encoding="utf-8",
        )
        return fallback

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4
    y = height - 30 * mm

    c.setFont("Helvetica-Bold", 18)
    c.drawString(25 * mm, y, "PROFORMA INVOICE")
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 25 * mm, y, datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"))

    y -= 12 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(25 * mm, y, "Steel Nail Manufacturing Co.")
    c.setFont("Helvetica", 9)
    y -= 5 * mm
    c.drawString(25 * mm, y, "Industrial B2B Marketplace — Milestone Settlement Record")

    y -= 15 * mm
    rows = [
        ("Order ID", order.id),
        ("Buyer Organization", order.buyer_org.legal_name if order.buyer_org else order.buyer_org_id),
        ("Milestone", f"{milestone.milestone_type.value} ({milestone.percentage}% of contract)"),
        ("Amount Settled", f"{milestone.amount} {order.currency}"),
        ("Contract Total", f"{order.total_amount} {order.currency}"),
        ("Provider Reference", f"{milestone.provider.value if milestone.provider else '-'} / {milestone.provider_payment_id or '-'}"),
        ("Order Status", order.status.value),
    ]
    for label, value in rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(25 * mm, y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(80 * mm, y, str(value))
        y -= 8 * mm

    y -= 10 * mm
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(
        25 * mm, y,
        "This proforma invoice is generated automatically upon cryptographically "
        "verified payment confirmation.",
    )

    c.showPage()
    c.save()
    return pdf_path
