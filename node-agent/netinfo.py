"""
Address helpers for the CoMesh node-agent — no dependency on the portal package.

The agent has to answer one question on every start: *under which address will
the portal reach me?* On a DHCP LAN it cannot know that from a config file, so it
is detected at runtime:

  1. ``ADVERTISE_HOST`` — what the operator pinned (a DNS name, an mDNS name like
     ``mygpu.local``, a mesh-VPN name, or an IP). Always wins: names survive a
     change of lease, plain IPs do not.
  2. the local address of the interface the default route uses (UDP probe, no
     traffic sent).
  3. the machine's hostname.

Keep this file byte-identical in intent with the portal's ``netinfo.py``; both
sides agree on the wire format (``host`` + ``port``, no scheme).
"""
from __future__ import annotations

import os
import socket
from typing import Optional
from urllib.parse import urlsplit

LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "[::]",
    "host.docker.internal",
    "host.docker.internal.",
}


def detect_outbound_ip() -> Optional[str]:
    """Local address of the interface with the default route. Sends nothing."""
    probe = ("1.1.1.1", 53)
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            s = socket.socket(family, socket.SOCK_DGRAM)
        except OSError:
            continue
        try:
            s.settimeout(0.5)
            s.connect(probe)
            addr = s.getsockname()[0]
            if addr and not addr.startswith("127.") and addr != "::1":
                return addr
        except OSError:
            continue
        finally:
            s.close()
    return None


def local_hostname(fqdn: bool = True) -> str:
    try:
        name = socket.getfqdn() if fqdn else socket.gethostname()
    except OSError:
        name = socket.gethostname()
    if not name or name in LOCAL_HOSTS or name.startswith("localhost"):
        try:
            name = socket.gethostname()
        except OSError:
            name = ""
    return name or ""


def resolve_advertise_host(preferred: str = "", env_var: str = "ADVERTISE_HOST") -> str:
    """See module docstring: explicit -> env -> detected IP -> hostname."""
    for candidate in (preferred, os.environ.get(env_var, "")):
        candidate = (candidate or "").strip()
        if candidate:
            return strip_scheme(candidate)
    ip = detect_outbound_ip()
    if ip:
        return ip
    return local_hostname()


def strip_scheme(value: str) -> str:
    value = (value or "").strip()
    if "://" in value:
        parts = urlsplit(value)
        value = parts.netloc or parts.path
    return value.strip().strip("/")


def gpu_summary() -> dict:
    """Best-effort GPU description used when registering a node.

    Returns ``{name, vram_gb}`` with ``unknown``/0 when there is no NVIDIA GPU
    (the portal accepts any gpu_type string; a CPU-only node is valid too).
    """
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        pynvml.nvmlShutdown()
        return {
            "name": name if isinstance(name, str) else name.decode("utf-8", "ignore"),
            "vram_gb": int(mem.total / 1024**3),
        }
    except Exception:
        return {"name": os.environ.get("GPU_TYPE", "unknown"), "vram_gb": int(os.environ.get("VRAM_GB", "0") or 0)}
