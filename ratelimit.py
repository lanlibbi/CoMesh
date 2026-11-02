"""
Rate limiting + login brute-force protection.

Design
------
Process-local token buckets with a threading lock. The portal runs a single
uvicorn worker by policy (see the single-worker note in docker-compose.yml:
the WS registry is process-local too), so an in-process limiter is exact for
this deployment. It is deliberately *not* a distributed limiter — if Phase 3
moves to multiple workers/Redis, swap `Bucket.consume` for a Redis INCR/EXPIRE.

Buckets are keyed by scope:

  chat:user:<id>          /v1/chat/completions per authenticated user
  chat:ip:<ip>            /v1/chat/completions per client IP (unauthenticated abuse)
  login:ip:<ip>           /auth/login attempts per IP
  login:email:<email>     /auth/login attempts per account (brute force)
  register:ip:<ip>        /auth/register per IP (signup abuse)
  node:<id>               node-authenticated endpoints per node (heartbeat etc.)
  admin:ip:<ip>           /admin/* per IP

Two mechanisms:

  * `limit()` / `rate_limit(...)` — token bucket, returns 429 + Retry-After.
  * `LoginGuard` — failure-based exponential backoff with lockout, used at
    /auth/login. A locked account is refused (429) even with the right
    password, until the lock expires.

Environment:
  RATE_LIMITS_DISABLED=1        disable all limiting (tests/benchmarks only)
  RATE_LIMIT_CHAT_PER_MIN       default 60     per user, sustained
  RATE_LIMIT_CHAT_BURST         default 20     per user, burst
  RATE_LIMIT_CHAT_IP_PER_MIN    default 120    per client IP
  RATE_LIMIT_CHAT_IP_BURST      default 40
  RATE_LIMIT_LOGIN_PER_MIN      default 10     per IP / per account
  RATE_LIMIT_LOGIN_BURST        default 5
  RATE_LIMIT_REGISTER_PER_MIN   default 30     per IP
  RATE_LIMIT_REGISTER_BURST     default 10
  RATE_LIMIT_NODE_PER_MIN       default 240    per node (heartbeat cadence is 30s)
  RATE_LIMIT_NODE_BURST         default 60
  RATE_LIMIT_ADMIN_PER_MIN      default 30
  RATE_LIMIT_ADMIN_BURST        default 5
  LOGIN_MAX_FAILURES            default 5      failures before lockout
  LOGIN_FAILURE_WINDOW_SECONDS  default 900    counting window
  LOGIN_LOCK_SECONDS            default 300    base lockout, doubles per extra failure
  LOGIN_LOCK_MAX_SECONDS        default 3600   lockout ceiling
  TRUST_PROXY_HEADERS           default 0      set to 1 behind the compose nginx
  TRUSTED_PROXY_NETS            default 172.16.0.0/12,10.0.0.0/8,127.0.0.1/32
"""
import ipaddress
import logging
import math
import os
import threading
import time
from typing import Callable, Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

log = logging.getLogger("gpu-pool.ratelimit")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default) or default)
    except (TypeError, ValueError):
        return default


def disabled() -> bool:
    return (os.environ.get("RATE_LIMITS_DISABLED", "0") or "0") not in ("0", "", "false", "False")


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------
class Bucket:
    """Token bucket. `capacity` = burst size, `refill` = tokens per second."""

    __slots__ = ("capacity", "refill", "tokens", "updated")

    def __init__(self, capacity: float, refill: float):
        self.capacity = max(1.0, float(capacity))
        self.refill = max(0.0001, float(refill))
        self.tokens = self.capacity
        self.updated = time.monotonic()

    def consume(self, n: float = 1.0) -> Tuple[bool, float]:
        """Try to take `n` tokens. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        elapsed = now - self.updated
        self.updated = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill)
        if self.tokens >= n:
            self.tokens -= n
            return True, 0.0
        missing = n - self.tokens
        return False, missing / self.refill


class RateLimiter:
    """Registry of named buckets, keyed by scope string."""

    def __init__(self, idle_ttl_seconds: float = 900.0):
        self._lock = threading.Lock()
        self._buckets: Dict[str, Bucket] = {}
        self._idle_ttl = idle_ttl_seconds

    def check(self, scope: str, *, per_minute: int, burst: int, cost: float = 1.0) -> Tuple[bool, float]:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(scope)
            if bucket is None or (now - bucket.updated) > self._idle_ttl:
                bucket = Bucket(capacity=burst, refill=per_minute / 60.0)
                self._buckets[scope] = bucket
                if len(self._buckets) > 20000:  # bound memory on hostile traffic
                    self._prune_locked(now)
            return bucket.consume(cost)

    def _prune_locked(self, now: float) -> None:
        stale = [k for k, b in self._buckets.items() if (now - b.updated) > self._idle_ttl]
        for k in stale:
            self._buckets.pop(k, None)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def bucket_count(self) -> int:
        with self._lock:
            return len(self._buckets)


LIMITER = RateLimiter()


def _trust_proxy_headers() -> bool:
    return (os.environ.get("TRUST_PROXY_HEADERS", "0") or "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


DEFAULT_TRUSTED_PROXY_NETS = "172.16.0.0/12,10.0.0.0/8,127.0.0.1/32"


def _trusted_proxy_networks():
    raw = os.environ.get("TRUSTED_PROXY_NETS", DEFAULT_TRUSTED_PROXY_NETS) or ""
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            log.warning("TRUSTED_PROXY_NETS: ignoring invalid entry %r", part)
    return tuple(nets)


def _is_trusted_proxy(peer: str) -> bool:
    """True when *peer* (the TCP peer, not a header) may speak for the client."""
    if not peer:
        return False
    try:
        addr = ipaddress.ip_address(peer.strip().strip("[]"))
    except ValueError:
        return False
    return any(addr in net for net in _trusted_proxy_networks())


def client_ip(request: Request) -> str:
    """
    Best-effort client identity for rate limiting.

    Without a proxy the socket address is the truth. Behind the bundled nginx
    (compose service ``frontend``) it is *always* the nginx container's address
    — then all users share one bucket and five failed logins lock everybody out.

    With ``TRUST_PROXY_HEADERS=1`` the header nginx sets itself is used instead:
    ``X-Real-IP``, which nginx overwrites with ``$remote_addr`` after its
    ``real_ip`` module resolved ``CF-Connecting-IP``. This only happens when the
    TCP peer really is a trusted proxy (``TRUSTED_PROXY_NETS``); otherwise
    anyone reaching the API directly on 8765 could forge the header.
    ``X-Forwarded-For`` is deliberately not preferred: as a list, its first
    element is traditionally client-controlled.
    """
    peer = request.client.host if request.client else "unknown"
    if _trust_proxy_headers() and _is_trusted_proxy(peer):
        real = (request.headers.get("x-real-ip") or "").strip()
        if real:
            return real
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return peer


def enforce(scope: str, *, per_minute: int, burst: int, cost: float = 1.0) -> None:
    """Raise 429 (with Retry-After) when the scope's bucket is exhausted."""
    if disabled():
        return
    allowed, retry_after = LIMITER.check(scope, per_minute=per_minute, burst=burst, cost=cost)
    if allowed:
        return
    wait = max(1, int(math.ceil(retry_after)))
    log.warning("rate limit hit: scope=%s retry_after=%ss", scope, wait)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Rate limit exceeded for this endpoint. Retry in {wait}s.",
        headers={"Retry-After": str(wait)},
    )


# ---------------------------------------------------------------------------
# Named limiters (env-driven, read per call so tests can retune at runtime)
# ---------------------------------------------------------------------------
def limit_chat(user_id: Optional[int], ip: str) -> None:
    if user_id is not None:
        enforce(
            f"chat:user:{user_id}",
            per_minute=_env_int("RATE_LIMIT_CHAT_PER_MIN", 60),
            burst=_env_int("RATE_LIMIT_CHAT_BURST", 20),
        )
    enforce(
        f"chat:ip:{ip}",
        per_minute=_env_int("RATE_LIMIT_CHAT_IP_PER_MIN", 120),
        burst=_env_int("RATE_LIMIT_CHAT_IP_BURST", 40),
    )


def limit_login(ip: str, email: str) -> None:
    enforce(
        f"login:ip:{ip}",
        per_minute=_env_int("RATE_LIMIT_LOGIN_PER_MIN", 10),
        burst=_env_int("RATE_LIMIT_LOGIN_BURST", 5),
    )
    enforce(
        f"login:email:{(email or '').lower()}",
        per_minute=_env_int("RATE_LIMIT_LOGIN_PER_MIN", 10),
        burst=_env_int("RATE_LIMIT_LOGIN_BURST", 5),
    )


def limit_register(ip: str) -> None:
    enforce(
        f"register:ip:{ip}",
        per_minute=_env_int("RATE_LIMIT_REGISTER_PER_MIN", 30),
        burst=_env_int("RATE_LIMIT_REGISTER_BURST", 10),
    )


def limit_node(node_id: int) -> None:
    enforce(
        f"node:{node_id}",
        per_minute=_env_int("RATE_LIMIT_NODE_PER_MIN", 240),
        burst=_env_int("RATE_LIMIT_NODE_BURST", 60),
    )


def limit_admin(ip: str) -> None:
    enforce(
        f"admin:ip:{ip}",
        per_minute=_env_int("RATE_LIMIT_ADMIN_PER_MIN", 30),
        burst=_env_int("RATE_LIMIT_ADMIN_BURST", 5),
    )


# ---------------------------------------------------------------------------
# Login brute-force guard (failure-based exponential backoff)
# ---------------------------------------------------------------------------
class LoginGuard:
    """
    Tracks failed logins per account and per IP.

    After `LOGIN_MAX_FAILURES` failures inside `LOGIN_FAILURE_WINDOW_SECONDS`
    the key is locked for `LOGIN_LOCK_SECONDS`, doubling with every further
    failure up to `LOGIN_LOCK_MAX_SECONDS`. A successful login clears the key.

    State is in-process (single-worker deployment, documented above): a portal
    restart resets counters. Failures are always logged for the audit trail.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # key -> [failure_count, first_failure_ts, locked_until]
        self._state: Dict[str, list] = {}

    def _config(self) -> Tuple[int, float, float, float]:
        return (
            _env_int("LOGIN_MAX_FAILURES", 5),
            float(_env_int("LOGIN_FAILURE_WINDOW_SECONDS", 900)),
            float(_env_int("LOGIN_LOCK_SECONDS", 300)),
            float(_env_int("LOGIN_LOCK_MAX_SECONDS", 3600)),
        )

    def locked_for(self, key: str) -> float:
        """Seconds the key stays locked (0 = not locked)."""
        if disabled():
            return 0.0
        now = time.monotonic()
        with self._lock:
            entry = self._state.get(key)
            if not entry:
                return 0.0
            locked_until = entry[2]
            if locked_until and locked_until > now:
                return locked_until - now
            return 0.0

    def check(self, *keys: str) -> None:
        """Raise 429 if any of the given keys is locked."""
        for key in keys:
            remaining = self.locked_for(key)
            if remaining > 0:
                wait = max(1, int(math.ceil(remaining)))
                log.warning("login blocked by lockout: key=%s retry_after=%ss", key, wait)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "Too many failed login attempts. This account/IP is temporarily locked. "
                        f"Retry in {wait}s."
                    ),
                    headers={"Retry-After": str(wait)},
                )

    def record_failure(self, *keys: str) -> None:
        if disabled():
            return
        max_failures, window, base_lock, max_lock = self._config()
        now = time.monotonic()
        with self._lock:
            for key in keys:
                entry = self._state.get(key) or [0, now, 0.0]
                if now - entry[1] > window:
                    entry = [0, now, 0.0]  # window expired -> start over
                entry[0] += 1
                if entry[0] >= max_failures:
                    extra = entry[0] - max_failures
                    lock = min(base_lock * (2 ** extra), max_lock)
                    entry[2] = now + lock
                self._state[key] = entry

    def record_success(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._state.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._state.clear()


LOGIN_GUARD = LoginGuard()


def login_keys(ip: str, email: str) -> Tuple[str, str]:
    return f"login:ip:{ip}", f"login:email:{(email or '').lower()}"


def login_limit() -> Callable:  # backwards-compatible alias for future use
    return limit_login
