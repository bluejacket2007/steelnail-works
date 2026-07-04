"""Role-Based Access Control.

``get_current_user`` resolves the Bearer access token into a live User row.
``require_roles(...)`` is the dependency factory used as a decorator-style
guard on every protected route:

    @router.post("/quotes/{id}/approve",
                 dependencies=[Depends(require_roles(Role.SALES_MANAGER))])
"""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    from app.core.security import decode_token  # local import avoids cycles

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_token(token, expected_type="access")
    except jwt.InvalidTokenError:
        raise credentials_error

    user = db.get(User, claims["sub"])
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_roles(*roles: Role):
    """Dependency factory enforcing that the caller holds one of ``roles``.

    SuperAdmin implicitly passes every check.
    """

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role == Role.SUPER_ADMIN or user.role in roles:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires one of roles: {[r.value for r in roles]}",
        )

    return checker
