"""
Authentication & token handling (hardened).

Two credential types are accepted, both as opaque bearer tokens:

  * API keys       "gpu_..."  long-lived, issued at register / login
  * session tokens "sess_..." short-lived (TTL configurable), revocable

Storage: only the SHA-256 hash of a token is persisted (`api_keys.key_hash`).
Verification is a hash lookup plus a constant-time comparison, so no plaintext
token is ever at rest. `last_used_at` gives an audit trail; `expires_at` gives
a hard expiry; `is_active` gives revocation.

Passwords: PBKDF2-HMAC-SHA256, per-user random salt, >= 240k iterations.
Legacy unsalted SHA-256 hashes from the POC are still accepted once and are
transparently upgraded to PBKDF2 on the next successful login (no forced
password reset, no breaking change for existing users).

Design note - why opaque tokens instead of JWT:
  The portal is consumed by OpenAI-compatible clients that put the credential
  in `Authorization: Bearer <token>`. A DB-backed opaque token gives the same
  client contract *plus* revocation, expiry and audit. A JWT would add a
  second signing secret to rotate and buys statelessness that a single uvicorn
  worker (see the single-worker policy in docker-compose.yml) does not need.

Environment:
  API_KEY_TTL_DAYS          default 0    (0 = API keys do not expire)
  SESSION_TOKEN_TTL_HOURS   default 24   (TTL of tokens issued by /auth/login)
  AUTH_PBKDF2_ITERATIONS    default 240000
  ADMIN_TOKEN               optional     static operator token for /admin/*
  ADMIN_EMAILS              optional     comma-separated admin account emails
  ADMIN_AUTH_DISABLED       default 0    (POC escape hatch: 1 disables admin auth)
"""
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import ApiKey, User

log = logging.getLogger("gpu-pool.auth")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_KEY_TTL_DAYS = int(os.environ.get("API_KEY_TTL_DAYS", "0") or 0)
SESSION_TOKEN_TTL_HOURS = float(os.environ.get("SESSION_TOKEN_TTL_HOURS", "24") or 24)
PBKDF2_ITERATIONS = int(os.environ.get("AUTH_PBKDF2_ITERATIONS", "240000") or 240000)
ADMIN_EMAILS = [e.strip().lower() for e in (os.environ.get("ADMIN_EMAILS") or "").split(",") if e.strip()]
ADMIN_AUTH_DISABLED = (os.environ.get("ADMIN_AUTH_DISABLED", "0") or "0") not in ("0", "", "false", "False")

PASSWORD_SCHEME = "pbkdf2_sha256"
LEGACY_SHA256_LEN = 64  # length of a hex sha256 digest = legacy POC format


def _env_admin_token() -> Optional[str]:
    """Read the static operator token lazily so tests can set it at runtime."""
    val = os.environ.get("ADMIN_TOKEN")
    return val if val else None


def _truthy(name: str, default: str = "0") -> bool:
    return (os.environ.get(name, default) or default) not in ("0", "", "false", "False")


# ---------------------------------------------------------------------------
# API keys / session tokens
# ---------------------------------------------------------------------------
def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash of a raw token. Only this value is persisted."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> Tuple[str, str, str]:
    """
    Generate a new API key. Returns (raw_key, key_hash, key_prefix).
    raw_key is the only time the un-hashed key is shown.
    """
    raw = f"gpu_{secrets.token_urlsafe(32)}"
    return raw, hash_api_key(raw), raw[:12]


def generate_session_token() -> Tuple[str, str, str]:
    """Generate a short-lived session token (issued by /auth/login)."""
    raw = f"sess_{secrets.token_urlsafe(32)}"
    return raw, hash_api_key(raw), raw[:13]


def _api_key_expiry(ttl_days: int) -> Optional[datetime]:
    if ttl_days and ttl_days > 0:
        return datetime.utcnow() + timedelta(days=ttl_days)
    return None


def issue_token(
    db: Session,
    user: User,
    *,
    token_type: str = "api_key",
    ttl_hours: float = 0.0,
    ttl_days: int = 0,
    label: Optional[str] = None,
    rotate: bool = False,
) -> Tuple[str, str, str]:
    """
    Create an ApiKey row for `user` and return (raw, key_hash, key_prefix).

    `rotate=True` deactivates the user's other tokens of the same type first
    (the old POC behaviour for login). `ttl_hours` / `ttl_days` set `expires_at`.
    """
    if token_type == "session":
        raw, key_hash, key_prefix = generate_session_token()
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours) if ttl_hours and ttl_hours > 0 else None
    else:
        raw, key_hash, key_prefix = generate_api_key()
        expires_at = _api_key_expiry(ttl_days)

    if rotate:
        for k in db.query(ApiKey).filter(
            ApiKey.user_id == user.id,
            ApiKey.is_active == True,  # noqa: E712 (SQLAlchemy comparison)
            ApiKey.token_type == token_type,
        ).all():
            k.is_active = False

    db.add(ApiKey(
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        label=label,
        token_type=token_type,
        expires_at=expires_at,
        is_active=True,
    ))
    return raw, key_hash, key_prefix


def generate_node_key() -> Tuple[str, str, str]:
    """Generate a node-agent key. Returns (raw, hash, prefix)."""
    raw = f"node_{secrets.token_urlsafe(24)}"
    return raw, hash_api_key(raw), raw[:13]


def verify_node_key(raw_key: str, stored_hash: Optional[str], legacy_plain: Optional[str] = None) -> bool:
    """
    Verify a node-agent key against its stored SHA-256 hash.

    Falls back to a constant-time compare against the legacy plaintext column
    (pre-hardening rows) so existing agents are not locked out; the caller is
    expected to migrate the row to the hashed form.
    """
    if not raw_key:
        return False
    if stored_hash:
        return hmac.compare_digest(hash_api_key(raw_key), stored_hash)
    if legacy_plain:
        return hmac.compare_digest(raw_key, legacy_plain)
    return False


def revoke_tokens(db: Session, user: User, token_type: Optional[str] = None) -> int:
    """Deactivate the user's tokens. Returns the number revoked."""
    q = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.is_active == True)  # noqa: E712
    if token_type:
        q = q.filter(ApiKey.token_type == token_type)
    rows = q.all()
    for k in rows:
        k.is_active = False
    return len(rows)


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    import base64
    return base64.b64decode(text.encode("ascii"))


def hash_password(pw: str, iterations: Optional[int] = None) -> str:
    """PBKDF2-HMAC-SHA256 hash: pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>."""
    iters = int(iterations or PBKDF2_ITERATIONS)
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iters)
    return f"{PASSWORD_SCHEME}${iters}${_b64(salt)}${_b64(dk)}"


def verify_password(pw: str, stored: Optional[str]) -> Tuple[bool, bool]:
    """
    Verify a password against a stored hash.

    Returns (ok, needs_upgrade). `needs_upgrade` is True when the stored hash
    uses the legacy POC scheme and should be re-hashed with PBKDF2.
    Never raises; a malformed stored hash is treated as a failed login.
    """
    if not stored:
        return False, False
    if stored.startswith(PASSWORD_SCHEME + "$"):
        try:
            _, iters_s, salt_s, hash_s = stored.split("$", 3)
            dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), _unb64(salt_s), int(iters_s))
            ok = hmac.compare_digest(_b64(dk), hash_s)
            return ok, bool(ok and int(iters_s) < PBKDF2_ITERATIONS)
        except Exception:
            return False, False
    # Legacy: unsalted sha256 hex digest (POC). Accept once, then upgrade.
    if len(stored) == LEGACY_SHA256_LEN:
        try:
            legacy = hashlib.sha256(pw.encode("utf-8")).hexdigest()
            ok = hmac.compare_digest(legacy, stored)
            return ok, bool(ok)
        except Exception:
            return False, False
    return False, False


def verify_password_dummy(pw: str) -> None:
    """
    Burn the same amount of CPU as a real verification.

    Called when the account does not exist so that response timing does not
    reveal whether an email is registered (user-enumeration defence).
    """
    hashlib.pbkdf2_hmac("sha256", (pw or "").encode("utf-8"), b"gpu-pool-dummy-salt", max(1, PBKDF2_ITERATIONS))


def upgrade_password_if_needed(db: Session, user: User, plain_pw: str, needs_upgrade: bool) -> bool:
    """Re-hash a legacy password hash with PBKDF2. Returns True if changed."""
    if not needs_upgrade:
        return False
    user.password_hash = hash_password(plain_pw)
    log.info("Upgraded password hash to %s for user %s", PASSWORD_SCHEME, user.id)
    return True


# ---------------------------------------------------------------------------
# Bearer-token resolution
# ---------------------------------------------------------------------------
def parse_bearer_header(authorization: Optional[str]) -> str:
    """Parse an `Authorization: Bearer <token>` header into the raw token.

    Raises 401 when the header is missing or malformed. Exposed publicly so
    routers that accept *optional* authentication (e.g. GET /nodes/{id}) can
    parse a header without raising on absence.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Use: Authorization: Bearer <api_key>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header. Expected: Bearer <api_key>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1].strip()


def resolve_token(db: Session, raw_token: str, *, touch: bool = True) -> Tuple[ApiKey, User]:
    """
    Resolve a raw token to (ApiKey, User). Raises 401 on any failure.

    Expiry and revocation are enforced here, so an expired or revoked token
    can never reach a handler.
    """
    key_hash = hash_api_key(raw_token)
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    # Constant-time sanity check on the stored hash (defence in depth: the DB
    # lookup already matched, but this keeps the compare path uniform).
    if not api_key or not hmac.compare_digest(api_key.key_hash, key_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is revoked or inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if api_key.expires_at is not None and api_key.expires_at <= datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.id == api_key.user_id).first()
    if user and getattr(user, "registration_status", "approved") != "approved":
        # Ein Konto in der Warteschlange darf auch mit einem ausgestellten Schlüssel nicht
        # arbeiten — sonst umgeht die Registrierung die Freigabe auf dem API-Weg.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration pending manual approval.",
        )
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if touch:
        api_key.last_used_at = datetime.utcnow()
        db.commit()
    return api_key, user


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency that extracts and validates the bearer token and
    returns the owning User. Updates last_used_at on success.
    """
    raw_token = parse_bearer_header(authorization)
    _api_key, user = resolve_token(db, raw_token)
    return user


def is_admin(user: User) -> bool:
    """True if the user is an admin account (ADMIN_EMAILS) or has role 'admin'."""
    if getattr(user, "role", None) == "admin":
        return True
    return (user.email or "").lower() in ADMIN_EMAILS


async def require_admin(
    authorization: Optional[str] = Header(default=None),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    FastAPI dependency for /admin/* endpoints.

    Accepts either:
      * the static operator token from ADMIN_TOKEN, presented either as
        `Authorization: Bearer <token>` or as `X-Admin-Token: <token>`, or
      * a bearer token of an admin account (ADMIN_EMAILS / role=admin).

    Default-deny: with neither ADMIN_TOKEN nor ADMIN_EMAILS configured every
    admin call is rejected, so an unconfigured deployment cannot be driven
    anonymously. ADMIN_AUTH_DISABLED=1 is the explicit POC escape hatch.
    """
    if _truthy("ADMIN_AUTH_DISABLED"):
        log.warning("ADMIN_AUTH_DISABLED=1 - /admin/* is unauthenticated (POC mode)")
        return None

    operator_token = _env_admin_token()
    presented = None
    if authorization:
        parts = authorization.split()
        presented = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else None

    # Static operator token: accepted from either header.
    if operator_token:
        if presented and hmac.compare_digest(presented, operator_token):
            return None  # authenticated as operator, no user context
        if x_admin_token and hmac.compare_digest(x_admin_token, operator_token):
            return None

    if not presented:
        # Default-deny only for callers presenting no admin identity at all (LANA-140):
        # a presented bearer is resolved and checked via is_admin() regardless of
        # ADMIN_TOKEN/ADMIN_EMAILS configuration.
        if not operator_token and not ADMIN_EMAILS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Admin API is not configured. Set ADMIN_TOKEN (and/or ADMIN_EMAILS) "
                    "on the portal, or ADMIN_AUTH_DISABLED=1 for a throwaway POC instance."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Admin authentication required. Use: Authorization: Bearer <admin token> "
                "or X-Admin-Token: <admin token>."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    _api_key, user = resolve_token(db, presented)
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required.")
    return user
