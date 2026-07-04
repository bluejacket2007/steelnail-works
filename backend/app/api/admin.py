"""Organization administration — credit ratings and directory lookups.

Credit rating directly controls how much discount the AI negotiation agent
is permitted to extend (see agent/tools.py::_CREDIT_DISCOUNT_CAP), so writes
are restricted to SalesManager/SuperAdmin.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rbac import get_current_user, require_roles
from app.models.models import Organization, Role, User
from app.schemas.schemas import CreditRatingUpdate, OrganizationOut

router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])


@router.get("", response_model=list[OrganizationOut])
def list_organizations(
    user: User = Depends(require_roles(Role.SALES_MANAGER, Role.SALES_REP)),
    db: Session = Depends(get_db),
):
    return db.execute(select(Organization).order_by(Organization.legal_name)).scalars().all()


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(
    org_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == Role.CLIENT_PROCUREMENT and user.org_id != org_id:
        raise HTTPException(status_code=403, detail="Not your organization")
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.patch("/{org_id}/credit", response_model=OrganizationOut)
def update_credit_rating(
    org_id: str,
    payload: CreditRatingUpdate,
    user: User = Depends(require_roles(Role.SALES_MANAGER)),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.credit_rating = payload.credit_rating
    org.credit_limit = payload.credit_limit
    db.commit()
    return org
