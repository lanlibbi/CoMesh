"""
GPU-Pool Node-Agent.

Three transports (Phase 1+2):

  HTTP (default, AGENT_TRANSPORT=http):
    - Runs a FastAPI server on AGENT_PORT (default 11435) that accepts
      forwarded chat completions and pushes periodic HTTP heartbeats.
    - This is the v1 behavior, UNCHANGED in Phase 1+2. Still used as
      fallback by the pool when the WS is down (HTTP path is bit-identical).

  WS (AGENT_TRANSPORT=ws):
    - Opens an OUTBOUND WebSocket to ws://<portal>/agent/connect.
    - Sends a JSON ping every WS_HEARTBEAT_SEC (default 15s) with
      vram/active_jobs/uptime. Auto-reconnects with exponential
      backoff (1s, 2s, 4s, ..., capped at WS_RECONNECT_MAX_SEC).
    - No inbound port required. The HTTP server does NOT start.
    - Phase 2: in WS mode, the agent also handles `{"type": "job", ...}`
      frames from the pool. It forwards the payload to its local Ollama
      and replies with `{"type": "job_result", ...}`. STREAMING is NOT
      supported in Phase 2 (payload.stream=true is treated as False and
      we return the full response) — streaming comes in Phase 3.

Configuration via environment variables (or a .env file):

  PORTAL_URL       Base URL of the portal. No default on purpose — an agent that
                   silently talks to localhost is worse than one that stops and
                   says so. Example: http://portal-host:8765
  NODE_ID          Numeric id of the registered GpuNode. Leave empty to let the
                   agent register itself (see REGISTER_* below).
  NODE_API_KEY     The agent_api_key issued by the portal. Also optional when the
                   agent registers itself.
  ADVERTISE_HOST   Host (name or IP) the portal should dial. Empty = detect at
                   runtime (outbound IP, else hostname). Prefer a DNS/mDNS name:
                   an IP breaks when the DHCP lease changes.
  PORTAL_USER_KEY  API key of a CoMesh account, used only for self-registration
                   (POST /nodes/register). Not needed once NODE_ID/NODE_API_KEY
                   are set.
  NODE_NAME        Display name for a self-registered node (default: hostname).
  NODE_GPU_TYPE    GPU label for a self-registered node (default: probed via NVML).
  NODE_VRAM_GB     VRAM for a self-registered node (default: probed via NVML).
                   Set it explicitly when there is no NVIDIA GPU (Apple Silicon:
                   the unified memory size); otherwise 1 GB is assumed and the
                   pool will never route a job to this node.
  NODE_SHARED_SECRET  Shared secret with the portal. The portal sends it as
                   `X-Node-Secret` on every request; without it the agent
                   answers 401. Empty = legacy mode, open to anyone who can
                   reach the port (a loud warning is logged at start).
  OLLAMA_URL       Local Ollama URL (default: http://localhost:11434)
  AGENT_PORT       Port to listen on (default: 11435)
  HEARTBEAT_SEC    Heartbeat interval in HTTP mode (default: 30)
  AGENT_TRANSPORT  "http" (default) or "ws". The installer sets "ws": outbound
                   only, no inbound port, no reachable address needed.
  WS_HEARTBEAT_SEC Ping interval in WS mode (default: 15)
  WS_RECONNECT_MAX_SEC  Cap for reconnect backoff (default: 30)
  NODE_STATE_FILE  Where self-registration keeps node_id/node_api_key.
                   Default: <user config dir>/node-state.json (NOT /data — the
                   container sets that path explicitly in its Dockerfile).
  COMESH_AGENT_ENV Config file to read instead of the default lookup. Without it
                   the agent reads <user config dir>/agent.env, then .env in the
                   working directory. Real environment variables always win.
  AGENT_LOG_FILE   Optional file to log to (rotated, 2 MB x 3). Needed under
                   launchd/schtasks, where nothing captures stdout.

Run:
  # HTTP mode (unchanged)
  docker run -d --name gpu-pool-agent \
    --gpus all \
    -e PORTAL_URL=http://portal-host:8765 \
    -e NODE_ID=1 \
    -e NODE_API_KEY=*** \
    -p 11435:11435 \
    gpu-pool-node-agent

  # WS mode (Phase 1; no inbound port published)
  docker run -d --name gpu-pool-agent-ws \
    --gpus all \
    -e AGENT_TRANSPORT=ws \
    -e PORTAL_URL=http://portal-host:8765 \
    -e NODE_ID=1 \
    -e NODE_API_KEY=*** \
    gpu-pool-node-agent

  # Configuration check — prints which address the portal would use, then exits
  python agent.py --check
"""
import asyncio
import hmac
import json
import logging
import logging.handlers
import os
import sys
import time
import warnings
from typing import List, Optional

# FastAPI meldet beim Import "@app.on_event is deprecated". Der Hinweis ist
# berechtigt, aber er erscheint VOR jeder Ausgabe — auch bei `--version` und
# `--check`, deren Ausgabe der Installer einliest. Deshalb genau diese eine
# Meldung stumm schalten (nicht alle Deprecation-Warnungen). Die Meldung beginnt
# mit einem Zeilenumbruch, darum `\s*` statt `.*` am Anfang.
warnings.filterwarnings("ignore", message=r"\s*on_event is deprecated")

import httpx
import psutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from netinfo import (
    detect_outbound_ip,
    gpu_summary,
    local_hostname,
    resolve_advertise_host,
)

# pynvml is optional in non-GPU dev environments
try:
    import pynvml
    pynvml.nvmlInit()
    _HAVE_NVML = True
except Exception:
    _HAVE_NVML = False

# ----------------------------------------------------------------------------
# Version, Ordner, Protokoll
# ----------------------------------------------------------------------------
# Der Agent laeuft auch als Einzelbinary (PyInstaller, ohne Python und ohne
# Quellbaum auf der Maschine). Dann zeigt `__file__` in ein temporaeres
# Entpackverzeichnis, und ein relativer Pfad zu `assets/` oder `.env` ist
# wertlos. Deshalb: alles, was der Agent zur Laufzeit braucht, haengt an
# Umgebungsvariablen mit einem Standard im **Benutzerverzeichnis**.
AGENT_VERSION_FALLBACK = "0.6.0"


def _bundle_dir() -> str:
    """Ordner der mitgelieferten Dateien — im Binary das Entpackverzeichnis."""
    return getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))


def _read_version() -> str:
    """Version aus der mitgelieferten VERSION-Datei, sonst der feste Ersatzwert."""
    for candidate in (
        os.path.join(_bundle_dir(), "VERSION"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "VERSION"),
    ):
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                value = fh.read().strip()
            if value:
                return value
        except OSError:
            continue
    return AGENT_VERSION_FALLBACK


AGENT_VERSION = _read_version()


def _user_config_dir() -> str:
    """Benutzer-Konfigurationsordner — dort schreibt der Installer `agent.env`.

    Linux/macOS: ``~/.config/comesh`` (bzw. ``$XDG_CONFIG_HOME/comesh``)
    Windows:     ``%LOCALAPPDATA%\\CoMesh``
    Der Container setzt die Variablen ausdruecklich und ist davon nicht betroffen.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local"
        )
        return os.path.join(base, "CoMesh")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "comesh")


def _setup_logging() -> None:
    """Protokoll auf stdout und — wenn ``AGENT_LOG_FILE`` gesetzt ist — in eine Datei.

    Die Datei ist der einzige Weg, unter launchd/schtasks zu sehen, was der Agent
    tut (dort gibt es kein Journal). Sie wird rotiert und enthaelt keine
    Geheimnisse: der Agent protokolliert Node-Id und Namen, nie Schluessel.
    """
    fmt = logging.Formatter("%(asctime)s [agent] %(levelname)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        if getattr(handler, "_comesh", False):
            root.removeHandler(handler)
            handler.close()
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    stream._comesh = True
    root.addHandler(stream)
    # httpx protokolliert jede Anfrage auf INFO ("HTTP Request: GET …"). Für ein
    # Dienstprotokoll, das ein Provider bei Problemen liest, ist das Rauschen:
    # die Zeilen, die zählen, sind Registrierung, WS-Verbindung und Fehler.
    for noisy in ("httpx", "httpcore", "uvicorn.access", "websockets.client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    path = os.environ.get("AGENT_LOG_FILE", "").strip()
    if not path:
        return
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        file_handler._comesh = True
        root.addHandler(file_handler)
    except OSError as exc:  # Protokoll ist Beiwerk, nie Startbedingung
        logging.getLogger("node-agent").warning(f"Cannot write AGENT_LOG_FILE {path}: {exc}")


_setup_logging()
log = logging.getLogger("node-agent")

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
# No default portal URL: a wrong default silently sends heartbeats (and API keys)
# to the wrong host. Empty means "not configured" and is reported as such.
PORTAL_URL = os.environ.get("PORTAL_URL", "").rstrip("/")
if PORTAL_URL and "://" not in PORTAL_URL:
    PORTAL_URL = "http://" + PORTAL_URL  # tolerate "portal-host:8765"

NODE_ID = str(os.environ.get("NODE_ID", "") or "").strip()
NODE_API_KEY = os.environ.get("NODE_API_KEY", "")

# --- self-registration (LANA-89) --------------------------------------------
# With an account key present and no NODE_ID yet, the agent registers itself and
# keeps the returned node credentials in a state file, so the operator never has
# to copy values between portal and host. That is what makes a one-variable
# setup work on a fresh DHCP network.
PORTAL_USER_KEY = os.environ.get("PORTAL_USER_KEY", "")
NODE_NAME = os.environ.get("NODE_NAME", "")
NODE_GPU_TYPE = os.environ.get("NODE_GPU_TYPE", "")
NODE_VRAM_GB = os.environ.get("NODE_VRAM_GB", "")
# Gemeinsames Geheimnis Portal <-> Node (Sicherheitsfix 03.11.2026).
# Das Portal schickt es als `X-Node-Secret` bei jeder Anfrage; ohne den Kopf
# antwortet der Agent 401. Ist die Variable leer, bleibt das alte Verhalten
# bestehen (der Agent ist dann ein offener Modell-Proxy fuer jeden, der den
# Port erreicht) — beim Start wird davor gewarnt.
NODE_SHARED_SECRET = os.environ.get("NODE_SHARED_SECRET", "").strip()
SECRET_HEADER = "X-Node-Secret"
# Zustandsdatei mit den selbst registrierten Node-Zugangsdaten. Standard ist
# seit dem Einzelbinary ein Pfad im **Benutzerverzeichnis**: `/data` gibt es nur
# im Container (der setzt die Variable ausdruecklich im Dockerfile).
NODE_STATE_FILE = (
    os.environ.get("NODE_STATE_FILE", "").strip()
    or os.path.join(_user_config_dir(), "node-state.json")
)
NODE_HOURLY_RATE = os.environ.get("NODE_HOURLY_RATE", "")
# Host the portal should dial. Empty = detected at runtime (see netinfo).
ADVERTISE_HOST = os.environ.get("ADVERTISE_HOST", "").strip()
# How the agent reaches the portal. Same env var the portal reads, so an operator
# can pin the exact host (usually only needed with a reverse proxy).
_PORTAL_TRY_ADVERTISE = os.environ.get("PORTAL_TRY_ADVERTISE_HOST", "1").strip().lower() not in ("0", "false", "no")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
# Which inference backend this node exposes:
#   ollama  -> local Ollama (default, legacy) — translates OpenAI->/api/chat
#   openai  -> any OpenAI-compatible self-hosted server (LM Studio, LiteLLM, vLLM…)
#              — forwards the OpenAI body directly to /v1/chat/completions
BACKEND = os.environ.get("BACKEND", "ollama").lower().strip()
# For BACKEND=openai: the base URL of the OpenAI-compatible server.
# Falls back to OLLAMA_URL so existing installs keep working when unset.
INFERENCE_URL = os.environ.get("INFERENCE_URL", OLLAMA_URL).rstrip("/")
AGENT_PORT = int(os.environ.get("AGENT_PORT", "11435"))
HEARTBEAT_SEC = int(os.environ.get("HEARTBEAT_SEC", "30"))

# Backend capabilities used by the health check / list-models probe.
def backend_list_url() -> str:
    """URL used to probe 'is the backend up + which models'. OpenAI-compatible servers expose /v1/models."""
    return f"{INFERENCE_URL}/v1/models" if BACKEND == "openai" else f"{INFERENCE_URL}/api/tags"

def backend_chat_url() -> str:
    """URL for the chat-completions call. Ollama uses its native /api/chat; OpenAI-compatible use /v1/chat/completions."""
    return f"{INFERENCE_URL}/v1/chat/completions" if BACKEND == "openai" else f"{INFERENCE_URL}/api/chat"


async def _infer(payload: dict, timeout: float = 300.0) -> dict:
    """Run one inference against the configured backend and return an OpenAI-shaped response.

    Accepts an OpenAI-shaped /v1/chat/completions body (``model``, ``messages``,
    ``temperature``, ``max_tokens``, ``stream``). Non-streaming; for chunked
    delivery see `_infer_streaming` (Phase 3, BACKEND=ollama only).

    - BACKEND=ollama: translates to Ollama's /api/chat (options.temperature/num_predict).
    - BACKEND=openai: forwards the OpenAI body verbatim to /v1/chat/completions
      (LM Studio, LiteLLM, vLLM, llama.cpp server, …).
    """
    stream = bool(payload.get("stream"))
    if BACKEND == "openai":
        # Forward the OpenAI body as-is; OpenAI-compatible servers accept it natively.
        oa_payload = {
            "model": payload.get("model", ""),
            "messages": payload.get("messages", []),
            "stream": False,
        }
        if "temperature" in payload and payload["temperature"] is not None:
            oa_payload["temperature"] = payload["temperature"]
        if payload.get("max_tokens") is not None:
            oa_payload["max_tokens"] = payload["max_tokens"]
        # Werkzeuge unverändert weiterreichen (OpenAI-Backends verstehen das direkt).
        if payload.get("tools"):
            oa_payload["tools"] = payload["tools"]
            if payload.get("tool_choice") is not None:
                oa_payload["tool_choice"] = payload["tool_choice"]
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(backend_chat_url(), json=oa_payload)
            r.raise_for_status()
            return r.json()
    # ---- Ollama native ----
    ollama_payload = {
        "model": payload.get("model", ""),
        "messages": payload.get("messages", []),
        "stream": False,
        "options": {},
    }
    if "temperature" in payload and payload["temperature"] is not None:
        ollama_payload["options"]["temperature"] = payload["temperature"]
    if payload.get("max_tokens") is not None:
        ollama_payload["options"]["num_predict"] = payload["max_tokens"]
    # Ollama nimmt `tools` im OpenAI-Schema direkt an.
    if payload.get("tools"):
        ollama_payload["tools"] = payload["tools"]
        if payload.get("tool_choice") is not None:
            ollama_payload["tool_choice"] = payload["tool_choice"]
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(backend_chat_url(), json=ollama_payload)
        r.raise_for_status()
        data = r.json()
    msg = data.get("message", {}) or {}
    usage = data.get("usage") or {}
    return {
        "id": f"chatcmpl-agent-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.get("model", ""),
        "choices": [{
            "index": 0,
            "message": {
                "role": msg.get("role", "assistant"),
                "content": msg.get("content", ""),
                "tool_calls": msg.get("tool_calls"),
            },
            "finish_reason": "tool_calls" if msg.get("tool_calls")
            else (data.get("done_reason") or "stop"),
        }],
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens") or data.get("prompt_eval_count") or 0,
            "completion_tokens": usage.get("completion_tokens") or data.get("eval_count") or 0,
            "total_tokens": (usage.get("total_tokens") or 0)
                or ((data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0)),
        },
        "_agent": {"node_id": NODE_ID, "gpu": get_gpu_info()},
    }


# ----------------------------------------------------------------------------
# Phase 3 (LANA-114): chunked inference. See `_infer_streaming`.
# ----------------------------------------------------------------------------
async def _infer_streaming(payload: dict, timeout: float, send_delta) -> dict:
    """Chunked upstream inference, BACKEND=ollama only.

    Streams Ollama's NDJSON /api/chat response and forwards every non-empty
    `message.content` delta to `send_delta(delta)` (an async callable that
    emits one `job_result_chunk` WS frame). Returns the same OpenAI-shaped
    envelope as `_infer`, with `message.content` being the exact
    concatenation of the emitted deltas and usage aggregated from the final
    `done` line: the final `job_result` frame stays binding, chunk frames
    are advisory.

    Raises like `_infer` (httpx errors bubble up). If the stream breaks
    mid-way after deltas were already sent, the caller reports ok:false in
    `job_result` and the pool falls back to HTTP; clients that received
    partial chunks must discard them (final/error frame is binding).
    """
    ollama_payload = {
        "model": payload.get("model", ""),
        "messages": payload.get("messages", []),
        "stream": True,
        "options": {},
    }
    if "temperature" in payload and payload["temperature"] is not None:
        ollama_payload["options"]["temperature"] = payload["temperature"]
    if payload.get("max_tokens") is not None:
        ollama_payload["options"]["num_predict"] = payload["max_tokens"]

    prompt_tokens = 0
    completion_tokens = 0
    content_parts: list = []

    async def _track(delta: str) -> None:
        content_parts.append(delta)
        await send_delta(delta)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", backend_chat_url(), json=ollama_payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                delta = (data.get("message") or {}).get("content") or ""
                if delta:
                    await _track(delta)
                if data.get("done"):
                    prompt_tokens = data.get("prompt_eval_count") or 0
                    completion_tokens = data.get("eval_count") or 0
    return {
        "id": f"chatcmpl-agent-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.get("model", ""),
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "".join(content_parts)},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "_agent": {"node_id": NODE_ID, "gpu": get_gpu_info()},
    }


# Phase 1: outbound transport. Default = "http" (legacy FastAPI server + HTTP heartbeats).
# Set AGENT_TRANSPORT=ws to use the outbound WebSocket client (no inbound port needed).
AGENT_TRANSPORT = os.environ.get("AGENT_TRANSPORT", "http").lower().strip()
# WS-specific tunables
WS_HEARTBEAT_SEC = int(os.environ.get("WS_HEARTBEAT_SEC", "15"))


# ---------------------------------------------------------------------------
# .env support for direct runs
# ---------------------------------------------------------------------------
# The interactive installer writes .env next to docker-compose.yml. Nobody reads
# that file when the agent is started directly (`python agent.py --check`, which
# docs/node-agent.md advertises), so the check reported "PORTAL_URL is unset"
# although .env set it. Compose injects the values itself, so this only adds a
# path for direct runs — and a real environment variable always wins.
def _load_env_file(path: str = ".env") -> None:
    """Read KEY=VALUE lines from *path* into os.environ, never overriding."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw_lines = fh.readlines()
    except OSError:
        return
    for raw in raw_lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _env_file_candidates() -> List[str]:
    """Wo der Agent seine Konfiguration sucht, in dieser Reihenfolge.

    Das Binary laeuft unter launchd/systemd/schtasks, und dort ist das
    Arbeitsverzeichnis beliebig (launchd: ``/``, schtasks: ``C:\\Windows\\System32``).
    Ein `.env` im Arbeitsverzeichnis ist deshalb kein verlaesslicher Ort. Gesucht
    wird darum zuerst der Ort, den der Installer schreibt:

      1. ``$COMESH_AGENT_ENV`` (ausdrueckliche Angabe, auch fuer Tests)
      2. ``<Benutzer-Konfigurationsordner>/agent.env``
      3. ``.env`` im Arbeitsverzeichnis (bisheriges Verhalten, Docker/Entwicklung)

    Es gewinnt die **erste vorhandene** Datei; echte Umgebungsvariablen schlagen
    jede Datei, weil `_load_env_file` vorhandene Schluessel nicht ueberschreibt.
    """
    explicit = os.environ.get("COMESH_AGENT_ENV", "").strip()
    if explicit:
        return [explicit]
    return [
        os.path.join(_user_config_dir(), "agent.env"),
        os.path.join(os.getcwd(), ".env"),
    ]


def _load_agent_env() -> None:
    """Die erste vorhandene Konfigurationsdatei laden (siehe `_env_file_candidates`)."""
    for candidate in _env_file_candidates():
        if os.path.isfile(candidate):
            _load_env_file(candidate)
            os.environ["COMESH_AGENT_ENV_USED"] = candidate
            return


def _refresh_config_from_environ() -> None:
    """Re-read the config globals above after _load_env_file() ran.

    Same expressions as the module-level config block, applied a second time so
    values that only exist in .env take effect for a direct run.
    """
    global PORTAL_URL, NODE_ID, NODE_API_KEY, PORTAL_USER_KEY, NODE_NAME
    global NODE_GPU_TYPE, NODE_VRAM_GB, NODE_SHARED_SECRET, ADVERTISE_HOST, OLLAMA_URL, BACKEND
    global INFERENCE_URL, AGENT_PORT, HEARTBEAT_SEC, AGENT_TRANSPORT, WS_HEARTBEAT_SEC
    global NODE_STATE_FILE
    PORTAL_URL = os.environ.get("PORTAL_URL", "").rstrip("/")
    if PORTAL_URL and "://" not in PORTAL_URL:
        PORTAL_URL = "http://" + PORTAL_URL
    NODE_ID = str(os.environ.get("NODE_ID", "") or "").strip()
    NODE_API_KEY = os.environ.get("NODE_API_KEY", "")
    PORTAL_USER_KEY = os.environ.get("PORTAL_USER_KEY", "")
    NODE_NAME = os.environ.get("NODE_NAME", "")
    NODE_GPU_TYPE = os.environ.get("NODE_GPU_TYPE", "")
    NODE_VRAM_GB = os.environ.get("NODE_VRAM_GB", "")
    NODE_SHARED_SECRET = os.environ.get("NODE_SHARED_SECRET", "").strip()
    ADVERTISE_HOST = os.environ.get("ADVERTISE_HOST", "").strip()
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    BACKEND = os.environ.get("BACKEND", "ollama").lower().strip()
    INFERENCE_URL = os.environ.get("INFERENCE_URL", OLLAMA_URL).rstrip("/")
    AGENT_PORT = int(os.environ.get("AGENT_PORT", "11435"))
    HEARTBEAT_SEC = int(os.environ.get("HEARTBEAT_SEC", "30"))
    AGENT_TRANSPORT = os.environ.get("AGENT_TRANSPORT", "http").lower().strip()
    WS_HEARTBEAT_SEC = int(os.environ.get("WS_HEARTBEAT_SEC", "15"))
    NODE_STATE_FILE = (
        os.environ.get("NODE_STATE_FILE", "").strip()
        or os.path.join(_user_config_dir(), "node-state.json")
    )
WS_RECONNECT_MAX_SEC = int(os.environ.get("WS_RECONNECT_MAX_SEC", "30"))


def _warn_if_unconfigured() -> None:
    """Beim Start sagen, wenn Zugangsdaten fehlen — nicht beim Import.

    Die Warnung stand früher auf Modulebene und erschien damit auch bei
    `--version`/`--check`; der Installer liest deren Ausgabe und bekam den
    Hinweis in die Versionszeile gemischt. Sie läuft NACH der
    Selbstregistrierung: vorher ist „keine Zugangsdaten" normal und die Meldung
    würde bei jedem frischen Node-Start fälschlich Alarm schlagen.
    """
    if not NODE_ID or not NODE_API_KEY:
        log.warning("NODE_ID / NODE_API_KEY not set — heartbeats and auth will not work.")

# Where this agent is reachable. Resolved once at start (ADVERTISE_HOST, else the
# outbound IP, else the hostname) and re-sent with every heartbeat so the portal
# can adopt it when it has no explicit address for this node.
ADVERTISE = os.environ.get("ADVERTISE_HOST", "").strip()


def advertised_host() -> str:
    """The host we tell the portal to dial. Resolved lazily, cached after the first call."""
    global ADVERTISE
    if not ADVERTISE:
        ADVERTISE = resolve_advertise_host(env_var="ADVERTISE_HOST")
        log.info(f"Advertise host detected: {ADVERTISE} (set ADVERTISE_HOST to pin a name)")
    return ADVERTISE

# Track in-flight requests so the agent can report active_jobs
_active_jobs = 0
_start_time = time.time()


# ----------------------------------------------------------------------------
# GPU info
# ----------------------------------------------------------------------------
def get_gpu_info() -> dict:
    """Return {vram_total, vram_used, utilization, name, active_jobs} or a stub."""
    info = {
        "vram_total": 0,
        "vram_used": 0,
        "vram_total_gb": 0.0,
        "vram_used_gb": 0.0,
        "utilization": 0.0,
        "name": "unknown",
        "active_jobs": _active_jobs,
        "host": {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "mem_percent": psutil.virtual_memory().percent,
        },
    }
    if not _HAVE_NVML:
        return info
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        info.update({
            "name": name if isinstance(name, str) else name.decode("utf-8", "ignore"),
            "vram_total": int(mem.total),
            "vram_used": int(mem.used),
            "vram_total_gb": round(mem.total / 1024**3, 2),
            "vram_used_gb": round(mem.used / 1024**3, 2),
            "utilization": util.gpu / 100.0,
        })
    except Exception as e:
        log.debug(f"NVML read failed: {e}")
    return info


def vram_report() -> tuple:
    """(vram_gb, source) — the VRAM this node advertises, and where it comes from.

    source is one of:
      * "override" — NODE_VRAM_GB was set explicitly (authoritative)
      * "detected" — read from NVML
      * "assumed"  — nothing detected and nothing declared: 1 GB

    The third case is the one that used to fail silently: the portal accepted
    1 GB, the VRAM gate in pool.find_best_node then refused every model, and
    the node sat online without ever getting a job. It is now reported to the
    portal (gpu_nodes.vram_source) so the operator sees *why*.
    """
    if NODE_VRAM_GB:
        try:
            return max(1, int(float(NODE_VRAM_GB))), "override"
        except ValueError:
            log.warning(f"NODE_VRAM_GB={NODE_VRAM_GB!r} is not a number — ignored")
    detected = int(gpu_summary().get("vram_gb") or 0)
    if detected > 0:
        return detected, "detected"
    return 1, "assumed"


# ----------------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------------
app = FastAPI(title="CoMesh Node-Agent", version=AGENT_VERSION)


@app.middleware("http")
async def _enforce_shared_secret(request: Request, call_next):
    """Zugangssperre: jeder Endpunkt verlangt den gemeinsamen Schluessel.

    Ohne gesetztes NODE_SHARED_SECRET bleibt alles offen (Rueckwaerts-
    vertraeglichkeit zu Agenten ohne die Variable) — der Start warnt davor.
    `/health` ist ausgenommen und antwortet ohne Schluessel nur mit einem
    nackten {"ok": …}, damit Monitoring weiter funktioniert, ohne dass
    Node-Id, GPU oder Speicher nach aussen fallen.
    """
    if not NODE_SHARED_SECRET:
        return await call_next(request)
    if request.url.path == "/health":
        return await call_next(request)  # antwortet selbst, ggf. ohne Details
    provided = request.headers.get(SECRET_HEADER, "")
    if provided and hmac.compare_digest(provided, NODE_SHARED_SECRET):
        return await call_next(request)
    return JSONResponse(
        status_code=401,
        content={
            "detail": (
                f"Missing or invalid {SECRET_HEADER} header. This node-agent requires "
                "the shared secret configured for the portal (NODE_SHARED_SECRET)."
            )
        },
    )
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "agent": "gpu-pool-node-agent",
        "node_id": NODE_ID,
        "uptime_sec": int(time.time() - _start_time),
        "ollama_url": OLLAMA_URL,
        "portal_url": PORTAL_URL,
    }


@app.get("/health")
def health(request: Request):
    """Lebenszeichen. Mit gueltigem Secret die vollen Details, sonst nur {"ok": …}."""
    info = get_gpu_info()
    backend_ok = False
    try:
        with httpx.Client(timeout=2.0) as c:
            r = c.get(backend_list_url())
            backend_ok = r.status_code == 200
    except Exception:
        pass
    ok = backend_ok and bool(NODE_ID)
    authorized = True
    if NODE_SHARED_SECRET:
        authorized = hmac.compare_digest(
            request.headers.get(SECRET_HEADER, ""), NODE_SHARED_SECRET
        )
    if not authorized:
        # Kein Secret: nur ein Lebenszeichen, keine Node-Id, keine GPU, kein Speicher.
        return {"ok": ok}
    return {
        "ok": ok,
        "ok": backend_ok and bool(NODE_ID),
        "backend": BACKEND,
        "ollama_reachable": backend_ok,  # legacy key, kept for portal compat
        "backend_reachable": backend_ok,
        "node_id": NODE_ID,
        "gpu": info,
    }


# ----------------------------------------------------------------------------
# OpenAI-compatible endpoint — portal forwards here
# ----------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


# ----------------------------------------------------------------------------
# Server-Sent Events (SSE) — Phase 4
#
# Bis hierher hat der HTTP-Endpunkt `stream: true` stillschweigend ignoriert und
# immer eine komplette Antwort geliefert. Ueber einen Cloudflare-Tunnel ist das
# ein Problem: eine lange Antwort ist ein einziger Request, und Cloudflare kappt
# bei rund 100 s mit 524. Mit SSE fliessen sofort Bytes, die Kappung greift nicht.
#
# BACKEND=openai: der Body wird mit stream=true unveraendert weitergegeben und
#                 die SSE-Zeilen des Backends durchgereicht.
# BACKEND=ollama: Ollamas NDJSON wird in OpenAI-konforme SSE-Rahmen uebersetzt.
# ----------------------------------------------------------------------------
def _sse_frame(model: str, delta: str = "", finish=None, choices=None) -> str:
    """One OpenAI-compatible `chat.completion.chunk` frame."""
    payload = {
        "id": f"chatcmpl-agent-{int(time.time() * 1000)}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": choices if choices is not None else [{
            "index": 0,
            "delta": ({"content": delta} if delta else {}),
            "finish_reason": finish,
        }],
    }
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _sse_error(message: str, kind: str = "backend_error") -> str:
    return "data: " + json.dumps({"error": {"message": message, "type": kind}}) + "\n\n"


async def _stream_sse(payload: dict, model: str):
    """Yield OpenAI-compatible SSE frames from whichever backend is configured."""
    # Erster Rahmen mit der Rolle, wie OpenAI-Clients es erwarten
    yield _sse_frame(model, choices=[{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}])

    if BACKEND == "openai":
        upstream = dict(payload)
        upstream["stream"] = True
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", backend_chat_url(), json=upstream) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        if line.strip() == "data: [DONE]":
                            continue          # wir senden das Ende selbst
                        yield line + "\n\n"
        yield "data: [DONE]\n\n"
        return

    # Ollama: NDJSON -> SSE
    ollama_payload = {
        "model": payload.get("model", ""),
        "messages": payload.get("messages", []),
        "stream": True,
        "options": {},
    }
    if payload.get("temperature") is not None:
        ollama_payload["options"]["temperature"] = payload["temperature"]
    if payload.get("max_tokens") is not None:
        ollama_payload["options"]["num_predict"] = payload["max_tokens"]

    prompt_tokens = 0
    completion_tokens = 0

    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream("POST", backend_chat_url(), json=ollama_payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                delta = (data.get("message") or {}).get("content") or ""
                if delta:
                    yield _sse_frame(model, delta=delta)
                if data.get("done"):
                    prompt_tokens = int(data.get("prompt_eval_count") or prompt_tokens or 0)
                    completion_tokens = int(data.get("eval_count") or completion_tokens or 0)
                    break

    usage_choices = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    frame = _sse_frame(model, choices=usage_choices)
    # Usage anhaengen, ohne den Rahmen zu verbiegen
    obj = json.loads(frame[len("data: "):].strip())
    obj["usage"] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    yield "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    """Chat completion. `stream: true` liefert Server-Sent Events (Phase 4)."""
    global _active_jobs

    payload = {
        "model": req.model,
        "messages": [m.model_dump() for m in req.messages],
        "stream": bool(req.stream),
    }
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    if req.max_tokens is not None:
        payload["max_tokens"] = req.max_tokens

    if req.stream:
        async def _gen():
            global _active_jobs
            _active_jobs += 1
            try:
                async for frame in _stream_sse(payload, req.model):
                    yield frame
            except httpx.HTTPStatusError as e:
                yield _sse_error(f"Backend {e.response.status_code}: {e.response.text[:200]}")
                yield "data: [DONE]\n\n"
            except Exception as e:  # noqa: BLE001 - ein Stream darf nicht hart brechen
                log.exception("agent stream failed")
                yield _sse_error(f"Agent error: {e}", "agent_error")
                yield "data: [DONE]\n\n"
            finally:
                _active_jobs = max(0, _active_jobs - 1)

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    _active_jobs += 1
    try:
        response = await _infer(payload, timeout=180.0)
        # For BACKEND=openai, _infer returns the OpenAI response verbatim (already
        # has choices/usage). For Ollama it returns our translated envelope.
        response.setdefault("_agent", {"node_id": NODE_ID, "gpu": get_gpu_info()})
        return response
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Backend {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        log.exception("agent chat failed")
        raise HTTPException(status_code=502, detail=f"Agent error: {e}")
    finally:
        _active_jobs = max(0, _active_jobs - 1)


# ----------------------------------------------------------------------------
# Self-registration + configuration check (LANA-89)
# ----------------------------------------------------------------------------
def _read_state_file() -> dict:
    try:
        with open(NODE_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_state_file(data: dict) -> None:
    """Persist node credentials next to the portal data (mode 0600)."""
    try:
        directory = os.path.dirname(NODE_STATE_FILE)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{NODE_STATE_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, NODE_STATE_FILE)
    except Exception as e:
        log.warning(f"Could not persist node state to {NODE_STATE_FILE}: {e}")


def _load_node_identity() -> None:
    """Fill NODE_ID/NODE_API_KEY from the state file or register fresh.

    Two supported setups:

      * operator copies NODE_ID + NODE_API_KEY into .env (classic), or
      * operator sets PORTAL_URL + PORTAL_USER_KEY only; the agent registers
        itself, writes /data/node-state.json, and is done. The address is derived
        from ADVERTISE_HOST / the detected outbound IP on the portal side, so
        neither side needs to know an IP up front.
    """
    global NODE_ID, NODE_API_KEY
    state = _read_state_file()
    if not NODE_ID and state.get("node_id"):
        NODE_ID = str(state["node_id"])
        NODE_API_KEY = NODE_API_KEY or state.get("node_api_key", "")
        log.info(f"Loaded node credentials from {NODE_STATE_FILE}: node_id={NODE_ID}")
    if NODE_ID and NODE_API_KEY:
        return
    if not (PORTAL_URL and PORTAL_USER_KEY):
        return

    summary = gpu_summary()
    name = NODE_NAME or local_hostname() or "node"
    vram_gb, vram_source = vram_report()
    body = {
        "name": name[:80],
        "gpu_type": (NODE_GPU_TYPE or summary["name"] or "unknown")[:80],
        "vram_gb": vram_gb,
        "vram_source": vram_source,
        "port": AGENT_PORT,
        # The address may well be empty here: the portal fills it in from the
        # first heartbeat, so a node on DHCP does not need to know it at all.
        "node_url": ADVERTISE_HOST or None,
    }
    if NODE_HOURLY_RATE:
        try:
            body["hourly_rate"] = float(NODE_HOURLY_RATE)
        except ValueError:
            pass
    try:
        r = httpx.post(
            f"{PORTAL_URL}/nodes/register",
            headers={"Authorization": f"Bearer {PORTAL_USER_KEY}", "Content-Type": "application/json"},
            json=body,
            timeout=20.0,
        )
        if r.status_code >= 300:
            log.error(f"Self-registration failed ({r.status_code}): {r.text[:300]}")
            log.error("Check PORTAL_USER_KEY (account API key) and that the account has role provider/both.")
            return
        data = r.json()
        NODE_ID = str(data.get("id") or "")
        NODE_API_KEY = data.get("agent_api_key") or ""
        log.info(f"Self-registered as node_id={NODE_ID} name={body['name']} ({body['gpu_type']})")
        _write_state_file({
            "node_id": NODE_ID,
            "node_api_key": NODE_API_KEY,
            "portal_url": PORTAL_URL,
            "name": body["name"],
        })
    except Exception as e:
        log.error(f"Self-registration error: {e!r}")


def _portal_probe() -> tuple:
    """(ok, Zeile) — erreicht dieser Agent die Portal-API?

    Erst ``/net/echo`` (es nennt die Adresse, unter der das Portal den Aufrufer
    sieht — die eigentliche Frage bei DHCP), dann ``/health``. Der Rueckfall ist
    noetig, weil der oeffentliche Portalname nur ``/api/...`` an die API
    durchreicht: ``/api/net/echo`` landet auf der HTML-Ersatzseite. Eine
    erreichbare Installation darf daran nicht scheitern — und eine HTML-Antwort
    darf nie als Erfolg gelten, nur weil der Status 200 ist.
    """
    with httpx.Client(timeout=10.0) as c:
        try:
            r = c.get(f"{PORTAL_URL}/net/echo")
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                portal = (r.json() or {}).get("portal") or {}
                return True, f"ja (public_url={portal.get('public_url')})"
        except Exception:
            pass
        try:
            r = c.get(f"{PORTAL_URL}/health")
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                return True, f"ja ({PORTAL_URL}/health)"
            return False, f"nein (HTTP {r.status_code} von {PORTAL_URL}/health)"
        except Exception as e:
            return False, f"nein ({e})"


def config_check() -> int:
    """Print what the portal would be told. Exit code 0 = a node can start."""
    ok = True
    advertise = resolve_advertise_host(env_var="ADVERTISE_HOST")
    print("CoMesh node-agent — configuration check")
    print(f"  version         : {AGENT_VERSION}")
    print(f"  portal URL      : {PORTAL_URL or '(unset — set PORTAL_URL)'}")
    print(f"  advertise host  : {advertise}  (= how the portal will dial this node)")
    print(f"  detected IP     : {detect_outbound_ip()}")
    print(f"  hostname        : {local_hostname()}")
    print(f"  agent port      : {AGENT_PORT}")
    print(f"  transport       : {AGENT_TRANSPORT}")
    print(f"  backend         : {BACKEND} @ {INFERENCE_URL}")
    print(f"  node id         : {NODE_ID or '(auto-register on start)'}")
    print(f"  node state file : {NODE_STATE_FILE}")
    print(f"  config file     : {os.environ.get('COMESH_AGENT_ENV_USED') or '(none found, environment only)'}")
    gpu = gpu_summary()
    print(f"  gpu             : {gpu['name']} ({gpu['vram_gb']} GB)")
    vram_gb, vram_source = vram_report()
    print(f"  vram advertised : {vram_gb} GB ({vram_source})")

    if not PORTAL_URL:
        print("  !! PORTAL_URL is unset — a node on a fresh network needs at least this one variable.")
        ok = False
    else:
        reachable, line = _portal_probe()
        print(f"  portal reachable: {line}")
        if not reachable:
            ok = False
    if not (NODE_ID and NODE_API_KEY) and not PORTAL_USER_KEY:
        print("  !! neither NODE_ID/NODE_API_KEY nor PORTAL_USER_KEY set — the node cannot join the pool.")
        ok = False
    print("=> OK" if ok else "=> incomplete configuration")
    return 0 if ok else 1


# ----------------------------------------------------------------------------
# Heartbeat loop
# ----------------------------------------------------------------------------
async def send_heartbeat(client: httpx.AsyncClient):
    if not NODE_ID or not NODE_API_KEY:
        return
    info = get_gpu_info()
    # status: busy if there are active jobs OR VRAM > 70% used; else online
    busy = info["active_jobs"] > 0 or (info["utilization"] or 0) > 0.7
    vram_gb, vram_source = vram_report()
    payload = {
        "status": "busy" if busy else "online",
        "gpu_util": info["utilization"],
        "vram_used_gb": info["vram_used_gb"],
        "vram_total_gb": info["vram_total_gb"],
        # Woher die gemeldete VRAM-Zahl stammt ("override"/"detected"/"assumed");
        # "assumed" heisst: keine GPU erkannt und nichts gesetzt -> 1 GB.
        "vram_gb": vram_gb,
        "vram_source": vram_source,
        "active_jobs": info["active_jobs"],
        # The portal adopts this only while the node has no explicitly configured
        # address. That is how a DHCP node stays dialable without any config.
        "advertise_host": advertised_host(),
        "agent_port": AGENT_PORT,
        "raw": info,
    }
    try:
        r = await client.post(
            f"{PORTAL_URL}/nodes/{NODE_ID}/heartbeat",
            headers={"X-Node-Key": NODE_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=10.0,
        )
        if r.status_code >= 300:
            log.warning(f"heartbeat {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.warning(f"heartbeat failed: {e}")


# ----------------------------------------------------------------------------
# Phase 2: Ollama proxy used by the WS job handler.
# This is the same OpenAI->Ollama translation that the HTTP /v1/chat/completions
# endpoint does, extracted so the WS loop can reuse it.
# ----------------------------------------------------------------------------
async def _ollama_chat_non_streaming(payload: dict, timeout: float = 180.0) -> dict:
    """Forward an OpenAI-shaped /v1/chat/completions body to the configured backend.

    Legacy helper used by the WS job handler. For BACKEND=ollama it translates to
    Ollama's /api/chat; for BACKEND=openai it forwards to /v1/chat/completions.
    Returns the OpenAI-shaped `choices` + `usage` envelope.
    """
    return await _infer(payload, timeout=timeout)


async def heartbeat_loop():
    async with httpx.AsyncClient() as client:
        # immediate first beat so the node flips to "online" quickly
        await send_heartbeat(client)
        while True:
            await asyncio.sleep(HEARTBEAT_SEC)
            await send_heartbeat(client)


# ----------------------------------------------------------------------------
# Phase 1: Outbound WebSocket client loop
# ----------------------------------------------------------------------------
def _portal_ws_url() -> str:
    """Convert http(s)://portal/... to ws(s)://portal/agent/connect with auth in query string.

    ``PORTAL_URL`` endet beim oeffentlichen Portalnamen auf ``/api`` (dort reicht
    nginx nur ``/api/...`` an die API durch), der WebSocket haengt aber an
    ``/agent/connect`` **ohne** dieses Praefix. Ohne das Abschneiden zeigt der
    Handshake auf ``/api/agent/connect`` und bekommt die HTML-Ersatzseite —
    die Node bleibt dann still offline, waehrend alles andere zu funktionieren
    scheint. Eine zweite Variable nur fuer den WS-Weg waere die Alternative;
    eine URL, die ueberall stimmt, ist die bessere.
    """
    base = PORTAL_URL.rstrip("/")
    if base.endswith("/api"):
        base = base[: -len("/api")]
    if base.startswith("https://"):
        ws_base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        ws_base = "ws://" + base[len("http://"):]
    else:
        ws_base = "ws://" + base
    return f"{ws_base}/agent/connect?node_id={NODE_ID}&node_key={NODE_API_KEY}"


async def ws_loop():
    """Connect, ping, handle jobs, reconnect forever.

    Backoff: 1s, 2s, 4s, 8s, 16s, capped at WS_RECONNECT_MAX_SEC.
    Reset to 1s on a successful welcome.

    Phase 2: also handles `{"type": "job", "job_id", "payload"}` messages
    from the pool. The payload is an OpenAI /v1/chat/completions body.
    The agent forwards it to its local Ollama (NON-STREAMING) and replies
    with `{"type": "job_result", "job_id", "ok", "response" | "error"}`.
    """
    import websockets  # local import so the import only fails in WS mode
    url = _portal_ws_url()
    backoff = 1.0
    log.info(f"WS transport: connecting to {url.split('?')[0]} (node_id={NODE_ID})")
    while True:
        try:
            async with websockets.connect(url, open_timeout=10, ping_interval=None) as ws:
                # Receive the welcome to confirm auth
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                try:
                    welcome = json.loads(raw)
                except Exception:
                    welcome = {"raw": raw[:200]}
                log.info(f"WS welcome received: {welcome.get('type', '?')}")
                backoff = 1.0  # success — reset
                # Ping loop
                while True:
                    info = get_gpu_info()
                    ping_msg = {
                        "type": "ping",
                        "vram_used_gb": info.get("vram_used_gb", 0.0),
                        "vram_total_gb": info.get("vram_total_gb", 0.0),
                        "active_jobs": info.get("active_jobs", 0),
                        "uptime": int(time.time() - _start_time),
                    }
                    try:
                        await ws.send(json.dumps(ping_msg))
                    except Exception as e:
                        log.warning(f"WS send failed: {e}")
                        break  # bubble up to reconnect
                    # Drain any incoming messages (welcome, pong, job frames)
                    try:
                        while True:
                            incoming = await asyncio.wait_for(ws.recv(), timeout=0.0)
                            try:
                                m = json.loads(incoming)
                                mtype = (m.get("type") or "").lower()
                                if mtype == "pong":
                                    pass  # RTT measurement hook (not used in Phase 1+2)
                                elif mtype == "job":
                                    # Phase 2: dispatch to Ollama in the background
                                    # so the ping loop keeps ticking.
                                    asyncio.create_task(_handle_job_frame(ws, m))
                                else:
                                    log.debug(f"WS ignored: {mtype}")
                            except Exception:
                                log.debug(f"WS non-JSON frame: {incoming[:80]}")
                    except asyncio.TimeoutError:
                        pass  # nothing buffered — expected
                    await asyncio.sleep(WS_HEARTBEAT_SEC)
        except asyncio.TimeoutError:
            log.warning(f"WS connect/welcome timed out, retrying in {backoff}s")
        except Exception as e:
            log.warning(f"WS disconnected: {e!r}, retrying in {backoff}s")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, float(WS_RECONNECT_MAX_SEC))


async def _handle_job_frame(ws, frame: dict) -> None:
    """Handle one `{"type":"job", job_id, payload}` message from the pool.

    Phase 3 (LANA-114): the handler supports chunked delivery. When the
    pool requests `stream: true` AND the backend is Ollama, the agent
    streams ND-JSON deltas as `job_result_chunk` frames and then sends the
    binding full `job_result` (content aggregated from the deltas). Both
    BACKEND=openai and any stream failure fall back to the Phase-2
    non-streaming path — chunk frames are advisory; errors after deltas
    must make clients discard partial content (final/error is binding).
    Timeouts: 180s for the Ollama call. The pool typically uses 120s for
    send_job_via_ws; we leave some headroom on the agent side.
    """
    global _active_jobs
    job_id = frame.get("job_id")
    payload = frame.get("payload") or {}
    if not job_id:
        log.warning(f"WS job frame without job_id: {frame}")
        return
    payload = dict(payload)
    want_stream = bool(payload.get("stream")) and BACKEND == "ollama"

    async def _send_chunk(delta: str) -> None:
        # Fire-and-forget: a failed chunk send means the socket is dying;
        # the stream will break on the next send and `_handle_job_frame`
        # reports ok:false in the final job_result.
        try:
            await ws.send(json.dumps({"type": "job_result_chunk",
                                      "job_id": job_id, "delta": delta}))
        except Exception as e:
            raise RuntimeError(f"chunk send failed: {e!r}") from e

    _active_jobs += 1
    try:
        ollama_timeout = float(os.environ.get("AGENT_OLLAMA_TIMEOUT", "180"))
        if want_stream:
            response = await _infer_streaming(payload, timeout=ollama_timeout,
                                              send_delta=_send_chunk)
            # Binding full result: content is the exact aggregation of the
            # chunk deltas we already sent (filled by _infer_streaming).
        else:
            response = await _infer(payload, timeout=ollama_timeout)
        reply = {"type": "job_result", "job_id": job_id, "ok": True, "response": response}
    except httpx.HTTPStatusError as e:
        err = f"Ollama HTTP {e.response.status_code}: {e.response.text[:200]}"
        log.warning(f"WS job {job_id} failed: {err}")
        reply = {"type": "job_result", "job_id": job_id, "ok": False, "error": err}
    except Exception as e:
        log.exception(f"WS job {job_id} error")
        reply = {"type": "job_result", "job_id": job_id, "ok": False, "error": f"agent error: {e!r}"}
    finally:
        _active_jobs = max(0, _active_jobs - 1)
    try:
        await ws.send(json.dumps(reply))
    except Exception as e:
        log.warning(f"WS job_result send failed: {e!r}")


def _startup_warnings() -> None:
    """Was beim Start sichtbar sein muss — für beide Transporte.

    Der VRAM-Hinweis gehört ausdrücklich auch in den WS-Betrieb: dort gibt es
    keinen HTTP-Server, aber dieselbe stille Falle (1 GB angenommen, nie ein
    Auftrag). Die Sperr-Warnung dagegen nur im HTTP-Betrieb — im WS-Betrieb
    öffnet der Agent gar keinen Port, die Meldung wäre falsch.
    """
    _warn_if_unconfigured()
    if AGENT_TRANSPORT != "ws":
        if not NODE_SHARED_SECRET:
            log.warning(
                "NODE_SHARED_SECRET is NOT set: every port of this agent is open to anyone "
                "who can reach %s — an LLM proxy without a lock. Set the same value on the "
                "portal and the agent to require the %s header.",
                AGENT_PORT, SECRET_HEADER,
            )
        else:
            log.info(
                f"Zugangssperre aktiv: alle Endpunkte ausser /health verlangen {SECRET_HEADER}"
            )
    vram_gb, vram_source = vram_report()
    if vram_source == "assumed":
        log.warning(
            "No GPU detected via NVML and NODE_VRAM_GB is unset — advertising %s GB. "
            "The pool will refuse every job that needs more, so this node looks online "
            "but never gets work. On Apple Silicon set NODE_VRAM_GB to the unified "
            "memory size (e.g. NODE_VRAM_GB=16).",
            vram_gb,
        )
    if not NODE_ID or not NODE_API_KEY:
        log.warning(
            "Agent is running without node credentials: no heartbeats, no jobs. "
            "Set NODE_ID + NODE_API_KEY, or PORTAL_URL + PORTAL_USER_KEY for self-registration."
        )
    log.info(f"Advertised as {advertised_host()}:{AGENT_PORT} (portal dials this)")


@app.on_event("startup")
async def _on_start():
    _load_node_identity()
    _startup_warnings()
    if AGENT_TRANSPORT == "ws":
        asyncio.create_task(ws_loop())
        # Guertel und Hosentraeger: auch im WS-Betrieb HTTP-Heartbeats senden,
        # solange die API erreichbar ist. Der Ping allein macht die Node nur
        # ueber last_ws_seen lebendig; status und VRAM kommen ueber diesen Weg.
        asyncio.create_task(heartbeat_loop())
        log.info(
            f"Node-agent WS transport started. node_id={NODE_ID} portal={PORTAL_URL} "
            f"ollama={OLLAMA_URL} ping={WS_HEARTBEAT_SEC}s"
        )
        return
    # HTTP transport (default, unchanged from v1)
    asyncio.create_task(heartbeat_loop())
    log.info(f"Node-agent started. node_id={NODE_ID} portal={PORTAL_URL} ollama={OLLAMA_URL}")


if __name__ == "__main__":
    # A direct run (`python agent.py` or the frozen binary) gets its settings from
    # the config file the installer wrote (`~/.config/comesh/agent.env`), falling
    # back to `.env` in the working directory — that is the file the interactive
    # installer writes.
    _load_agent_env()
    _refresh_config_from_environ()
    # Erneut, weil AGENT_LOG_FILE meist erst aus der Konfigurationsdatei kommt.
    _setup_logging()
    import argparse
    parser = argparse.ArgumentParser(description="CoMesh Node-Agent")
    parser.add_argument(
        "--transport", choices=["http", "ws"], default=None,
        help="Override AGENT_TRANSPORT env var (default: read from env, fallback 'http')",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Print the network configuration (portal reachability, detected address) and exit",
    )
    parser.add_argument("--version", action="store_true", help="Print the agent version and exit")
    args = parser.parse_args()
    if args.version:
        print(f"comesh-agent {AGENT_VERSION}")
        raise SystemExit(0)
    if args.transport:
        AGENT_TRANSPORT = args.transport  # local override for this run
        log.info(f"--transport={args.transport} override applied")
    if args.check:
        raise SystemExit(config_check())
    if AGENT_TRANSPORT == "ws":
        # WS mode: don't bind a port, just run the async loop.
        #
        # Beide Schleifen, wie im FastAPI-Startup: der WS-Ping allein macht die
        # Node nur ueber `last_ws_seen` lebendig, waehrend `status` und `vram_gb`
        # aus dem HTTP-Heartbeat kommen. Wer nur `ws_loop()` startet, laesst eine
        # verbundene Node im Portal ohne Messwerte stehen — der Fehler, der den
        # WS-Betrieb schon einmal unbrauchbar gemacht hat.
        _load_node_identity()
        _startup_warnings()

        async def _run_ws() -> None:
            await asyncio.gather(ws_loop(), heartbeat_loop())

        try:
            asyncio.run(_run_ws())
        except KeyboardInterrupt:
            log.info("WS transport interrupted, exiting.")
    else:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
