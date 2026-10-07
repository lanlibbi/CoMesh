"""
Network-address helpers (LANA-89).

Nothing in CoMesh may depend on a fixed IP, a hostname from one particular
site, or a mesh VPN: a deployment has to come up on a plain DHCP LAN, behind a
reverse proxy, or inside a tailnet, without editing code.

Two rules this module encodes:

* A node is addressed by ``node_url`` (scheme + host + port). The host may be a
  DNS name, an mDNS name (``host.local``), a mesh-VPN name (e.g. Tailscale
  MagicDNS) or a bare IP — the portal does not care, it is whatever *the
  portal* can reach.
* When a node has no ``node_url``, the portal derives one from the *source
  address of its heartbeat* and stores it back on the node. That is what makes
  DHCP work without any configuration: the agent reports itself in, the portal
  learns where it comes from. Such a URL is flagged ``node_url_auto`` and
  re-derived on every heartbeat, because a lease change invalidates it.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

# Hosts that are only meaningful on the machine itself — never a node address.
LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "[::]",
    "host.docker.internal",
    "host.docker.internal.",
}

DEFAULT_AGENT_PORT = 11435


# ---------------------------------------------------------------------------
# Detection (agent side, and the portal's own advertise address)
# ---------------------------------------------------------------------------
def detect_outbound_ip() -> Optional[str]:
    """Local address of the interface the default route uses — no traffic sent.

    A UDP socket is never connected, so nothing leaves the machine; the kernel
    just resolves which source address a packet to ``probe`` *would* use. That
    is the address a peer on the same network sees, which is exactly what a
    node has to advertise.
    """
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
    """Hostname of this machine. Prefers a name that resolves on the network."""
    try:
        name = socket.getfqdn() if fqdn else socket.gethostname()
    except OSError:
        name = socket.gethostname()
    # getfqdn() happily returns "localhost" on a misconfigured host.
    if not name or name in LOCAL_HOSTS or name.startswith("localhost"):
        try:
            name = socket.gethostname()
        except OSError:
            name = ""
    return name or ""


def resolve_advertise_host(preferred: str = "", env_var: str = "ADVERTISE_HOST") -> str:
    """Host to register/announce this process under.

    Order: explicit argument -> ``ADVERTISE_HOST`` -> detected outbound IP ->
    detected hostname. A DNS/mDNS name is *better* than an IP because it
    survives a DHCP lease change; the caller can pin one via ``ADVERTISE_HOST``
    (``mygpu.local``, ``gpu-01.example.net``, a tailnet MagicDNS name, …).
    """
    for candidate in (preferred, os.environ.get(env_var, "")):
        candidate = (candidate or "").strip()
        if candidate:
            return strip_scheme(candidate)
    ip = detect_outbound_ip()
    if ip:
        return ip
    return local_hostname()


# ---------------------------------------------------------------------------
# URL juggling
# ---------------------------------------------------------------------------
def strip_scheme(value: str) -> str:
    """``http://host:1234/`` -> ``host:1234``; leaves a bare host untouched."""
    value = (value or "").strip()
    if "://" in value:
        parts = urlsplit(value)
        value = parts.netloc or parts.path
    return value.strip().strip("/")


def host_of(value: str) -> Optional[str]:
    """Bare host out of a URL, ``host:port`` or bare host. IPv6 brackets kept."""
    raw = strip_scheme(value)
    if not raw:
        return None
    if raw.startswith("["):  # [::1]:11435
        return raw.split("]")[0] + "]"
    return raw.split(":")[0].split("/")[0] or None


def port_of(value: str) -> Optional[int]:
    raw = strip_scheme(value)
    if not raw or raw.startswith("["):
        tail = raw.split("]")[-1] if raw.startswith("[") else raw
    else:
        tail = raw
    if ":" not in tail:
        return None
    tail = tail.split("/")[0]
    try:
        return int(tail.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return None


def normalize_node_url(
    value: Optional[str],
    default_scheme: str = "http",
    default_port: Optional[int] = None,
) -> Optional[str]:
    """Turn any operator input into a canonical ``scheme://host[:port]``.

    Accepts ``node-host``, ``node-host:11435``, ``http://node-host:11435``,
    ``http://10.0.0.42:11435``, ``https://gpu-01.example.net``. Trailing
    slashes and paths are dropped (the agent always serves the API at the
    root). Returns ``None`` for empty input.
    """
    value = (value or "").strip()
    if not value:
        return None
    scheme = default_scheme
    if "://" in value:
        scheme, _, rest = value.partition("://")
        scheme = scheme.strip() or default_scheme
    else:
        rest = value
    rest = rest.strip().strip("/")
    if not rest:
        return None
    if not rest.startswith("["):
        rest = rest.split("/")[0]
    else:  # keep an IPv6 literal intact
        rest = rest.split("/")[0]
    if default_port and not port_of(rest):
        rest = f"{rest}:{default_port}"
    return f"{scheme}://{rest}"


def node_base_url(node_url: Optional[str], port: int, fallback_scheme: str = "http") -> Optional[str]:
    """Base URL to call a node-agent on. ``node_url`` is authoritative.

    ``node_url`` may be:
      * empty/None -> caller falls back to the legacy ``fallback_host:port``.
      * a host without a port (`http://node-host`) -> the node's ``port`` is
        appended, so an operator only has to type the name.
      * a full URL (`https://gpu-01.example.net`) -> used as-is; a reverse proxy
        or TLS terminator in front of the agent stays possible.
    """
    if not node_url:
        return None
    normalized = normalize_node_url(node_url, default_scheme=fallback_scheme)
    if not normalized:
        return None
    parts = urlsplit(normalized)
    if not parts.port:
        netloc = f"{parts.netloc}:{port}"
        return urlunsplit((parts.scheme, netloc, "", "", "")).rstrip("/")
    return normalized.rstrip("/")


def is_auto_url(node_url: Optional[str]) -> bool:
    """True when the URL is a bare ``http://<ip>:port`` we could have derived."""
    host = host_of(node_url or "")
    if not host:
        return False
    if (node_url or "").startswith("https://"):
        return False
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def derive_node_url(source_host: str, port: int, scheme: str = "http") -> Optional[str]:
    """Build a node URL from a heartbeat's source address.

    Used only when the node carries no explicitly configured URL (or carries one
    the portal derived itself earlier). A local-only source address cannot be
    dialled back, so it yields ``None`` and the node keeps whatever it had.
    """
    source_host = (source_host or "").strip().strip("[]")
    if not source_host or source_host in LOCAL_HOSTS:
        return None
    scheme = "https" if (scheme or "").startswith("https") else "http"
    return f"{scheme}://{source_host}:{port}"


def source_host(request) -> Optional[str]:
    """Peer address of an incoming request, honouring ``X-Forwarded-For``.

    Behind a reverse proxy the socket address is the proxy; nginx sets
    ``X-Real-IP``/``X-Forwarded-For``, so those win (first hop only — the values
    are client-controlled and never trusted for anything but display).
    """
    for header in ("x-real-ip", "x-forwarded-for"):
        raw = request.headers.get(header) if hasattr(request, "headers") else None
        if raw:
            first = raw.split(",")[0].strip()
            if first:
                return first.strip("[]")
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client else None
    return host.strip("[]") if host else None


def request_base_url(request, fallback_port: Optional[int] = None) -> Optional[str]:
    """Public base URL of *this* portal, as the caller reached it.

    Used for payment return URLs, where hardcoding a host would break every
    other deployment. Falls back to ``X-Forwarded-*`` from the reverse proxy.
    """
    if request is None:
        return None
    headers = getattr(request, "headers", {}) or {}
    host = headers.get("x-forwarded-host") or headers.get("host")
    if not host:
        url = getattr(request, "url", None)
        host = url.netloc if url else None
    if not host:
        return None
    scheme = headers.get("x-forwarded-proto")
    if not scheme:
        scheme = getattr(getattr(request, "url", None), "scheme", None) or "http"
    scheme = scheme.split(",")[0].strip() or "http"
    return f"{scheme}://{host}".rstrip("/")
