"""
Admin authorization helper.

Admin endpoints are gated behind a real role check: the caller must present a
valid API key whose owning user has `role == "admin"`. This replaces the
POC-era convention where every `/admin/*` route was unauthenticated
(see POC-REPORT.md, caveat #1).

Role model:
  * self-service roles (what a user may set for themselves):
      provider | consumer | both
  * privileged role (only settable by an existing admin through
      PATCH /admin/users/{id}):
      admin

A user can never promote themselves to admin: PUT /v1/me/role accepts
SELF_SERVICE_ROLES only.
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import ADMIN_ROLE, User


def require_admin(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: the caller must be an active user with role 'admin'."""
    if (getattr(user, "role", "") or "").lower() != ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Admin role required. Your account role is "
                f"'{getattr(user, 'role', None)}' — admin endpoints are restricted "
                "to users with role 'admin'."
            ),
        )
    return user
