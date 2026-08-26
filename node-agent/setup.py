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

    return f"""# GPU-Pool Node-Agent (automatisch generiert vom Setup-Skript)
services:
  agent:
    build: .
    container_name: gpu-pool-agent
    restart: unless-stopped

    environment:
      - NODE_ID=${{NODE_ID}}
      - NODE_API_KEY=${{NODE_API_KEY}}
      - PORTAL_URL=${{PORTAL_URL}}
      - AGENT_PORT={agent_port}
      - HEARTBEAT_SEC=${{HEARTBEAT_SEC:-30}}
      - LOG_LEVEL=${{LOG_LEVEL:-INFO}}
{backend_env}
{transport_env}

    ports:
{ports_line}

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:{agent_port}/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
{gpu}{extra_hosts}"""


def main() -> None:
    print("=" * 62)
    print("GPU-Pool Node-Agent Setup")
    print("Konfiguriert dieses Node als Contributor im GPU-Pool")
    print("=" * 62)

    backend_key = ask_choice(
        "\nWelches GPU-Backend nutzt dieser Node?",
        [b["label"] for b in BACKENDS.values()],
        default=1,
    )
    # ask_choice returns the chosen label — map back to the backend key
    backend_key = [k for k, v in BACKENDS.items() if v["label"] == backend_key][0]
    b = BACKENDS[backend_key]

    url = ask(f"\n{b['url_desc']} (z. B. {b['default_url']}):", b["default_url"]).rstrip("/")

    agent_port = int(ask("Port für den Node-Agent (inbound):", "8080"))

    # WebSocket-Transport ist Standard (kein offener Inbound-Port nötig)
    transport = ask_choice(
        "\nTransport für die Verbindung zum Portal?",
        ["WebSocket (empfohlen, outbound, kein offener Port nötig)", "HTTP (offener Port)"],
        default=1,
    )
    transport_val = "ws" if transport.startswith("WebSocket") else "http"

    nvidia = ask_choice(
        "\nHat dieser Node eine NVIDIA-GPU, die durchgereicht werden soll?",
        ["Ja, NVIDIA-GPU (GPU-Passthrough)", "Nein / anders (CPU oder AMD)"],
        default=2,
    )
    nvidia_bool = nvidia.startswith("Ja")

    # Dateien schreiben
    env_path = ".env"
    exists = os.path.exists(env_path)
    if exists:
        print(f"\n⚠️  {env_path} existiert bereits — ich überschreibe nur die Backend-Zeilen.")
    with open(env_path, "a") as f:
        if not exists:
            f.write("# GPU-Pool Node-Agent Environment\n")
            f.write(f"# Generiert am {__import__('datetime').datetime.now().isoformat()}\n")
            f.write(f"NODE_ID=setze-node-id\n")
            f.write(f"NODE_API_KEY=setze-node-api-key\n")
            f.write(f"PORTAL_URL=http://100.126.79.111:8765\n")
        f.write(f"\n# --- Backend: {backend_key} ---\n")
        f.write(f"BACKEND={b['backend']}\n")
        if b["backend"] == "ollama":
            f.write(f"OLLAMA_URL={url}\n")
        else:
            f.write(f"INFERENCE_URL={url}\n")
        f.write(f"AGENT_PORT={agent_port}\n")
        f.write(f"AGENT_TRANSPORT={transport_val}\n")

    compose = build_compose(backend_key, b["backend"], agent_port, url, nvidia_bool, transport_val)
    with open("docker-compose.yml", "w") as f:
        f.write(compose)

    print("\n✅ Fertig!")
    print(f"  Backend:        {backend_key} ({b['backend']})")
    print(f"  Backend-URL:    {url}")
    print(f"  Agent-Port:     {agent_port}")
    print(f"  Transport:      {transport_val}")
    print(f"  NVIDIA-Passthr: {'ja' if nvidia_bool else 'nein'}")
    print(f"\n  .env + docker-compose.yml geschrieben.")
    print(f"\n  Nächste Schritte:")
    print(f"    1. In .env NODE_ID und NODE_API_KEY setzen (aus dem Portal)")
    print(f"    2. docker compose up -d")
    print(f"    3. docker compose logs -f agent")


if __name__ == "__main__":
    main()
