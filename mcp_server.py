"""MCP-Endpunkt am Portal: Claude verbindet sich per URL, ohne lokale Installation.

Claude Desktop und Claude Code koennen MCP-Server als **remote** einbinden (Streamable HTTP).
Deshalb braucht es keinen Download und keine Dateien: das Portal selbst spricht MCP unter `/mcp`,
die Anmeldung laeuft ueber denselben Account-Schluessel wie die API.

Umgesetzt ist der JSON-RPC-Teil von MCP (2025-06-18), den Claude fuer den Verbindungsaufbau und
fuer Werkzeugaufrufe braucht:

  initialize            -> Serverfaehigkeiten
  notifications/...     -> 202 ohne Inhalt
  tools/list            -> Werkzeuge (Modelle auflisten, fragen, Portal beschreiben)
  tools/call            -> Werkzeug ausfuehren

Die Werkzeuge benutzen **denselben** Weg wie die API (`chat_completions`): Whitelist, Guthaben,
Rate-Limit und Abrechnung gelten damit unveraendert. Kein zweiter Pfad, keine Umgehung.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

log = logging.getLogger("gpu-pool.mcp")

PROTOKOLL_VERSION = "2025-06-18"
SERVER_NAME = "comesh"


def _werkzeuge() -> List[Dict[str, Any]]:
    """Was Claude anbieten darf. Bewusst klein: Modelle ansehen und fragen."""
    return [
        {
            "name": "list_models",
            "description": (
                "Listet die Modelle, die dieses Konto in CoMesh nutzen darf - mit Kennung und "
                "Herkunft. Der erste Eintrag ist der Standard, wenn kein Modell genannt wird."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "ask",
            "description": (
                "Schickt eine Frage an ein Modell im CoMesh-Pool und gibt die Antwort zurueck. "
                "Ohne 'model' wird das Standardmodell des Kontos genutzt."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Die Frage oder Aufgabe."},
                    "model": {
                        "type": "string",
                        "description": "Modellkennung aus list_models (optional).",
                    },
                    "system": {"type": "string", "description": "Systemanweisung (optional)."},
                    "max_tokens": {
                        "type": "integer",
                        "description": "Obergrenze fuer die Antwort (optional).",
                    },
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
        {
            "name": "whoami",
            "description": "Zeigt Konto, Rolle und welche Modelle freigegeben sind.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]


def _text(inhalt: str) -> Dict[str, Any]:
    """MCP-Ergebnis mit einem Textblock."""
    return {"content": [{"type": "text", "text": inhalt}], "isError": False}


def _fehler(inhalt: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": inhalt}], "isError": True}


async def _modelle_fuer(user, db) -> List[str]:
    from main import _modell_katalog

    katalog = await _modell_katalog(user, db)
    return [m.get("name") or m.get("model") for m in katalog if (m.get("name") or m.get("model"))]


async def _werkzeug_ausfuehren(name: str, argumente: Dict[str, Any], user, db, request: Request):
    """Ein Werkzeug ausfuehren. Fehler werden als MCP-Ergebnis zurueckgegeben, nicht als HTTP."""
    if name == "list_models":
        modelle = await _modelle_fuer(user, db)
        if not modelle:
            return _fehler("Dieses Konto darf derzeit kein Modell nutzen. Im Profil freigeben lassen.")
        zeilen = [f"- {m}" for m in modelle]
        return _text("Verfuegbare Modelle fuer " + str(getattr(user, "email", "")) + ":\n" + "\n".join(zeilen))

    if name == "whoami":
        freigaben = None
        try:
            freigaben = user.get_allowed_models()
        except Exception:
            freigaben = None
        text = (
            f"Konto: {getattr(user, 'email', '?')}\n"
            f"Rolle: {getattr(user, 'role', '?')}\n"
            f"Cloud-Modelle erlaubt: {'ja' if getattr(user, 'allow_cloud', False) else 'nein'}\n"
            f"Freigaben: {('alle lokalen' if freigaben is None else (', '.join(freigaben) or 'keine'))}"
        )
        return _text(text)

    if name == "ask":
        prompt = str(argumente.get("prompt") or "").strip()
        if not prompt:
            return _fehler("'prompt' fehlt.")
        modelle = await _modelle_fuer(user, db)
        modell = str(argumente.get("model") or "").strip()
        if not modell:
            if not modelle:
                return _fehler("Kein Modell verfuegbar.")
            modell = modelle[0]
        nachrichten = []
        system = str(argumente.get("system") or "").strip()
        if system:
            nachrichten.append({"role": "system", "content": system})
        nachrichten.append({"role": "user", "content": prompt})

        from main import ChatCompletionRequest, chat_completions

        rumpf: Dict[str, Any] = {"model": modell, "messages": nachrichten, "stream": False}
        grenze = argumente.get("max_tokens")
        if isinstance(grenze, int) and 0 < grenze <= 32000:
            rumpf["max_tokens"] = grenze
        try:
            anfrage = ChatCompletionRequest(**rumpf)
            ergebnis = await chat_completions(request=request, body=anfrage, user=user, db=db)
        except HTTPException as e:
            return _fehler(f"Abgelehnt: {e.detail}")
        except Exception as e:  # noqa: BLE001
            return _fehler(f"Fehler beim Aufruf: {e}")

        # chat_completions liefert je nach Weg ein pydantic-Modell oder ein Response-Objekt.
        if hasattr(ergebnis, "model_dump"):
            roh = ergebnis.model_dump()
        else:
            roh = ergebnis.body if hasattr(ergebnis, "body") else ergebnis
        if isinstance(roh, (bytes, bytearray)):
            roh = json.loads(roh.decode("utf-8"))
        elif isinstance(roh, str):
            roh = json.loads(roh)
        if not isinstance(roh, dict) or roh.get("error"):
            return _fehler(str((roh or {}).get("error") or "Unbekannte Antwort des Pools."))
        try:
            inhalt = roh["choices"][0]["message"]["content"]
        except Exception:
            inhalt = json.dumps(roh)[:2000]
        return _text(str(inhalt))

    return _fehler(f"Unbekanntes Werkzeug: {name}")


def register(app) -> None:
    """Routen fuer MCP an die App haengen."""

    @app.post("/mcp")
    async def mcp_endpunkt(request: Request):
        """JSON-RPC 2.0 fuer MCP. Antwortet immer mit 200 und einem JSON-RPC-Objekt."""
        from anthropic_api import get_current_user_any
        from database import SessionLocal

        # Anmeldung ueber denselben Weg wie die API (Authorization oder x-api-key).
        db: Session = SessionLocal()
        try:
            try:
                # get_current_user_any ist synchron und nimmt die Koepfe einzeln entgegen.
                user = get_current_user_any(
                    authorization=request.headers.get("authorization"),
                    x_api_key=request.headers.get("x-api-key"),
                    db=db,
                )
            except HTTPException as e:
                return JSONResponse(
                    status_code=401,
                    content={"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32001, "message": str(e.detail)}},
                )

            try:
                nachricht = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "Kein gueltiges JSON"}},
                )

            # Einzelaufruf oder Stapel
            einzeln = isinstance(nachricht, dict)
            anfragen = [nachricht] if einzeln else list(nachricht or [])
            antworten = []
            for anfrage in anfragen:
                if not isinstance(anfrage, dict):
                    continue
                methode = str(anfrage.get("method") or "")
                kennung = anfrage.get("id")
                params = anfrage.get("params") or {}

                # Benachrichtigungen (ohne id) bekommen keine Antwort.
                ist_benachrichtigung = kennung is None

                if methode == "initialize":
                    gewuenscht = str(params.get("protocolVersion") or PROTOKOLL_VERSION)
                    antworten.append({
                        "jsonrpc": "2.0", "id": kennung,
                        "result": {
                            # Die Version des Clients spiegeln, wenn wir sie kennen; sonst unsere.
                            "protocolVersion": gewuenscht or PROTOKOLL_VERSION,
                            "capabilities": {"tools": {"listChanged": False}},
                            "serverInfo": {"name": SERVER_NAME, "version": _version()},
                            "instructions": (
                                "CoMesh-Pool. Mit list_models die verfuegbaren Modelle anzeigen, "
                                "mit ask eine Frage an ein Modell schicken."
                            ),
                        },
                    })
                    continue

                if methode in ("notifications/initialized", "notifications/cancelled") or ist_benachrichtigung:
                    continue  # nichts zurueckgeben

                if methode == "ping":
                    antworten.append({"jsonrpc": "2.0", "id": kennung, "result": {}})
                    continue

                if methode == "tools/list":
                    antworten.append({"jsonrpc": "2.0", "id": kennung,
                                      "result": {"tools": _werkzeuge()}})
                    continue

                if methode == "tools/call":
                    name = str(params.get("name") or "")
                    argumente = params.get("arguments") or {}
                    try:
                        ergebnis = await _werkzeug_ausfuehren(name, argumente, user, db, request)
                    except Exception as e:  # noqa: BLE001
                        log.warning("MCP-Werkzeug %s fehlgeschlagen: %s", name, e)
                        ergebnis = _fehler(f"Werkzeug fehlgeschlagen: {e}")
                    antworten.append({"jsonrpc": "2.0", "id": kennung, "result": ergebnis})
                    continue

                antworten.append({
                    "jsonrpc": "2.0", "id": kennung,
                    "error": {"code": -32601, "message": f"Methode nicht unterstuetzt: {methode}"},
                })

            if not antworten:
                # Nur Benachrichtigungen: MCP erwartet 202 ohne Inhalt.
                return Response(status_code=202)
            return JSONResponse(content=antworten[0] if einzeln else antworten)
        finally:
            db.close()

    @app.get("/mcp")
    async def mcp_info():
        """Kurze Selbstauskunft - hilfreich beim Einrichten und fuer Healthchecks.

        Kein Streaming: dieser Server antwortet auf POST mit JSON. Claude kommt damit zurecht;
        der GET-Pfad dient nur der Orientierung.
        """
        return {
            "name": SERVER_NAME,
            "protocol": PROTOKOLL_VERSION,
            "transport": "streamable-http (JSON-Antworten, kein SSE)",
            "auth": "Authorization: Bearer <gpu_...> (oder x-api-key)",
            "tools": [w["name"] for w in _werkzeuge()],
        }


def _version() -> str:
    try:
        import pathlib

        # Portal-Version zuerst: der MCP-Server laeuft im Portal, nicht im Agenten.
        for kandidat in ("VERSION", "AGENT_VERSION"):
            p = pathlib.Path(__file__).with_name(kandidat)
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return "0"
