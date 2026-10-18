"""Regression tests for the login path and the public exposure of pool data.

These are the cheap, in-process guard rails for LANA-46: they pin the behaviour
that broke in production (a login attempt with an unknown e-mail raised a
NameError and answered 500 instead of 401) and the two data-leak findings
(public /nodes/list, unscoped /pool/jobs).

Run with:  python3 -m pytest tests/test_login_hardening.py
"""
import pytest


@pytest.fixture(autouse=True)
def _reset_limits():
    """Rate-limit buckets and lockouts are process-global; start each test clean."""
    from ratelimit import LIMITER, LOGIN_GUARD
    LIMITER.reset()
    LOGIN_GUARD.reset()
    yield
    LIMITER.reset()
    LOGIN_GUARD.reset()


def _register(client, email, password="test123456"):
    r = client.post("/auth/register", json={
        "email": email, "name": "Regression", "password": password,
        "role": "both", "initial_credits": 10,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_login_unknown_email_is_401_not_500(client):
    r = client.post("/auth/login", json={
        "email": "definitely-not-here@example.invalid", "password": "whatever123",
    })
    assert r.status_code == 401, f"{r.status_code}: {r.text}"
    assert r.json().get("detail") == "Invalid credentials"


def test_login_wrong_password_is_401(client):
    _register(client, "reg-wrongpw@example.com")
    r = client.post("/auth/login", json={
        "email": "reg-wrongpw@example.com", "password": "not-the-password",
    })
    assert r.status_code == 401, f"{r.status_code}: {r.text}"


def test_login_repeated_failures_lock_out(client):
    """The account lockout must answer 429 (with Retry-After), never 401 forever."""
    _register(client, "reg-lockout@example.com")
    codes = []
    for _ in range(12):
        r = client.post("/auth/login", json={
            "email": "reg-lockout@example.com", "password": "wrong-password",
        })
        codes.append(r.status_code)
        if r.status_code == 429:
            assert "Retry-After" in r.headers
            break
    assert 429 in codes, f"no lockout seen, codes={codes}"


def test_public_node_list_hides_private_fields(client):
    r = client.get("/nodes/list")
    assert r.status_code == 200, r.text
    for row in r.json():
        for private in ("owner_id", "tailscale_ip", "earnings_total", "node_url"):
            assert private not in row, f"{private} leaked in /nodes/list"


def test_pool_jobs_requires_authentication(client):
    assert client.get("/pool/jobs").status_code == 401


def test_admin_api_is_closed_without_token(client):
    r = client.post("/admin/users", json={"email": "x@example.com", "name": "X"})
    assert r.status_code == 401, f"{r.status_code}: {r.text}"
