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

  PORTAL_URL       Base URL of the portal, e.g. http://100.126.79.111:8765
  NODE_ID          Numeric id of the registered GpuNode
  NODE_API_KEY     The agent_api_key issued by POST /nodes/register
  OLLAMA_URL       Local Ollama URL (default: http://localhost:11434)
  AGENT_PORT       Port to listen on (HTTP transport only; default: 11435)
  HEARTBEAT_SEC    Heartbeat interval in HTTP mode (default: 30)
  AGENT_TRANSPORT  "http" (default) or "ws"
  WS_HEARTBEAT_SEC Ping interval in WS mode (default: 15)
  WS_RECONNECT_MAX_SEC  Cap for reconnect backoff (default: 30)

Run:
  # HTTP mode (unchanged)
  docker run -d --name gpu-pool-agent \
    --gpus all \
    -e PORTAL_URL=http://100.126.79.111:8765 \
    -e NODE_ID=1 \
    -e NODE_API_KEY=node_xxx... \
    -p 11435:11435 \
    gpu-pool-node-agent

  # WS mode (Phase 1; no inbound port published)
  docker run -d --name gpu-pool-agent-ws \
    --gpus all \
    -e AGENT_TRANSPORT=ws \
    -e PORTAL_URL=http://100.126.79.111:8765 \
    -e NODE_ID=1 \
    -e NODE_API_KEY=node_xxx... \
    gpu-pool-node-agent
"""
import asyncio
import json
import logging
import os
import time
from typing import List, Optional

import httpx
import psutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# pynvml is optional in non-GPU dev environments
try:
    import pynvml
    pynvml.nvmlInit()
    _HAVE_NVML = True
except Exception:
    _HAVE_NVML = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [agent] %(levelname)s %(message)s")
log = logging.getLogger("node-agent")

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
PORTAL_URL = os.environ.get("PORTAL_URL", "http://100.126.79.111:8765").rstrip("/")
NODE_ID = os.environ.get("NODE_ID", "")
NODE_API_KEY = os.environ.get("NODE_API_KEY", "")
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


async def _infer(payload: dict, timeout: float = 180.0) -> dict:
    """Run one inference against the configured backend and return an OpenAI-shaped response.

    Accepts an OpenAI-shaped /v1/chat/completions body (``model``, ``messages``,
    ``temperature``, ``max_tokens``, ``stream``). Non-streaming only.

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
            "message": {"role": msg.get("role", "assistant"), "content": msg.get("content", "")},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens") or data.get("prompt_eval_count") or 0,
            "completion_tokens": usage.get("completion_tokens") or data.get("eval_count") or 0,
            "total_tokens": (usage.get("total_tokens") or 0)
                or ((data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0)),
        },
        "_agent": {"node_id": NODE_ID, "gpu": get_gpu_info()},
    }


# Phase 1: outbound transport. Default = "http" (legacy FastAPI server + HTTP heartbeats).
# Set AGENT_TRANSPORT=ws to use the outbound WebSocket client (no inbound port needed).
AGENT_TRANSPORT = os.environ.get("AGENT_TRANSPORT", "http").lower().strip()
# WS-specific tunables
WS_HEARTBEAT_SEC = int(os.environ.get("WS_HEARTBEAT_SEC", "15"))
WS_RECONNECT_MAX_SEC = int(os.environ.get("WS_RECONNECT_MAX_SEC", "30"))

if not NODE_ID or not NODE_API_KEY:
    log.warning("NODE_ID / NODE_API_KEY not set — heartbeats and auth will not work.")

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


# ----------------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------------
app = FastAPI(title="GPU-Pool Node-Agent", version="0.1.0")
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
def health():
    info = get_gpu_info()
    backend_ok = False
    try:
        with httpx.Client(timeout=2.0) as c:
            r = c.get(backend_list_url())
            backend_ok = r.status_code == 200
    except Exception:
        pass
    return {
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


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    global _active_jobs
    _active_jobs += 1
    try:
        payload = {
            "model": req.model,
            "messages": [m.model_dump() for m in req.messages],
            "stream": req.stream,
        }
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens
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
# Heartbeat loop
# ----------------------------------------------------------------------------
async def send_heartbeat(client: httpx.AsyncClient):
    if not NODE_ID or not NODE_API_KEY:
        return
    info = get_gpu_info()
    # status: busy if there are active jobs OR VRAM > 80% used; else online
    busy = info["active_jobs"] > 0 or (info["utilization"] or 0) > 0.8
    payload = {
        "status": "busy" if busy else "online",
        "gpu_util": info["utilization"],
        "vram_used_gb": info["vram_used_gb"],
        "vram_total_gb": info["vram_total_gb"],
        "active_jobs": info["active_jobs"],
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
    """Convert http(s)://portal/... to ws(s)://portal/agent/connect with auth in query string."""
    base = PORTAL_URL.rstrip("/")
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

    Phase 2: NON-STREAMING ONLY.
      - We force `stream=False` in the payload before forwarding to Ollama
        (the agent never returns `job_result_chunk` frames in Phase 2).
      - On success, reply with the full OpenAI-shaped response.
      - On any failure, reply with `ok: false` and the error string.
    Timeouts: 180s for the Ollama call. The pool typically uses 120s for
    send_job_via_ws; we leave some headroom on the agent side.
    """
    global _active_jobs
    job_id = frame.get("job_id")
    payload = frame.get("payload") or {}
    if not job_id:
        log.warning(f"WS job frame without job_id: {frame}")
        return
    # Phase 2: non-streaming only — force stream=False so we never try to
    # stream back over WS (Phase 3 will add `job_result_chunk` ND-JSON).
    if payload.get("stream"):
        log.info(f"WS job {job_id}: stream=true requested, forcing non-streaming (Phase 2 limit)")
    payload = dict(payload)
    payload["stream"] = False

    _active_jobs += 1
    try:
        ollama_timeout = float(os.environ.get("AGENT_OLLAMA_TIMEOUT", "180"))
        response = await _ollama_chat_non_streaming(payload, timeout=ollama_timeout)
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


@app.on_event("startup")
async def _on_start():
    if AGENT_TRANSPORT == "ws":
        asyncio.create_task(ws_loop())
        log.info(
            f"Node-agent WS transport started. node_id={NODE_ID} portal={PORTAL_URL} "
            f"ollama={OLLAMA_URL} ping={WS_HEARTBEAT_SEC}s"
        )
        return
    # HTTP transport (default, unchanged from v1)
    asyncio.create_task(heartbeat_loop())
    log.info(f"Node-agent started. node_id={NODE_ID} portal={PORTAL_URL} ollama={OLLAMA_URL}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GPU-Pool Node-Agent")
    parser.add_argument(
        "--transport", choices=["http", "ws"], default=None,
        help="Override AGENT_TRANSPORT env var (default: read from env, fallback 'http')",
    )
    args = parser.parse_args()
    if args.transport:
        AGENT_TRANSPORT = args.transport  # local override for this run
        log.info(f"--transport={args.transport} override applied")
    if AGENT_TRANSPORT == "ws":
        # WS mode: don't bind a port, just run the async loop.
        try:
            asyncio.run(ws_loop())
        except KeyboardInterrupt:
            log.info("WS transport interrupted, exiting.")
    else:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
