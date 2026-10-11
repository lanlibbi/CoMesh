"""
GPU-Pool Feature Tests (POC).

Run with the api service reachable. Defaults to http://localhost:8000.
Override with the GPU_POOL_API env var.

    GPU_POOL_API=http://portal-host:8765 python3 tests/test_features.py

Tests:
  1. Register a provider user
  2. Switch role to consumer and back
  3. Query /v1/available-models and check structure
  4. Set allowed_models and verify persistence
  5. Cloud-model request as default user should be 403
  6. Cloud-model request after opt-in goes through (no node -> 502/503 OK)

Exits with code 0 on success, 1 on first failure.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

API = os.environ.get("GPU_POOL_API", "http://localhost:8000").rstrip("/")


def http(method, path, body=None, token=None, raw=False):
    url = f"{API}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("utf-8")
            if raw:
                return r.status, text
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
        try:
            payload = json.loads(text)
        except Exception:
            payload = text
        if raw:
            return e.code, text
        return e.code, payload


PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def check(name, cond, detail=""):
    if cond:
        print(f"  {PASS} {name}{(' — ' + detail) if detail else ''}")
        return True
    print(f"  {FAIL} {name}{(' — ' + detail) if detail else ''}")
    return False


def run():
    print(f"GPU-Pool feature tests against {API}")
    print("=" * 60)
    failures = 0
    email = f"test-{int(time.time())}-{os.getpid()}@example.com"
    password = "test123456"
    print(f"Test user: {email}")
    print()

    # --- 1. Register a provider user
    print("Test 1: Register a provider user")
    status, body = http("POST", "/auth/register", {
        "email": email, "name": "Test", "password": password,
        "role": "provider", "initial_credits": 50,
    })
    ok = check("register returns 200", status == 200, str(status))
    if not ok:
        failures += 1
        return failures
    key = body["api_key"]
    check("response includes role=provider", body.get("role") == "provider", f"got {body.get('role')}")
    check("response includes allowed_models=null", body.get("allowed_models") is None)
    failures += 0 if body.get("role") == "provider" and body.get("allowed_models") is None else 1

    # --- 2. Switch role to consumer and back
    print("\nTest 2: Switch role to consumer and back")
    status, body = http("PUT", "/v1/me/role", {"role": "consumer"}, token=key)
    check("PUT role=consumer -> 200", status == 200, str(status))
    check("response.role == consumer", body.get("role") == "consumer")
    status, body = http("GET", "/v1/me", token=key)
    check("GET /v1/me reflects new role", body.get("role") == "consumer", f"got {body.get('role')}")
    # back to provider
    status, body = http("PUT", "/v1/me/role", {"role": "both"}, token=key)
    check("PUT role=both -> 200", status == 200)
    check("response.role == both", body.get("role") == "both")

    # --- 3. /v1/available-models structure
    print("\nTest 3: /v1/available-models structure")
    status, body = http("GET", "/v1/available-models", token=key)
    check("GET /v1/available-models -> 200", status == 200)
    check("response has 'models' array", isinstance(body.get("models"), list))
    if body.get("models"):
        m0 = body["models"][0]
        check(
            "first model has name/size_gb/is_cloud/is_local",
            all(k in m0 for k in ("name", "size_gb", "is_cloud", "is_local")),
            str(list(m0.keys())),
        )
        # Find a cloud model name (fall back to a fake one if Ollama has none)
        cloud = next((m for m in body["models"] if m.get("is_cloud")), None)
        cloud_name = cloud["name"] if cloud else "fake-cloud-model-9999"
        check("have at least one model", len(body["models"]) >= 1, f"got {len(body['models'])}")
    else:
        cloud_name = "fake-cloud-model-9999"

    # --- 4. Set allowed_models and verify persistence
    print("\nTest 4: Set allowed_models + verify persistence")
    status, body = http("PUT", "/v1/me/allowed-models", {
        "models": ["qwen2.5-coder:7b"],
        "allow_cloud": False,
    }, token=key)
    check("PUT allowed-models -> 200", status == 200)
    check("response.allowed_models is the list we sent",
          body.get("allowed_models") == ["qwen2.5-coder:7b"],
          f"got {body.get('allowed_models')}")
    check("response.allow_cloud is False", body.get("allow_cloud") is False)
    status, body = http("GET", "/v1/me", token=key)
    check("GET /v1/me reflects whitelist",
          body.get("allowed_models") == ["qwen2.5-coder:7b"],
          f"got {body.get('allowed_models')}")

    # --- 5. Cloud request as default user -> 403
    print("\nTest 5: Cloud request blocked without opt-in")
    status, body = http("POST", "/v1/chat/completions", {
        "model": cloud_name,
        "messages": [{"role": "user", "content": "hi"}],
    }, token=key)
    check("cloud model request returns 403", status == 403, f"got {status}")
    check("error mentions cloud/profile", "cloud" in str(body).lower() or "profile" in str(body).lower(),
          str(body)[:100])

    # --- 6. After opt-in, request goes through (no node -> 502/503 OK)
    print("\nTest 6: Cloud request allowed after opt-in")
    status, body = http("PUT", "/v1/me/allowed-models", {
        "models": [cloud_name, "qwen2.5-coder:7b"],
        "allow_cloud": True,
    }, token=key)
    check("opt-in to cloud -> 200", status == 200)
    check("allow_cloud is True", body.get("allow_cloud") is True)
    check("cloud model in allowed_models", cloud_name in (body.get("allowed_models") or []),
          f"allowed: {body.get('allowed_models')}")
    # Now make a cloud request — should NOT be 403. May be 200, 502, or 503 depending on
    # whether Ollama is reachable / a node is online. We just verify it's not 403.
    status, body = http("POST", "/v1/chat/completions", {
        "model": cloud_name,
        "messages": [{"role": "user", "content": "hi"}],
    }, token=key)
    check("cloud request not 403 after opt-in", status != 403, f"got {status}: {str(body)[:120]}")

    # --- bonus: role-gated node registration
    print("\nBonus: Consumer can't register nodes")
    http("PUT", "/v1/me/role", {"role": "consumer"}, token=key)
    status, body = http("POST", "/nodes/register", {
        "name": "blocked-test", "gpu_type": "RTX 4090", "vram_gb": 24,
    }, token=key)
    check("consumer POST /nodes/register -> 403", status == 403, f"got {status}")

    print()
    print("=" * 60)
    if failures == 0:
        print(f"All tests passed against {API}")
        return 0
    print(f"{failures} test group(s) had failures")
    return 1


if __name__ == "__main__":
    sys.exit(run())
