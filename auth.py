"""
API-Key authentication.

Keys are stored hashed in the DB (key_hash column). The raw key is only
shown to the user once at creation time. Subsequent requests send the key
in the Authorization header: "Bearer gpu_xxx..."
"""
import hashlib
import secrets
from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import ApiKey, User


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash of the raw API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key. Returns (raw_key, key_hash, key_prefix).
    raw_key is the only time the un-hashed key is shown.
    """
    raw = f"gpu_{secrets.token_urlsafe(32)}"
    return raw, hash_api_key(raw), raw[:12]


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency that extracts and validates the API key,
    returns the owning User. Updates last_used_at on success.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Use: Authorization: Bearer <api_key>",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header. Expected: Bearer <api_key>",
        )

    raw_key = parts[1]
    key_hash = hash_api_key(raw_key)

    api_key = db.query(ApiKey).filter(
        ApiKey.key_hash == key_hash,
        ApiKey.is_active == True,
    ).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key.",
        )

    user = db.query(User).filter(
        User.id == api_key.user_id,
        User.is_active == True,
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )
    if getattr(user, "registration_status", "approved") != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration pending manual approval.",
        )

    api_key.last_used_at = datetime.utcnow()
    db.commit()
    return user
