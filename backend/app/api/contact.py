"""Public marketing-site contact form.

The POST endpoint is intentionally unauthenticated (a prospective buyer
browsing the catalog has no account yet) but still passes through the
global XSS sanitizer and the anonymous-tier Redis rate limiter like every
other route, so it carries the same hardening as authenticated endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rbac import require_roles
from app.models.models import ContactInquiry, Role, User
from app.schemas.schemas import ContactInquiryCreate, ContactInquiryOut

router = APIRouter(prefix="/api/v1/contact", tags=["contact"])


@router.post("", response_model=ContactInquiryOut, status_code=201)
def submit_inquiry(payload: ContactInquiryCreate, db: Session = Depends(get_db)):
    inquiry = ContactInquiry(**payload.model_dump())
    db.add(inquiry)
    db.commit()
    return inquiry


@router.get("", response_model=list[ContactInquiryOut])
def list_inquiries(
    user: User = Depends(require_roles(Role.SALES_REP, Role.SALES_MANAGER)),
    db: Session = Depends(get_db),
):
    return db.execute(
        select(ContactInquiry).order_by(ContactInquiry.handled, ContactInquiry.created_at.desc())
    ).scalars().all()


@router.post("/{inquiry_id}/handled", response_model=ContactInquiryOut)
def mark_handled(
    inquiry_id: str,
    user: User = Depends(require_roles(Role.SALES_REP, Role.SALES_MANAGER)),
    db: Session = Depends(get_db),
):
    inquiry = db.get(ContactInquiry, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    inquiry.handled = True
    inquiry.handled_by = user.id
    db.commit()
    return inquiry
