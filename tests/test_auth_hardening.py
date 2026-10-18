"""
GPU-Pool auth-hardening tests (token handling, rate limiting, brute force).

Run against an in-process server with a throwaway SQLite DB:

    python3 tests/test_auth_hardening.py

Or against a live portal (uses the configured ADMIN_TOKEN):

    GPU_POOL_API=http://localhost:8765 ADMIN_TOKEN=... python3 tests/test_auth_hardening.py

Covered:
   1. Password storage: PBKDF2 with salt, legacy sha256 hash upgraded on login
   2. Session tokens: issued by login, TTL set, rotated on re-login
   3. Token expiry is enforced (401 after expiry)
   4. Explicit revocation (POST /auth/logout)
   5. Failed logins are counted; the account locks with exponential backoff
      and a locked account is refused even with the correct password
   6. Rate limits: 429 + Retry-After on node endpoints and on chat completions
   7. Admin endpoints are closed by default and accept ADMIN_TOKEN when set
   8. Node-agent keys are stored hashed; rotation invalidates the old key
   9. Public node listings do not leak contributor-private fields
  10. /pool/jobs is scoped to the caller instead of exposing all users' jobs
  11. Register enforces a minimum password length

Exits with code 0 on success, 1 on failure.
"""
import asyncio
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _testutil import ADMIN_HEADERS, TEST_ADMIN_TOKEN, start_test_server, stop_test_server  # noqa: E402

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []


def check(name, cond, detail=""):
    tag = PASS if cond else FAIL
    print(f"  {tag} {name}{(' — ' + detail) if detail else ''}")
    results.append(bool(cond))
    return cond


# ---------------------------------------------------------------------------
# Live (out-of-process) client
# ---------------------------------------------------------------------------
class LiveAPI:
    """Async JSON client.

    Must be async: in in-process mode the test client and the uvicorn server
    share one event loop, so a blocking urllib call would deadlock the server
    (the request would time out with no response).
    """

    def __init__(self, base):
        import httpx
        self.base = base.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base, timeout=30.0,
                                         follow_redirects=False)

    async def request(self, method, path, body=None, token=None, headers=None):
        hdrs = dict(headers or {})
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        hdrs.setdefault("Content-Type", "application/json")
        r = await self._client.request(method, path, json=body, headers=hdrs)
        try:
            payload = r.json()
        except Exception:
            payload = r.text
        return r.status_code, payload, dict(r.headers)

    async def aclose(self):
        await self._client.aclose()


def header(headers, name: str):
    """Case-insensitive header lookup (uvicorn lowercases header names)."""
    for k, v in (headers or {}).items():
        if k.lower() == name.lower():
            return v
    return None


def reset_limits(env):
    """Clear rate-limit buckets and login lockouts between test groups."""
    try:
        rl = env.mod("ratelimit")
        rl.LIMITER.reset()
        rl.LOGIN_GUARD.reset()
    except (KeyError, AttributeError):
        pass


def fresh_email(tag: str) -> str:
    return f"auth-{tag}-{int(time.time())}-{secrets.token_hex(3)}@example.com"


async def register(api, tag, *, password="test123456", role="both"):
    """Public signup. Returns (status, body, headers). Email is in body["email"]."""
    return await api.request("POST", "/auth/register", {
        "email": fresh_email(tag), "name": f"Auth {tag}", "password": password,
        "role": role, "initial_credits": 100,
    })


async def login(api, email, password):
    return await api.request("POST", "/auth/login", {"email": email, "password": password})


# ---------------------------------------------------------------------------
# Test 1: password storage
# ---------------------------------------------------------------------------
async def test_password_storage(api, env):
    print("\nTest 1: password storage (PBKDF2 + legacy upgrade)")
    st, body, _h = await register(api, "pw")
    email = (body or {}).get("email")
    check("register -> 200", st == 200, f"got {st}: {str(body)[:120]}")
    if st != 200:
        return

    db, models = env.mod("database"), env.mod("models")
    s = db.SessionLocal()
    try:
        user = s.query(models.User).filter(models.User.email == email).first()
        stored = user.password_hash or ""
        check("hash uses pbkdf2_sha256 scheme", stored.startswith("pbkdf2_sha256$"), stored[:30])
        check("hash carries >= 240k iterations",
              stored.startswith("pbkdf2_sha256$") and int(stored.split("$")[1]) >= 240000,
              stored.split("$")[1] if stored.startswith("pbkdf2_sha256$") else "-")
        check("hash is salted (no plain sha256 of the password)",
              stored != hashlib.sha256(b"test123456").hexdigest())
        check("password not stored in plaintext", "test123456" not in stored)
        check("token stored hashed, not raw",
              s.query(models.ApiKey).filter(models.ApiKey.user_id == user.id).first().key_hash
              == hashlib.sha256(body["api_key"].encode()).hexdigest())

        # Downgrade to the legacy POC hash and prove login still works + upgrades.
        s.query(models.User).filter(models.User.id == user.id).update(
            {"password_hash": hashlib.sha256(b"legacypw1").hexdigest()}
        )
        s.commit()
    finally:
        s.close()

    st, body2, _h = await login(api, email, "legacypw1")
    check("legacy sha256 password still logs in", st == 200, f"got {st}: {str(body2)[:120]}")

    s = db.SessionLocal()
    try:
        user = s.query(models.User).filter(models.User.email == email).first()
        check("legacy hash upgraded to pbkdf2 on login",
              (user.password_hash or "").startswith("pbkdf2_sha256$"),
              (user.password_hash or "")[:24])
    finally:
        s.close()
    st, _b, _h = await login(api, email, "legacypw1")
    check("upgraded hash verifies the same password", st == 200, f"got {st}")


# ---------------------------------------------------------------------------
# Test 2/3/4: session tokens
# ---------------------------------------------------------------------------
async def test_sessions(api, env):
    print("\nTest 2: session tokens (TTL + rotation)")
    st, body, _h = await register(api, "sess")
    email = (body or {}).get("email")
    if st != 200:
        check("register for session test", False, str(body)[:120])
        return None
    account_key = body["api_key"]

    st, login_body, _h = await login(api, email, "test123456")
    check("login -> 200", st == 200, f"got {st}: {str(login_body)[:120]}")
    if st != 200:
        return None
    check("login issues a session token (sess_ prefix)",
          str(login_body.get("api_key", "")).startswith("sess_"), str(login_body.get("api_key"))[:12])
    check("token_type=session", login_body.get("token_type") == "session", str(login_body.get("token_type")))
    check("expires_at is set", bool(login_body.get("expires_at")), str(login_body.get("expires_at")))
    check("expires_in is within the 24h default",
          (login_body.get("expires_in") or 0) > 0 and login_body["expires_in"] <= 24 * 3600 + 5,
          str(login_body.get("expires_in")))

    sess1 = login_body["api_key"]
    st, _b, _h = await api.request("GET", "/v1/me", token=sess1)
    check("session token authenticates /v1/me", st == 200, f"got {st}")

    st, _b, _h = await api.request("GET", "/v1/me", token=account_key)
    check("long-lived API key still authenticates (no regression)", st == 200, f"got {st}")

    print("\nTest 3: token rotation + expiry enforcement")
    st, login2, _h = await login(api, email, "test123456")
    sess2 = (login2 or {}).get("api_key")
    check("second login -> 200", st == 200, f"got {st}")
    st, _b, _h = await api.request("GET", "/v1/me", token=sess1)
    check("previous session token revoked by rotation -> 401", st == 401, f"got {st}")
    st, _b, _h = await api.request("GET", "/v1/me", token=sess2)
    check("current session token works", st == 200, f"got {st}")

    # Force-expire sess2 directly in the DB (same process, same DB).
    db, models = env.mod("database"), env.mod("models")
    from datetime import datetime, timedelta
    s = db.SessionLocal()
    try:
        row = s.query(models.ApiKey).filter(
            models.ApiKey.key_hash == hashlib.sha256(sess2.encode()).hexdigest()
        ).first()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        s.commit()
    finally:
        s.close()
    st, body3, _h = await api.request("GET", "/v1/me", token=sess2)
    check("expired session token -> 401", st == 401, f"got {st}")
    check("error names the expiry", "expired" in json.dumps(body3).lower(), str(body3)[:80])

    print("\nTest 4: explicit revocation (logout)")
    st, login3, _h = await login(api, email, "test123456")
    sess3 = (login3 or {}).get("api_key")
    st, body4, _h = await api.request("POST", "/auth/logout", token=sess3)
    check("POST /auth/logout -> 200", st == 200, f"got {st}: {str(body4)[:100]}")
    check("logout reports a revoked session", (body4 or {}).get("revoked", 0) >= 1, str(body4)[:100])
    st, _b, _h = await api.request("GET", "/v1/me", token=sess3)
    check("revoked session token -> 401", st == 401, f"got {st}")
    st, _b, _h = await api.request("GET", "/v1/me", token=account_key)
    check("logout does not revoke the long-lived API key", st == 200, f"got {st}")


# ---------------------------------------------------------------------------
# Test 5: brute-force protection
# ---------------------------------------------------------------------------
async def test_bruteforce(api, env):
    print("\nTest 5: login brute-force protection")
    st, body_bf, _h = await register(api, "bf")
    email = (body_bf or {}).get("email")
    if st != 200:
        check("register for brute-force test", False, str(st))
        return

    reset_limits(env)
    ratelimit = env.mod("ratelimit")
    # This group tests the *lockout* specifically, so raise the token bucket
    # out of the way; the bucket itself is covered in Test 6.
    os.environ["LOGIN_MAX_FAILURES"] = "5"
    os.environ["LOGIN_LOCK_SECONDS"] = "300"
    os.environ["RATE_LIMIT_LOGIN_PER_MIN"] = "600"
    os.environ["RATE_LIMIT_LOGIN_BURST"] = "200"

    st, _b, _h = await login(api, email, "test123456")
    check("correct password logs in before any lockout", st == 200, f"got {st}")

    statuses = []
    for i in range(5):
        st, _b, _h = await login(api, email, f"wrong-{i}")
        statuses.append(st)
    check("wrong passwords -> 401", all(s == 401 for s in statuses), str(statuses))

    st, body_locked, hdrs_locked = await login(api, email, "test123456")
    check("correct password refused while locked -> 429", st == 429, f"got {st}: {str(body_locked)[:100]}")
    check("lockout 429 carries Retry-After", bool(header(hdrs_locked, "Retry-After")),
          str(header(hdrs_locked, "Retry-After")))
    check("lockout message names the cause",
          "locked" in json.dumps(body_locked).lower() or "too many" in json.dumps(body_locked).lower(),
          str(body_locked)[:120])

    st_unknown, body_unknown, _h = await login(api, fresh_email("ghost"), "whatever123")
    check("lockout also covers the client IP (blocked while locked -> 429)",
          st_unknown == 429, f"got {st_unknown}: {str(body_unknown)[:80]}")

    # Prove the lockout (not a broken password path) is what blocked login.
    ratelimit.LOGIN_GUARD.reset()
    st, _b, _h = await login(api, email, "test123456")
    check("after lock expiry/reset the correct password works again", st == 200, f"got {st}")

    # A different account is not affected by another account's lockout.
    st, _b, _h = await login(api, fresh_email("ghost2"), "whatever123")
    check("other accounts are unaffected by the lockout", st == 401, f"got {st}")

    os.environ["RATE_LIMIT_LOGIN_PER_MIN"] = "10"
    os.environ["RATE_LIMIT_LOGIN_BURST"] = "5"
    reset_limits(env)


# ---------------------------------------------------------------------------
# Test 6: rate limits
# ---------------------------------------------------------------------------
async def test_rate_limits(api, env):
    print("\nTest 6: rate limits (429 + Retry-After)")
    reset_limits(env)
    ratelimit = env.mod("ratelimit")
    os.environ["RATE_LIMITS_DISABLED"] = "0"

    st, body, _h = await register(api, "rl", role="provider")
    if st != 200:
        check("register for rate-limit test", False, str(st))
        return
    key = body["api_key"]

    # --- per-user node limit (register_node calls limit_node(user.id))
    os.environ["RATE_LIMIT_NODE_PER_MIN"] = "1"
    os.environ["RATE_LIMIT_NODE_BURST"] = "1"
    ratelimit.LIMITER.reset()
    payload = {"name": "rl-node", "gpu_type": "RTX 4090", "vram_gb": 24}
    st1, _b1, _h1 = await api.request("POST", "/nodes/register", payload, token=key)
    st2, b2, h2 = await api.request("POST", "/nodes/register", payload, token=key)
    check("first node register passes", st1 in (200, 201), f"got {st1}")
    check("second node register -> 429", st2 == 429, f"got {st2}: {str(b2)[:100]}")
    check("node 429 carries Retry-After", bool(header(h2, "Retry-After")), str(header(h2, "Retry-After")))

    # --- per-user chat limit
    os.environ["RATE_LIMIT_CHAT_PER_MIN"] = "1"
    os.environ["RATE_LIMIT_CHAT_BURST"] = "1"
    ratelimit.LIMITER.reset()
    chat = {"model": "qwen2.5-coder:7b", "messages": [{"role": "user", "content": "hi"}]}
    st1, _b1, _h1 = await api.request("POST", "/v1/chat/completions", chat, token=key)
    st2, b2, h2 = await api.request("POST", "/v1/chat/completions", chat, token=key)
    check("first chat request is not rate limited", st1 != 429, f"got {st1}: {str(_b1)[:80]}")
    check("second chat request -> 429", st2 == 429, f"got {st2}: {str(b2)[:100]}")
    check("chat 429 carries Retry-After", bool(header(h2, "Retry-After")), str(header(h2, "Retry-After")))

    # --- login limit
    os.environ["RATE_LIMIT_LOGIN_PER_MIN"] = "1"
    os.environ["RATE_LIMIT_LOGIN_BURST"] = "1"
    ratelimit.LIMITER.reset()
    ratelimit.LOGIN_GUARD.reset()
    st1, _b1, _h1 = await login(api, "nobody@example.com", "x")
    st2, _b2, h2 = await login(api, "nobody2@example.com", "x")
    check("first login attempt is not rate limited", st1 == 401, f"got {st1}")
    check("second login attempt from the same IP -> 429", st2 == 429, f"got {st2}")
    check("login 429 carries Retry-After", bool(header(h2, "Retry-After")), str(header(h2, "Retry-After")))

    # --- reset and prove limits are configurable, not hardcoded
    ratelimit.LIMITER.reset()
    ratelimit.LOGIN_GUARD.reset()
    os.environ["RATE_LIMIT_CHAT_PER_MIN"] = "60"
    os.environ["RATE_LIMIT_CHAT_BURST"] = "20"
    os.environ["RATE_LIMIT_LOGIN_PER_MIN"] = "10"
    os.environ["RATE_LIMIT_LOGIN_BURST"] = "5"
    os.environ["RATE_LIMIT_NODE_PER_MIN"] = "240"
    os.environ["RATE_LIMIT_NODE_BURST"] = "60"
    st, _b, _h = await api.request("GET", "/v1/me", token=key)
    check("normal traffic unaffected after limits are restored", st == 200, f"got {st}")


# ---------------------------------------------------------------------------
# Test 7: admin gate
# ---------------------------------------------------------------------------
async def test_admin_gate(api, env):
    print("\nTest 7: admin endpoint authentication (was unauthenticated)")
    reset_limits(env)
    body = {"email": fresh_email("adm"), "name": "Admin Test", "initial_credits": 5}

    os.environ.pop("ADMIN_TOKEN", None)
    os.environ.pop("ADMIN_EMAILS", None)
    st, b, _h = await api.request("POST", "/admin/users", body)
    check("unconfigured admin API -> 401 (default deny)", st == 401, f"got {st}: {str(b)[:100]}")

    os.environ["ADMIN_TOKEN"] = TEST_ADMIN_TOKEN
    st, b, _h = await api.request("POST", "/admin/users", body, headers={"X-Admin-Token": "nope-not-the-token"})
    check("wrong operator token -> 401", st == 401, f"got {st}: {str(b)[:100]}")
    st, b, _h = await api.request("POST", "/admin/users", body, headers={"X-Admin-Token": TEST_ADMIN_TOKEN})
    check("correct operator token -> 201 (created)", st == 201, f"got {st}: {str(b)[:120]}")
    check("admin-created user gets a key", bool((b or {}).get("api_key")), str(b)[:60])

    st, b, _h = await api.request("POST", "/admin/users/1/topup", {"amount": 5},
                                  headers={"X-Admin-Token": TEST_ADMIN_TOKEN})
    check("topup accepts the operator token", st == 200, f"got {st}: {str(b)[:100]}")

    # An ordinary user token must not pass the admin gate.
    st, reg, _h = await register(api, "notadmin")
    if st == 200:
        st, b, _h = await api.request("POST", "/admin/users",
                                {"email": fresh_email("x"), "name": "X"},
                                token=reg["api_key"])
        check("ordinary user token -> 403", st == 403, f"got {st}: {str(b)[:100]}")

    # ... but an allowlisted admin account token does.
    os.environ["ADMIN_EMAILS"] = "admin@example.com"
    st, admin_reg, _h = await register(api, "admin", role="both")
    if st == 200:
        db, models = env.mod("database"), env.mod("models")
        s = db.SessionLocal()
        try:
            s.query(models.User).filter(models.User.id == admin_reg["user_id"]).update(
                {"email": "admin@example.com"}
            )
            s.commit()
        finally:
            s.close()
        st, b, _h = await api.request("POST", "/admin/users",
                                {"email": fresh_email("viaadmin"), "name": "ViaAdmin"},
                                token=admin_reg["api_key"])
        check("allowlisted admin account token -> 201 (created)", st == 201, f"got {st}: {str(b)[:120]}")


# ---------------------------------------------------------------------------
# Test 8: node-agent key handling
# ---------------------------------------------------------------------------
async def test_node_keys(api, env):
    print("\nTest 8: node-agent keys (hashed at rest + rotation)")
    reset_limits(env)
    st, body, _h = await register(api, "nodekey", role="provider")
    if st != 200:
        check("register for node-key test", False, str(st))
        return
    key = body["api_key"]
    os.environ["RATE_LIMIT_NODE_PER_MIN"] = "600"
    os.environ["RATE_LIMIT_NODE_BURST"] = "200"
    env.mod("ratelimit").LIMITER.reset()

    st, node, _h = await api.request("POST", "/nodes/register",
                               {"name": "key-node", "gpu_type": "RTX 3060", "vram_gb": 12},
                               token=key)
    check("node register -> 201", st == 201, f"got {st}: {str(node)[:120]}")
    if st != 201:
        return
    raw = node["agent_api_key"]
    node_id = node["id"]

    db, models = env.mod("database"), env.mod("models")
    s = db.SessionLocal()
    try:
        row = s.query(models.GpuNode).filter(models.GpuNode.id == node_id).first()
        check("raw key not stored in the DB", row.api_key is None, str(row.api_key))
        check("key hash stored",
              row.api_key_hash == hashlib.sha256(raw.encode()).hexdigest(), str(row.api_key_hash)[:16])
    finally:
        s.close()

    hb = {"status": "online", "gpu_util": 0.1, "vram_used_gb": 2.0, "active_jobs": 0}
    st, _b, _h = await api.request("POST", f"/nodes/{node_id}/heartbeat", hb, headers={"X-Node-Key": raw})
    check("heartbeat with the issued key -> 204", st == 204, f"got {st}")
    st, b, _h = await api.request("POST", f"/nodes/{node_id}/heartbeat", hb, headers={"X-Node-Key": "node_wrong"})
    check("heartbeat with a wrong key -> 401", st == 401, f"got {st}: {str(b)[:80]}")

    st, rot, _h = await api.request("POST", f"/nodes/{node_id}/rotate-key", token=key)
    check("rotate-key -> 200", st == 200, f"got {st}: {str(rot)[:100]}")
    new_raw = (rot or {}).get("agent_api_key")
    check("rotation returns a new key", bool(new_raw) and new_raw != raw, str(new_raw)[:12])
    st, _b, _h = await api.request("POST", f"/nodes/{node_id}/heartbeat", hb, headers={"X-Node-Key": raw})
    check("old key invalid after rotation -> 401", st == 401, f"got {st}")
    st, _b, _h = await api.request("POST", f"/nodes/{node_id}/heartbeat", hb, headers={"X-Node-Key": new_raw})
    check("new key works after rotation -> 204", st == 204, f"got {st}")


# ---------------------------------------------------------------------------
# Test 9/10: exposure of other users' data
# ---------------------------------------------------------------------------
async def test_public_exposure(api, env):
    print("\nTest 9: public node views do not leak private fields")
    reset_limits(env)
    st, node_list, _h = await api.request("GET", "/nodes/list")
    check("GET /nodes/list -> 200", st == 200, f"got {st}")
    if st == 200 and node_list:
        first = node_list[0]
        check("public list has no tailscale_ip", "tailscale_ip" not in first, str(list(first.keys()))[:120])
        check("public list has no owner_id", "owner_id" not in first)
        check("public list has no earnings_total", "earnings_total" not in first)
        check("public list still identifies the node", "id" in first and "name" in first)

    print("\nTest 10: /pool/jobs is scoped to the caller")
    st, body, _h = await register(api, "jobs", role="provider")
    key = body["api_key"]
    env.mod("ratelimit").LIMITER.reset()
    st, node, _h = await api.request("POST", "/nodes/register",
                               {"name": "jobs-node", "gpu_type": "RTX 4090", "vram_gb": 24},
                               token=key)
    node_id = (node or {}).get("id")

    db, models = env.mod("database"), env.mod("models")
    s = db.SessionLocal()
    try:
        other = models.User(email=fresh_email("other"), name="Other", is_active=True)
        s.add(other)
        s.flush()
        s.add(models.PoolJob(user_id=other.id, model="secret-model", source="community",
                             status="succeeded"))
        s.add(models.PoolJob(user_id=body["user_id"], node_id=node_id, model="mine-model",
                             source="community", status="succeeded"))
        s.commit()
    finally:
        s.close()

    st, jobs, _h = await api.request("GET", "/pool/jobs?limit=50", token=key)
    check("GET /pool/jobs -> 200", st == 200, f"got {st}")
    if st == 200:
        models_seen = {j.get("model") for j in jobs}
        check("own job visible", "mine-model" in models_seen, str(models_seen))
        check("other user's job hidden", "secret-model" not in models_seen, str(models_seen))
    st, b, _h = await api.request("GET", "/pool/jobs?limit=50")
    check("GET /pool/jobs without a token -> 401", st == 401, f"got {st}")


# ---------------------------------------------------------------------------
# Test 11: register validation
# ---------------------------------------------------------------------------
async def test_register_validation(api, env):
    print("\nTest 11: register validation")
    reset_limits(env)
    st, b, _h = await api.request("POST", "/auth/register", {
        "email": fresh_email("short"), "name": "Short", "password": "abc",
    })
    check("too-short password -> 422", st == 422, f"got {st}: {str(b)[:100]}")
    st, b, _h = await api.request("POST", "/auth/register", {
        "email": fresh_email("ok"), "name": "OK", "password": "longenough1",
    })
    check("long enough password -> 200", st == 200, f"got {st}: {str(b)[:100]}")
    st, b, _h = await api.request("POST", "/v1/chat/completions",
                            {"model": "qwen2.5-coder:7b", "messages": [{"role": "user", "content": "hi"}]})
    check("no token -> 401 with OpenAI-compatible error", st == 401, f"got {st}")
    check("error mentions Authorization/Bearer",
          "authorization" in json.dumps(b).lower() or "bearer" in json.dumps(b).lower(),
          str(b)[:100])


# ---------------------------------------------------------------------------
# Environment handle for the in-process server
# ---------------------------------------------------------------------------
class Env:
    def __init__(self, app):
        self.app = app

    def mod(self, name):
        return sys.modules[name]


async def run_against_live(base_url):
    api = LiveAPI(base_url)
    env = Env(None)
    print(f"GPU-Pool auth tests against {base_url}")
    print("=" * 64)
    print("NOTE: live mode covers the API surface only; DB-level assertions "
          "(hash scheme, expiry) are skipped.")
    try:
        await test_register_validation(api, env)
        await test_public_exposure(api, env)
    finally:
        await api.aclose()


async def run_in_process():
    port, app, server, task, data_dir = await start_test_server()
    api = LiveAPI(f"http://127.0.0.1:{port}")
    env = Env(app)
    print(f"GPU-Pool auth-hardening tests on 127.0.0.1:{port} (in-process, throwaway DB)")
    print("=" * 64)
    try:
        await test_password_storage(api, env)
        await test_sessions(api, env)
        await test_bruteforce(api, env)
        await test_rate_limits(api, env)
        await test_admin_gate(api, env)
        await test_node_keys(api, env)
        await test_public_exposure(api, env)
        await test_register_validation(api, env)
    finally:
        await api.aclose()
        await stop_test_server(server, task, data_dir)


def main():
    live = os.environ.get("GPU_POOL_API")
    if live:
        asyncio.run(run_against_live(live))
    else:
        # The in-process server is the default: it is self-contained, uses a
        # private DATA_DIR and needs no running portal.
        import uvicorn  # noqa: F401  (fail fast with a clear ImportError)
        asyncio.run(run_in_process())

    print()
    print("=" * 64)
    failed = results.count(False)
    print(f"{len(results) - failed}/{len(results)} checks passed")
    if failed:
        print(f"{failed} check(s) FAILED")
        return 1
    print("All auth-hardening tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
