#!/usr/bin/env python3
"""
GPU-Pool Node-Agent Installer

Fragt interaktiv ab, welches Inference-Backend der Node verwenden soll,
und generiert daraus die passende `.env` + `docker-compose.yml`.

Unterstützte Backends:
  ollama  -> lokales Ollama (Standard, /api/chat)
  lmstudio-> LM Studio (OpenAI-kompatibel, /v1/chat/completions)
  litellm -> LiteLLM Proxy (OpenAI-kompatibel, /v1/chat/completions)
  openai  -> beliebiger OpenAI-kompatibler Server (vLLM, llama.cpp…)

Die `docker-compose.yml` wird anhand der Auswahl generiert (GPU-Passthrough
nur wo sinnvoll, Backend-URL an den jeweiligen Server angepasst).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

# Schluessel, die dieses Skript besitzt und bei jedem Lauf auf den aktuellen
# Stand bringt. Alles andere in der .env (PORTAL_USER_KEY, NODE_ID, ...) bleibt
# unangetastet.
MANAGED_KEYS = (
    "PORTAL_URL",
    "ADVERTISE_HOST",
    "BACKEND",
    "OLLAMA_URL",
    "INFERENCE_URL",
    "AGENT_PORT",
    "AGENT_TRANSPORT",
)

BACKEND_MARKER_PREFIX = "# --- Backend:"

# Grundgeruest der Datei beim allerersten Lauf. Die Werte selbst setzt
# `upsert_env()` - so gibt es nur eine Stelle, die Keys schreibt.
INITIAL_ENV_LINES = (
    "# GPU-Pool Node-Agent Environment",
    "# Variante A (am einfachsten): der Agent registriert sich selbst.",
    "# Nur PORTAL_URL + PORTAL_USER_KEY (Account-API-Key) setzen - sonst nichts.",
    "PORTAL_URL=",
    "PORTAL_USER_KEY=dein-account-api-key",
    "# Optional: eigenen Namen festnageln statt erkannter IP (mDNS/DNS empfohlen).",
    "ADVERTISE_HOST=",
    "#",
    "# Variante B: Node im Portal registrieren und Werte hier eintragen.",
    "# NODE_ID=1",
    "# NODE_API_KEY=node_...",
)

BACKENDS = {
    "ollama": {
        "label": "Ollama (lokal, /api/chat)",
        "backend": "ollama",
        "default_url": "http://host.docker.internal:11434",
        "url_desc": "Ollama API-URL",
    },
    "lmstudio": {
        "label": "LM Studio (OpenAI-kompatibel, /v1/chat/completions)",
        "backend": "openai",
        "default_url": "http://host.docker.internal:1234",
        "url_desc": "LM Studio Server-URL",
    },
    "litellm": {
        "label": "LiteLLM Proxy (OpenAI-kompatibel, /v1/chat/completions)",
        "backend": "openai",
        "default_url": "http://host.docker.internal:4000",
        "url_desc": "LiteLLM Proxy-URL",
    },
    "openai": {
        "label": "Anderer OpenAI-kompatibler Server (vLLM, llama.cpp, …)",
        "backend": "openai",
        "default_url": "http://host.docker.internal:8000",
        "url_desc": "Server-URL (OpenAI-kompatibel)",
    },
}


def ask_choice(prompt: str, choices: list[str], default: int | None = None) -> str:
    print(prompt)
    for i, c in enumerate(choices, 1):
        marker = " (default)" if default == i else ""
        print(f"  {i}) {c}{marker}")
    while True:
        raw = input(f"  Auswahl [1-{len(choices)}]" + (f" oder Enter für {default}" if default else "") + "> ").strip()
        if raw == "" and default:
            return choices[default - 1]
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print("  Ungültig — bitte neu.")


def ask(prompt: str, default: str) -> str:
    val = input(f"{prompt} [{default}]: ").strip()
    return val or default


def read_env(path: str) -> dict[str, str]:
    """Liest KEY=VALUE aus einer vorhandenen .env (Kommentare zaehlen nicht)."""
    values: dict[str, str] = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def guess_backend_key(env: dict[str, str]) -> str | None:
    """Errät das bereits konfigurierte Backend (fuer den Vorschlagswert)."""
    backend = env.get("BACKEND", "").strip().lower()
    if backend == "ollama":
        return "ollama"
    if backend == "openai":
        url = env.get("INFERENCE_URL", "").rstrip("/")
        for key, spec in BACKENDS.items():
            if spec["backend"] == "openai" and url.endswith(":" + spec["default_url"].rsplit(":", 1)[-1]):
                return key
        return "openai"
    return None


def upsert_env(
    path: str,
    updates: dict[str, str],
    remove: list[str] | tuple[str, ...] = (),
) -> tuple[list[str], list[str], list[str]]:
    """Schreibt ``updates`` in die .env, ohne den Rest der Datei zu verlieren.

    Vorhandene Schluessel werden an ihrer Stelle ersetzt statt angehaengt,
    fehlende am Ende ergaenzt. Dubletten verwalteter Schluessel (Altlast
    frueherer Laeufe) fliegen raus. Alle nicht verwalteten Keys bleiben
    unangetastet. ``remove`` nennt Keys, die komplett verschwinden sollen
    (z. B. die URL des alten Backends).

    Rueckgabe: (ersetzte Keys, neu angelegte Keys, entfernte Keys).
    """
    pending = dict(updates)
    doomed = {k for k in remove if k not in pending}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    else:
        lines = [INITIAL_ENV_LINES[0], f"# Generiert am {datetime.now().isoformat()}", *INITIAL_ENV_LINES[1:]]

    replaced: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    seen: set[str] = set()
    marker_written = False
    out: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(BACKEND_MARKER_PREFIX):
            # Marker stammt vom Skript: genau einer, immer mit aktuellem Backend.
            if marker_written:
                continue
            marker_written = True
            out.append(f"{BACKEND_MARKER_PREFIX} {updates['BACKEND']} ---" if "BACKEND" in updates else line)
            continue
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in doomed:
                if key not in removed:
                    removed.append(key)
                continue
            if key in pending:
                out.append(f"{key}={pending.pop(key)}")
                replaced.append(key)
                seen.add(key)
                continue
            if key in seen:
                # Dublette eines bereits ersetzten Keys (alter Append-Lauf).
                continue
        out.append(line)

    if pending:
        if out and out[-1].strip():
            out.append("")
        if "BACKEND" in pending and not marker_written:
            out.append(f"{BACKEND_MARKER_PREFIX} {pending['BACKEND']} ---")
            marker_written = True
        for key in MANAGED_KEYS:
            if key in pending:
                out.append(f"{key}={pending[key]}")
                added.append(key)
                del pending[key]
        for key, value in pending.items():
            out.append(f"{key}={value}")
            added.append(key)

    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return replaced, added, removed


def build_compose(backend_key: str, backend_value: str, agent_port: int, url: str, nvidia: bool, transport: str) -> str:
    backend_env = (
        f"      - BACKEND=ollama\n      - OLLAMA_URL={url}"
        if backend_key == "ollama"
        else f"      - BACKEND=openai\n      - INFERENCE_URL={url}"
    )

    gpu = (
        """
    # GPU-Passthrough (NVIDIA)
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
"""
        if nvidia
        else ""
    )

    extra_hosts = (
        """
    # host.docker.internal: lokales Backend vom Container aus erreichen
    extra_hosts:
      - "host.docker.internal:host-gateway"
"""
    )

    transport_env = f"      - AGENT_TRANSPORT={transport}"
    ports_line = f"      - \"{agent_port}:{agent_port}\"  # Health-Check / Inbound (HTTP-Transport)"

    # Keine feste externe IP: das Portal wird allein ueber PORTAL_URL angesprochen.
    # Eigene Adresse: leer = automatisch (Outbound-IP). Ein DNS-/mDNS-Name ueberlebt
    # einen DHCP-Lease-Wechsel, eine IP nicht.
    return f"""# CoMesh Node-Agent (automatisch generiert vom Setup-Skript)
services:
  agent:
    build: .
    container_name: gpu-pool-agent
    restart: unless-stopped

    environment:
      - PORTAL_URL=${{PORTAL_URL}}
      # Variante A: Selbst-Registrierung (nur diese zwei Zeilen noetig)
      - PORTAL_USER_KEY=${{PORTAL_USER_KEY:-}}
      # Variante B: Node im Portal registrieren und Werte hier eintragen
      - NODE_ID=${{NODE_ID:-}}
      - NODE_API_KEY=${{NODE_API_KEY:-}}
      # Eigene Erreichbarkeit: leer = automatisch erkannt
      - ADVERTISE_HOST=${{ADVERTISE_HOST:-}}
      - NODE_NAME=${{NODE_NAME:-}}
      - NODE_STATE_FILE=/data/node-state.json
      - AGENT_PORT={agent_port}
      - HEARTBEAT_SEC=${{HEARTBEAT_SEC:-30}}
      - LOG_LEVEL=${{LOG_LEVEL:-INFO}}
{backend_env}
{transport_env}

    ports:
{ports_line}

    # Node-Credentials ueberleben einen Rebuild (kein zweiter Node-Eintrag).
    volumes:
      - agent_state:/data

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:{agent_port}/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
{gpu}{extra_hosts}
volumes:
  agent_state:"""


def main() -> None:
    print("=" * 62)
    print("GPU-Pool Node-Agent Setup")
    print("Konfiguriert dieses Node als Contributor im GPU-Pool")
    print("=" * 62)

    # Vorhandene .env einlesen: ihre Werte sind die Vorschlagswerte, damit ein
    # zweiter Lauf die Konfiguration nicht mit den Platzhalter-Defaults
    # ueberschreibt.
    env_path = ".env"
    existing = read_env(env_path)

    labels = [b["label"] for b in BACKENDS.values()]
    known_backend = guess_backend_key(existing)
    default_index = list(BACKENDS).index(known_backend) + 1 if known_backend else 1
    choice = ask_choice(
        "\nWelches GPU-Backend nutzt dieser Node?",
        labels,
        default=default_index,
    )
    # ask_choice returns the chosen label — map back to the backend key
    backend_key = [k for k, v in BACKENDS.items() if v["label"] == choice][0]
    b = BACKENDS[backend_key]

    url_default = existing.get(
        "OLLAMA_URL" if b["backend"] == "ollama" else "INFERENCE_URL",
        b["default_url"],
    ) or b["default_url"]
    url = ask(f"\n{b['url_desc']} (z. B. {b['default_url']}):", url_default).rstrip("/")

    portal_url = ask(
        "\nPortal-URL (Name oder IP des Portal-Hosts; Name bevorzugt, ueberlebt DHCP-Wechsel):",
        existing.get("PORTAL_URL") or "http://portal-host:8765",
    ).rstrip("/")
    advertise = ask(
        "\nName/IP, unter der das Portal DIESEN Node erreichen soll (leer = automatisch erkennen):",
        existing.get("ADVERTISE_HOST", ""),
    ).strip()

    port_default = existing.get("AGENT_PORT", "").strip()
    if not port_default.isdigit():
        port_default = "11435"
    while True:
        raw_port = ask("Port für den Node-Agent (inbound):", port_default)
        if raw_port.isdigit():
            agent_port = int(raw_port)
            break
        print("  Ungültig — bitte eine Portnummer.")

    # WebSocket-Transport ist Standard (kein offener Inbound-Port nötig)
    transport = ask_choice(
        "\nTransport für die Verbindung zum Portal?",
        ["WebSocket (empfohlen, outbound, kein offener Port nötig)", "HTTP (offener Port)"],
        default=2 if existing.get("AGENT_TRANSPORT", "").strip().lower() == "http" else 1,
    )
    transport_val = "ws" if transport.startswith("WebSocket") else "http"

    nvidia = ask_choice(
        "\nHat dieser Node eine NVIDIA-GPU, die durchgereicht werden soll?",
        ["Ja, NVIDIA-GPU (GPU-Passthrough)", "Nein / anders (CPU oder AMD)"],
        default=2,
    )
    nvidia_bool = nvidia.startswith("Ja")

    # Dateien schreiben: die verwalteten Keys werden ersetzt, nicht angehaengt.
    url_key = "OLLAMA_URL" if b["backend"] == "ollama" else "INFERENCE_URL"
    stale_url_key = "INFERENCE_URL" if url_key == "OLLAMA_URL" else "OLLAMA_URL"
    updates = {
        "PORTAL_URL": portal_url,
        "ADVERTISE_HOST": advertise,
        "BACKEND": b["backend"],
        url_key: url,
        "AGENT_PORT": str(agent_port),
        "AGENT_TRANSPORT": transport_val,
    }
    if existing:
        print(
            f"\n⚠️  {env_path} existiert bereits — ich ersetze die Keys dieses Skripts "
            f"({', '.join(sorted(updates))}) und lasse alle anderen unangetastet."
        )
    replaced, added, removed = upsert_env(env_path, updates, remove=[stale_url_key])

    compose = build_compose(backend_key, b["backend"], agent_port, url, nvidia_bool, transport_val)
    with open("docker-compose.yml", "w") as f:
        f.write(compose)

    if replaced:
        print(f"\n  .env: ersetzt  {', '.join(replaced)}")
    if added:
        print(f"  .env: ergaenzt {', '.join(added)}")
    if removed:
        print(f"  .env: entfernt {', '.join(removed)} (Backend-Wechsel)")

    print("\n✅ Fertig!")
    print(f"  Backend:        {backend_key} ({b['backend']})")
    print(f"  Backend-URL:    {url}")
    print(f"  Agent-Port:     {agent_port}")
    print(f"  Transport:      {transport_val}")
    print(f"  NVIDIA-Passthr: {'ja' if nvidia_bool else 'nein'}")
    print(f"\n  .env + docker-compose.yml geschrieben.")
    print(f"\n  Nächste Schritte:")
    print(f"    1. In .env PORTAL_USER_KEY auf einen Account-API-Key setzen")
    print(f"       (Variante A: der Agent registriert sich selbst)")
    print(f"       oder NODE_ID + NODE_API_KEY aus dem Portal eintragen (Variante B)")
    print(f"    2. Konfiguration pruefen: docker compose run --rm agent python agent.py --check")
    print(f"    3. docker compose up -d && docker compose logs -f agent")


if __name__ == "__main__":
    main()
