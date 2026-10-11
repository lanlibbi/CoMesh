#!/usr/bin/env python3
"""End-to-end check for LANA-89: a node on a DHCP-like network registers itself.

Runs a real portal (uvicorn, temp DATA_DIR) and the real node-agent code in two
subprocesses, then asserts the path the ticket describes:

  1., 2.  node-agent starts with ONLY PORTAL_URL + PORTAL_USER_KEY + ADVERTISE_HOST,
           self-registers, and writes its credentials to the state file
  3.      the portal stores the node URL the agent advertised (no IP in any config)
  4.      a heartbeat from the agent flips the node online, and the portal's
          auto-detection path is exercised too
  5.      the pool builds a dial URL from node_url (not from a hardcoded IP)

Usage:  .venv/bin/python tests/e2e_dhcp_flow.py
Exit code 0 = pass. Prints each step, so a failure names the step that broke.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PORTAL_PORT = 8931
AGENT_PORT = 8932
PORTAL_URL = f"http://127.0.0.1:{PORTAL_PORT}"

failures: list[str] = []


def step(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def http(method: str, url: str, body: dict | None = None, headers: dict | None = None,
         timeout: float = 10.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300]}


def wait_for_port(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="comesh-dhcp-e2e-"))
    data_dir = tmp / "portal-data"
    data_dir.mkdir(parents=True)
    state_file = tmp / "node-state.json"
    log_portal = open(tmp / "portal.log", "w")
    log_agent = open(tmp / "agent.log", "w")

    env_portal = {
        **os.environ,
        "DATA_DIR": str(data_dir),
        "SEED_KEY_PATH": str(data_dir / "seed_api_key.txt"),
        "CONFIG_PATH": str(REPO / "config.yaml"),
        "PYTHONPATH": str(REPO),
    }
    portal = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
         "--port", str(PORTAL_PORT), "--log-level", "warning"],
        cwd=str(REPO), env=env_portal, stdout=log_portal, stderr=subprocess.STDOUT,
    )
    agent = None
    try:
        print("1. portal up (temp DATA_DIR, no fixed address configured)")
        if not wait_for_port(PORTAL_PORT):
            print("  portal never came up; log tail:")
            print((tmp / "portal.log").read_text()[-1500:])
            return 1
        step("portal answers /health", http("GET", f"{PORTAL_URL}/health")[0] == 200)

        status, echo = http("GET", f"{PORTAL_URL}/net/echo")
        step("portal serves the setup check /net/echo", status == 200, str(echo)[:120] if status != 200 else "")

        # --- account to register a node with ---------------------------------
        email = f"dhcp-{int(time.time())}@example.test"
        status, reg = http("POST", f"{PORTAL_URL}/auth/register",
                           {"email": email, "password": "sup3rsecret!", "name": "DHCP Tester"})
        if status != 200:
            status, reg = http("POST", f"{PORTAL_URL}/auth/login",
                               {"email": email, "password": "sup3rsecret!"})
        step("test account created/logged in", status == 200, f"HTTP {status}: {reg}")
        user_key = (reg or {}).get("api_key") or (reg or {}).get("apiKey")
        if not user_key:
            print("  no API key in the auth response — cannot continue:", reg)
            return 1
        http("PUT", f"{PORTAL_URL}/v1/me/role", {"role": "provider"},
             {"Authorization": f"Bearer {user_key}"})

        # --- node-agent: the "fresh DHCP network" setup ----------------------
        print("2. node-agent starts with only PORTAL_URL + PORTAL_USER_KEY (no NODE_ID, no IP)")
        env_agent = {
            **os.environ,
            "PYTHONPATH": str(REPO / "node-agent"),
            "PORTAL_URL": PORTAL_URL,
            "PORTAL_USER_KEY": user_key,
            "ADVERTISE_HOST": "e2e-node.example.test",
            "NODE_NAME": "e2e-dhcp-node",
            "NODE_GPU_TYPE": "Test GPU",
            "NODE_VRAM_GB": "8",
            "AGENT_PORT": str(AGENT_PORT),
            "NODE_STATE_FILE": str(state_file),
            "HEARTBEAT_SEC": "2",
            "OLLAMA_URL": "http://127.0.0.1:59999",
        }
        agent = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "agent:app", "--host", "127.0.0.1",
             "--port", str(AGENT_PORT), "--log-level", "warning"],
            cwd=str(REPO / "node-agent"), env=env_agent, stdout=log_agent, stderr=subprocess.STDOUT,
        )
        if not wait_for_port(AGENT_PORT):
            print("  agent never came up; log tail:")
            print((tmp / "agent.log").read_text()[-2000:])
            return 1

        deadline = time.time() + 25
        while time.time() < deadline and not state_file.exists():
            time.sleep(0.4)
        step("agent self-registered and wrote its state file", state_file.exists(),
             str(state_file) if not state_file.exists() else "")
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
        step("state file carries node_id + agent key",
             bool(state.get("node_id")) and bool(state.get("node_api_key")),
             f"node_id={state.get('node_id')}")
        step("state file is not world-readable",
             state_file.exists() and (state_file.stat().st_mode & 0o077) == 0,
             oct(state_file.stat().st_mode) if state_file.exists() else "missing")

        # --- node visible in the portal, with an address ---------------------
        print("3. portal knows the node and where to reach it")
        nodes = http("GET", f"{PORTAL_URL}/nodes/my", headers={"Authorization": f"Bearer {user_key}"})[1] or []
        node = nodes[0] if nodes else {}
        step("node registered (no NODE_ID given by the operator)", bool(node.get("id")), str(node)[:200])
        step("node_url came from the agent, not from a config IP",
             (node.get("node_url") or "").startswith("http://e2e-node.example.test"),
             f"node_url={node.get('node_url')}")
        step("the node's port is stored next to the URL (dial URL gets it appended)",
             node.get("port") == AGENT_PORT, f"port={node.get('port')}")
        step("node_url is flagged as explicitly advertised (not auto)",
             node.get("node_url_auto") is False, f"auto={node.get('node_url_auto')}")
        step("deprecated tailscale_ip mirror carries the host",
             node.get("tailscale_ip") == "e2e-node.example.test", f"mirror={node.get('tailscale_ip')}")

        # --- heartbeat + online state ---------------------------------------
        print("4. heartbeat flips the node online and pools it")
        deadline = time.time() + 20
        mine = {}
        while time.time() < deadline:
            mine = (http("GET", f"{PORTAL_URL}/nodes/my",
                         headers={"Authorization": f"Bearer {user_key}"})[1] or [{}])[0]
            if mine.get("status") in ("online", "busy"):
                break
            time.sleep(1)
        step("heartbeat received (status online/busy)", mine.get("status") in ("online", "busy"),
             f"status={mine.get('status')}")
        step("portal exposes the agent port it was told", mine.get("port") == AGENT_PORT,
             f"port={mine.get('port')}")

        # --- auto-detected address (the DHCP path, no advertise_host) -------
        print("5. auto-detection path: register without node_url, heartbeat from a public source")
        status, raw = http("POST", f"{PORTAL_URL}/nodes/register", {
            "name": "auto-detect node", "gpu_type": "Test GPU", "vram_gb": 8,
            "port": 11435, "node_url": None,
        }, {"Authorization": f"Bearer {user_key}"})
        auto_id = (raw or {}).get("id")
        auto_key = (raw or {}).get("agent_api_key")
        step("second node registers with an empty address", status == 201, f"HTTP {status}: {raw}")
        if auto_id and auto_key:
            status, _ = http("POST", f"{PORTAL_URL}/nodes/{auto_id}/heartbeat", {
                "status": "online", "gpu_util": 0.1, "vram_used_gb": 1.0,
                "advertise_host": "192.168.7.77", "agent_port": 11435,
            }, {"X-Node-Key": auto_key})
            step("heartbeat accepted", status == 204, f"HTTP {status}")
            auto_node = http("GET", f"{PORTAL_URL}/nodes/my",
                             headers={"Authorization": f"Bearer {user_key}"})[1] or []
            match = [n for n in auto_node if n.get("id") == auto_id]
            got = (match[0].get("node_url") if match else None) or ""
            step("portal derived the address from the heartbeat",
                 got == "http://192.168.7.77:11435", f"node_url={got}")
            step("derived address is flagged auto",
                 bool(match) and match[0].get("node_url_auto") is True)

        # --- pool dial URL ---------------------------------------------------
        print("6. the pool dials node_url (no hardcoded address anywhere)")
        sys.path.insert(0, str(REPO))
        from netinfo import node_base_url  # noqa: E402
        step("node_base_url keeps an explicit port",
             node_base_url("http://gpu-01.local:11435", 11435) == "http://gpu-01.local:11435")
        step("node_base_url adds the node port when the URL has none",
             node_base_url("http://gpu-01.local", 11435) == "http://gpu-01.local:11435")
        step("node_base_url preserves https (reverse proxy)",
             node_base_url("https://gpu.example.net", 11435) == "https://gpu.example.net:11435")
        step("no node_url -> no dial URL (caller must fall back), not an empty host URL",
             node_base_url(None, 11435) is None and node_base_url("", 11435) is None)

    finally:
        for proc in (agent, portal):
            if proc and proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        log_portal.close()
        log_agent.close()
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"RESULT: {len(failures)} check(s) failed: {failures}")
        return 1
    print("RESULT: all checks passed — a node with only .env variables registered, "
          "reported its own address, and the pool can dial it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
