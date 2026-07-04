"""OAuth2 authentication endpoints.

- 15-minute stateless JWT access tokens returned in the response body.
- 7-day refresh tokens delivered ONLY as HttpOnly / SameSite=Strict / Secure
  cookies, rotated on every refresh and revocable server-side.
"""
from __future__ import annotations

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.rbac import get_current_user
from app.core.security import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    revoke_refresh_token,
    set_refresh_cookie,
    verify_password,
)
from app.models.models import Organization, Role, User
from app.schemas.schemas import MeResponse, RegisterRequest, TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=MeResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Self-service buyer onboarding — creates the org + procurement user."""
    exists = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")

    org = Organization(
        legal_name=payload.organization_name,
        gstin=payload.gstin,
        ein=payload.ein,
    )
    db.add(org)
    db.flush()

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=Role.CLIENT_PROCUREMENT,
        org_id=org.id,
    )
    db.add(user)
    db.commit()
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.execute(select(User).where(User.email == form.username)).scalar_one_or_none()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    set_refresh_cookie(response, create_refresh_token(user.id))
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value, user.org_id),
        expires_in_seconds=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        claims = decode_token(token, expected_type="refresh")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

    user = db.get(User, claims["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account unavailable")

    # Rotation: the presented refresh token is burned; a fresh one is issued.
    revoke_refresh_token(token)
    set_refresh_cookie(response, create_refresh_token(user.id))
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value, user.org_id),
        expires_in_seconds=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token:
        revoke_refresh_token(token)
    clear_refresh_cookie(response)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    return user
