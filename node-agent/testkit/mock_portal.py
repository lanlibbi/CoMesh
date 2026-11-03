"""Testportal für den Installer — bildet die Wege des echten Portals nach.

Zweck: `install.sh`/`install.ps1` und das Einzelbinary **ohne** das laufende
Portal prüfen zu können. Das ist kein Ersatz für einen Test gegen das echte
Portal, deckt aber genau die Kette ab, an der es sonst still scheitert:
Selbstregistrierung, WebSocket-Handshake, Heartbeat, „erscheint die Node in
/nodes/my", und die Adresslage des öffentlichen Namens (API unter `/api`,
`/agent/connect` **ohne** Präfix — so wie nginx es ausliefert).

    python -m uvicorn mock_portal:app --host 127.0.0.1 --port 8799

Dann:

    COMESH_BASE_URL=http://127.0.0.1:8799/downloads \
    COMESH_PORTAL_URL=http://127.0.0.1:8799/api \
    COMESH_USER_KEY=gpu_test_… sh install.sh

Der Zustand liegt nur im Speicher (Neustart = leer). Nichts hier ist für den
Produktivbetrieb gedacht: keine Authentifizierung, keine Datenbank, keine
Prüfsummen.
"""
from __future__ import annotations

import json
import time
from typing import Dict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

STATE: Dict[str, object] = {"next_id": 100, "nodes": {}, "heartbeats": [], "pings": 0, "ws": 0}


class RegisterBody(BaseModel):
    name: str = ""
    gpu_type: str = "unknown"
    vram_gb: int = 1
    vram_source: str = "assumed"
    port: int = 11435
    node_url: str | None = None
    hourly_rate: float | None = None


api = FastAPI(title="CoMesh mock portal — API")


@api.get("/health")
def health():
    return {"status": "ok", "mock": True, "community": {"nodes_total": len(STATE["nodes"])}}


@api.get("/v1/me")
def me(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return JSONResponse({"detail": "Missing Authorization header."}, status_code=401)
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return JSONResponse({"detail": "API key is revoked or inactive."}, status_code=401)
    return {"id": 7, "email": "provider@example.invalid", "role": "provider", "allowed_models": None}


@api.post("/nodes/register")
def register(body: RegisterBody, request: Request):
    if not request.headers.get("authorization", "").lower().startswith("bearer "):
        return JSONResponse({"detail": "Missing Authorization header."}, status_code=401)
    node_id = STATE["next_id"]  # type: ignore[operator]
    STATE["next_id"] = node_id + 1  # type: ignore[operator]
    STATE["nodes"][node_id] = {  # type: ignore[index]
        "id": node_id,
        "name": body.name,
        "gpu_type": body.gpu_type,
        "vram_gb": body.vram_gb,
        "vram_source": body.vram_source,
        "port": body.port,
        "node_url": body.node_url,
        "registered_at": time.time(),
    }
    return {
        "id": node_id,
        "agent_api_key": f"node_mock_{node_id}",
        "name": body.name,
        "vram_gb": body.vram_gb,
    }


@api.get("/nodes/my")
def nodes_my(request: Request):
    if not request.headers.get("authorization", "").lower().startswith("bearer "):
        return JSONResponse({"detail": "Missing Authorization header."}, status_code=401)
    return list(STATE["nodes"].values())  # type: ignore[union-attr]


@api.post("/nodes/{node_id}/heartbeat")
def heartbeat(node_id: int, payload: dict, request: Request):
    if not request.headers.get("x-node-key"):
        return JSONResponse({"detail": "node key missing"}, status_code=401)
    node = STATE["nodes"].get(node_id)  # type: ignore[union-attr]
    if node is None:
        return JSONResponse({"detail": "unknown node"}, status_code=404)
    node["last_heartbeat"] = time.time()
    node["vram_gb"] = payload.get("vram_gb", node.get("vram_gb"))
    node["vram_source"] = payload.get("vram_source", node.get("vram_source"))
    node["status"] = payload.get("status")
    STATE["heartbeats"].append({"node_id": node_id, "at": time.time(), "payload": payload})
    return JSONResponse({}, status_code=204)


@api.get("/__state")
def dump_state():
    """Nur für Tests: was das Portal gesehen hat (ohne Zugangsdaten)."""
    return {
        "nodes": list(STATE["nodes"].values()),  # type: ignore[union-attr]
        "heartbeats": len(STATE["heartbeats"]),  # type: ignore[arg-type]
        "pings": STATE["pings"],
        "ws_sessions": STATE["ws"],
    }


# Auffangroute wie im echten nginx: unbekannte Pfade unter /api liefern die
# HTML-Ersatzseite mit Status 200 — genau die Falle, die einen Client täuscht,
# der nur den Statuscode prüft. Sie MUSS nach allen echten Routen stehen.
@api.get("/{unknown:path}")
def spa_fallback(unknown: str):
    from fastapi.responses import HTMLResponse

    return HTMLResponse("<!doctype html><html><body>CoMesh</body></html>", status_code=200)


app = FastAPI(title="CoMesh mock portal")
app.mount("/api", api)


@app.get("/net/echo")
def net_echo(request: Request):
    """Nur im LAN erreichbar (nginx proxied es nicht durch) — wie im echten Portal."""
    return {
        "portal": {"public_url": "http://127.0.0.1:8799"},
        "peer": request.client.host if request.client else None,
    }


# --- Auslieferung der Binaries (wie frontend-alpine/downloads/ im Portal) ----
# Über HTTP, nicht über file:// — genau der Weg, den install.sh geht.
import os  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402

DOWNLOADS = os.environ.get("MOCK_DOWNLOADS", "/tmp/comesh-downloads")


@app.get("/downloads/{name}")
def download(name: str):
    if "/" in name or name.startswith("."):
        return JSONResponse({"detail": "bad name"}, status_code=400)
    path = os.path.join(DOWNLOADS, name)
    if not os.path.isfile(path):
        return JSONResponse({"detail": "not found"}, status_code=404)
    return FileResponse(path)


@app.websocket("/agent/connect")
async def agent_connect(ws: WebSocket, node_id: str = "", node_key: str = ""):
    """Wie das echte Portal: Auth über die Query, dann Willkommen + Pings zählen."""
    await ws.accept()
    if node_id not in {str(k) for k in STATE["nodes"]}:  # type: ignore[union-attr]
        await ws.close(code=4401)
        return
    STATE["ws"] = int(STATE["ws"]) + 1  # type: ignore[arg-type]
    await ws.send_text(json.dumps({"type": "welcome", "node_id": node_id}))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                frame = json.loads(raw)
            except ValueError:
                continue
            if frame.get("type") == "ping":
                STATE["pings"] = int(STATE["pings"]) + 1  # type: ignore[arg-type]
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
