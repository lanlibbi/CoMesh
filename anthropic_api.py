"""Anthropic-kompatible Schnittstelle, damit Claude Desktop den Pool als Anbieter nutzen kann.

Warum das der richtige Weg ist (Quelle: Anthropics Doku „Deploy Claude Desktop on 3P with an LLM
gateway", Stand 18.11.2026):

  * Claude Desktop kann einen eigenen Gateway als Inferenz-Anbieter nutzen
    (`inferenceProvider = gateway`), eingestellt über Developer → „Configure Third-Party
    Inference" oder per verwalteter Konfiguration (MDM/Admin-Konsole).
  * Der Gateway **muss die Anthropic Messages API sprechen**: `POST /v1/messages` mit Streaming und
    Werkzeugaufrufen.
  * `GET /v1/models` ist optional — implementiert man es, findet Claude Desktop die Modelle
    **selbst** und zeigt sie in der Modellauswahl. Genau das ist der Wunsch: lokale Modelle aus dem
    Portal in Claude Desktop sichtbar.

CoMesh spricht bisher OpenAI (`/v1/chat/completions`). Dieses Modul übersetzt in beide Richtungen und
ruft intern denselben Weg auf — Routing, Whitelist, Guthaben und Abrechnung bleiben an einer Stelle.

Kein Nachbau der Modelle: `x-api-key` (Anthropic-Kopf) und `Authorization: Bearer` werden beide
akzeptiert, weil Clients des Pools den letzteren benutzen.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from auth import resolve_token
from database import get_db
from models import User

router = APIRouter()

ANTHROPIC_VERSION = "2023-06-01"


# ---------------------------------------------------------------------------
# Zugang: x-api-key (Anthropic) oder Bearer (OpenAI/Clients des Pools)
# ---------------------------------------------------------------------------
def get_current_user_any(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Nutzer aus `x-api-key` oder `Authorization: Bearer …` bestimmen."""
    token = (x_api_key or "").strip()
    if not token and authorization:
        teile = authorization.split(None, 1)
        if len(teile) == 2 and teile[0].lower() == "bearer":
            token = teile[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing credentials: send x-api-key or Authorization: Bearer",
        )
    _key, user = resolve_token(db, token)
    return user


# ---------------------------------------------------------------------------
# Übersetzung: Anthropic Messages → OpenAI-Chat
# ---------------------------------------------------------------------------
def _text_aus_inhalt(inhalt: Any) -> str:
    """Anthropic-Inhalt (String oder Blöcke) zu reinem Text zusammenfassen."""
    if inhalt is None:
        return ""
    if isinstance(inhalt, str):
        return inhalt
    teile: List[str] = []
    for block in inhalt if isinstance(inhalt, list) else []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            teile.append(str(block.get("text") or ""))
    return "\n".join(t for t in teile if t)


def to_openai_request(body: Dict[str, Any]) -> Dict[str, Any]:
    """Anthropic-`/v1/messages`-Anfrage in die OpenAI-Form bringen, die CoMesh schon versteht.

    Übersetzt werden: `system` (String oder Blöcke), Textblöcke, Werkzeugaufrufe des Assistenten
    (`tool_use` → `tool_calls`) und Werkzeugergebnisse (`tool_result` → Rolle `tool`), `tools`
    (`input_schema` → `parameters`), `stop_sequences` → `stop`, `max_tokens`, `temperature`.
    """
    nachrichten: List[Dict[str, Any]] = []

    system = body.get("system")
    if system:
        nachrichten.append({"role": "system", "content": _text_aus_inhalt(system)})

    for nachricht in body.get("messages") or []:
        rolle = nachricht.get("role")
        inhalt = nachricht.get("content")

        # Werkzeugergebnisse kommen als Blöcke in einer user-Nachricht und werden zu
        # eigenen `tool`-Nachrichten — OpenAI erlaubt sie nicht als Text einer user-Nachricht.
        if isinstance(inhalt, list):
            werkzeug_ergebnisse = [b for b in inhalt if isinstance(b, dict) and b.get("type") == "tool_result"]
            for block in werkzeug_ergebnisse:
                nachrichten.append({
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id") or "",
                    "content": _text_aus_inhalt(block.get("content")),
                })
            texte = [b for b in inhalt if isinstance(b, dict) and b.get("type") == "text"]
            aufrufe = [b for b in inhalt if isinstance(b, dict) and b.get("type") == "tool_use"]
            if aufrufe:
                nachrichten.append({
                    "role": "assistant",
                    "content": "\n".join(str(b.get("text") or "") for b in texte) or None,
                    "tool_calls": [
                        {
                            "id": b.get("id") or f"toolu_{secrets.token_hex(8)}",
                            "type": "function",
                            "function": {
                                "name": b.get("name") or "",
                                "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False),
                            },
                        }
                        for b in aufrufe
                    ],
                })
            elif texte and not werkzeug_ergebnisse:
                nachrichten.append({"role": rolle, "content": "\n".join(str(b.get("text") or "") for b in texte)})
            continue

        nachrichten.append({"role": rolle, "content": inhalt if inhalt is not None else ""})

    payload: Dict[str, Any] = {
        "messages": nachrichten,
        "stream": False,   # der Aufrufer entscheidet; intern immer ungestreamt anstoßen
    }
    if body.get("model"):
        payload["model"] = body["model"]
    if body.get("max_tokens"):
        payload["max_tokens"] = body["max_tokens"]
    if body.get("temperature") is not None:
        payload["temperature"] = body["temperature"]
    if body.get("stop_sequences"):
        payload["stop"] = body["stop_sequences"]

    werkzeuge = body.get("tools")
    if werkzeuge:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": w.get("name") or "",
                    "description": w.get("description") or "",
                    "parameters": w.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
            for w in werkzeuge
            if isinstance(w, dict)
        ]
        # Anthropic: {"type":"auto"|"any"|"tool","name":...}; OpenAI: "auto"|"required"|{"type":"function",...}
        wahl = body.get("tool_choice")
        if isinstance(wahl, dict):
            typ = wahl.get("type")
            if typ == "any":
                payload["tool_choice"] = "required"
            elif typ == "tool" and wahl.get("name"):
                payload["tool_choice"] = {"type": "function", "function": {"name": wahl["name"]}}
            elif typ == "auto":
                payload["tool_choice"] = "auto"

    return payload


STOP_GRUENDE = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "content_filter": "end_turn",
}


def to_anthropic_response(openai_resp: Dict[str, Any], modell: str) -> Dict[str, Any]:
    """OpenAI-Antwort in eine Anthropic-Message umwandeln.

    `usage` bekommt `input_tokens`/`output_tokens`; die Cache-Felder melden wir ehrlich mit 0 —
    der Pool cached nicht über Anfragen hinweg, und erfundene Trefferzahlen wären schlimmer als
    Nullen (Claude Desktop zeigt sonst eine Ersparnis an, die es nicht gibt).
    """
    erste = (openai_resp.get("choices") or [{}])[0]
    nachricht = erste.get("message") or {}
    inhalt: List[Dict[str, Any]] = []

    text = nachricht.get("content")
    if isinstance(text, list):          # manche Backends liefern Blöcke
        text = _text_aus_inhalt(text)
    if text:
        inhalt.append({"type": "text", "text": str(text)})

    for aufruf in nachricht.get("tool_calls") or []:
        funktion = aufruf.get("function") or {}
        argumente = funktion.get("arguments")
        try:
            eingabe = json.loads(argumente) if isinstance(argumente, str) and argumente.strip() else {}
        except Exception:
            eingabe = {}
        inhalt.append({
            "type": "tool_use",
            "id": aufruf.get("id") or f"toolu_{secrets.token_hex(8)}",
            "name": funktion.get("name") or "",
            "input": eingabe,
        })

    if not inhalt:
        inhalt.append({"type": "text", "text": ""})

    benutzung = openai_resp.get("usage") or {}
    eingabe_tokens = int(benutzung.get("prompt_tokens") or 0)
    ausgabe_tokens = int(benutzung.get("completion_tokens") or 0)

    return {
        "id": f"msg_{secrets.token_hex(12)}",
        "type": "message",
        "role": "assistant",
        "model": openai_resp.get("model") or modell,
        "content": inhalt,
        "stop_reason": STOP_GRUENDE.get(erste.get("finish_reason") or "stop", "end_turn"),
        "stop_sequence": None,
        "usage": {
            "input_tokens": eingabe_tokens,
            "output_tokens": ausgabe_tokens,
            # Ehrlich: keine Treffer aus dem Cache, also 0 statt einer erfundenen Zahl.
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


def models_antwort_anthropic(modelle: List[Dict[str, Any]]) -> Dict[str, Any]:
    """`GET /v1/models` in der Form, die Claude Desktop zur Selbsterkennung liest."""
    daten = []
    for m in modelle:
        kennung = m.get("id") or m.get("name") or ""
        if not kennung:
            continue
        daten.append({
            "id": kennung,
            "display_name": m.get("display_name") or kennung,
            "created_at": m.get("created_at") or "2026-01-01T00:00:00Z",
            "type": "model",
        })
    return {
        "data": daten,
        "has_more": False,
        "first_id": daten[0]["id"] if daten else None,
        "last_id": daten[-1]["id"] if daten else None,
    }


# ---------------------------------------------------------------------------
# SSE: OpenAI-Deltas → Anthropic-Ereignisse
# ---------------------------------------------------------------------------
def sse(ereignis: str, daten: Dict[str, Any]) -> str:
    return f"event: {ereignis}\ndata: {json.dumps(daten, ensure_ascii=False)}\n\n"


async def stream_als_anthropic(quelle, modell: str, request: Request):
    """Übersetzt einen OpenAI-SSE-Strom in die Ereignisfolge der Messages API.

    Reihenfolge laut Anthropic: `message_start`, `content_block_start`,
    `content_block_delta`*, `content_block_stop`, `message_delta`, `message_stop`.
    Werkzeugaufrufe kommen als eigener Block mit `input_json_delta` — die Argumente werden
    gesammelt und am Blockende als ein Delta ausgeliefert, weil lokale Modelle sie ohnehin
    am Stück liefern.
    """
    kennung = f"msg_{secrets.token_hex(12)}"
    gesendet_start = False
    text_offen = False
    werkzeug_index = 0
    werkzeug_puffer: Dict[int, Dict[str, Any]] = {}
    ausgabe_tokens = 0
    stop_grund = "end_turn"

    yield sse("message_start", {
        "type": "message_start",
        "message": {
            "id": kennung, "type": "message", "role": "assistant", "model": modell,
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    })
    gesendet_start = True

    async for zeile in quelle:
        if await request.is_disconnected():
            return
        roh = zeile.decode("utf-8", "ignore") if isinstance(zeile, (bytes, bytearray)) else str(zeile)
        for teil in roh.split("\n"):
            teil = teil.strip()
            if not teil.startswith("data:"):
                continue
            daten = teil[5:].strip()
            if daten == "[DONE]":
                continue
            try:
                paket = json.loads(daten)
            except Exception:
                continue
            auswahl = (paket.get("choices") or [{}])[0]
            delta = auswahl.get("delta") or {}

            stueck = delta.get("content")
            if stueck:
                if not text_offen:
                    yield sse("content_block_start", {
                        "type": "content_block_start", "index": 0,
                        "content_block": {"type": "text", "text": ""},
                    })
                    text_offen = True
                yield sse("content_block_delta", {
                    "type": "content_block_delta", "index": 0,
                    "delta": {"type": "text_delta", "text": stueck},
                })

            for aufruf in delta.get("tool_calls") or []:
                platz = int(aufruf.get("index") or 0)
                eintrag = werkzeug_puffer.setdefault(platz, {"id": "", "name": "", "argumente": ""})
                if aufruf.get("id"):
                    eintrag["id"] = aufruf["id"]
                funktion = aufruf.get("function") or {}
                if funktion.get("name"):
                    eintrag["name"] = funktion["name"]
                if funktion.get("arguments"):
                    eintrag["argumente"] += funktion["arguments"]

            if auswahl.get("finish_reason"):
                stop_grund = STOP_GRUENDE.get(auswahl["finish_reason"], "end_turn")
            if paket.get("usage"):
                ausgabe_tokens = int((paket["usage"] or {}).get("completion_tokens") or ausgabe_tokens)

    if text_offen:
        yield sse("content_block_stop", {"type": "content_block_stop", "index": 0})

    for platz in sorted(werkzeug_puffer):
        eintrag = werkzeug_puffer[platz]
        index = (1 if text_offen else 0) + werkzeug_index
        werkzeug_index += 1
        yield sse("content_block_start", {
            "type": "content_block_start", "index": index,
            "content_block": {
                "type": "tool_use",
                "id": eintrag["id"] or f"toolu_{secrets.token_hex(8)}",
                "name": eintrag["name"], "input": {},
            },
        })
        yield sse("content_block_delta", {
            "type": "content_block_delta", "index": index,
            "delta": {"type": "input_json_delta", "partial_json": eintrag["argumente"] or "{}"},
        })
        yield sse("content_block_stop", {"type": "content_block_stop", "index": index})

    if not gesendet_start:
        return
    yield sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_grund, "stop_sequence": None},
        "usage": {"output_tokens": ausgabe_tokens},
    })
    yield sse("message_stop", {"type": "message_stop"})


# ---------------------------------------------------------------------------
# Routen
# ---------------------------------------------------------------------------
def _felder(body: Dict[str, Any]) -> Tuple[bool, str, bool]:
    """(stream?, modell, max_tokens gesetzt?) aus der Anfrage."""
    modell = str(body.get("model") or "")
    return bool(body.get("stream")), modell, bool(body.get("max_tokens"))


# Namen im Claude-Stil, die Claude Code und Claude Desktop in der Auswahl akzeptieren.
CLAUDE_ALIASE = ("claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5")

# Einstellungsschluessel je Alias. Claude zeigt in seiner Auswahl nur diese drei Namen und das
# aktuelle Modell - die lesbaren Kennungen erscheinen dort nicht. Damit die Auswahl etwas bewirkt,
# braucht jeder Alias ein eigenes Ziel.
ALIAS_SETTINGS = {
    "claude-sonnet-4-5": "alias_target_sonnet_4_5",
    "claude-opus-4-1": "alias_target_opus_4_1",
    "claude-haiku-4-5": "alias_target_haiku_4_5",
}


def alias_ziele(verfuegbare_modelle=None, default_modell: str = "", gespeichert=None) -> dict:
    """Zielmodell je Claude-Alias.

    `gespeichert` kommt aus den Einstellungen (Alias -> Modellname). Ein Eintrag gilt nur, wenn das
    Modell auch im Katalog steht; sonst faellt der Alias auf das gemeinsame Ziel zurueck, statt ins
    Leere zu zeigen.
    """
    gemeinsam = alias_ziel(verfuegbare_modelle, default_modell)
    erlaubt = [m for m in (verfuegbare_modelle or []) if (m or "").strip()]
    ziele = {}
    for alias in CLAUDE_ALIASE:
        wahl = str((gespeichert or {}).get(alias) or "").strip()
        ziele[alias] = wahl if (wahl and (not erlaubt or wahl in erlaubt)) else gemeinsam
    return ziele


def alias_ziel(verfuegbare_modelle=None, default_modell: str = "") -> str:
    """Auf welches echte Modell ein Claude-Alias zeigt.

    Reihenfolge: `ANTHROPIC_ALIAS_TARGET` (ausdrueckliche Angabe des Betreibers), sonst
    `DEFAULT_MODEL` des Portals, sonst das erste Modell, das der Pool gerade anbietet.
    Gibt "" zurueck, wenn es nichts gibt — dann werden auch keine Aliase angeboten.
    """
    aus_env = (os.environ.get("ANTHROPIC_ALIAS_TARGET") or "").strip()
    if aus_env:
        return aus_env
    # Vorrang hat, was das Konto wirklich nutzen darf: `verfuegbare_modelle` ist bereits mit
    # can_use_model() gefiltert. Erst danach der Portal-Standardwert - sonst zeigt der Alias auf
    # ein Modell, das beim ersten Aufruf mit 403 abgelehnt wird (genau das ist passiert).
    for name in (verfuegbare_modelle or []):
        if (name or "").strip():
            return name.strip()
    if (default_modell or "").strip():
        return default_modell.strip()
    return ""


PRAEFIX = "claude-custom-"


def modell_slug(modell: str) -> str:
    """Lesbarer Teil einer Kennung: 'qwen2.5-coder:7b' -> 'qwen2-5-coder-7b'."""
    roh = (modell or "").strip().lower()
    if not roh:
        return ""
    roh = roh.split("/")[-1]                      # Registry-Pfade abschneiden
    roh = re.sub(r"[^a-z0-9]+", "-", roh).strip("-")
    return roh[:48]


def claude_kennung(modell: str, vergeben=None) -> str:
    """Claude-taugliche, LESBARE Kennung fuer ein echtes Modell.

    `vergeben` ist die Menge bereits benutzter Kennungen; bei Gleichstand (zwei Modelle ergeben
    denselben Slug, z.B. 'qwen3:8b' und 'qwen3-8b') bekommt das zweite einen kurzen Zusatz aus dem
    Modellnamen, damit die Kennung eindeutig bleibt.
    """
    roh = (modell or "").strip()
    if not roh:
        return ""
    slug = modell_slug(roh) or "modell"
    kennung = PRAEFIX + slug
    if vergeben and kennung in vergeben:
        zusatz = re.sub(r"[^a-z0-9]", "", roh.lower())[:4] or "x1"
        kennung = f"{PRAEFIX}{slug}-{zusatz}"
        lauf = 2
        while kennung in vergeben:
            kennung = f"{PRAEFIX}{slug}-{zusatz}{lauf}"
            lauf += 1
    return kennung


def modell_aus_kennung(kennung: str) -> str:
    """Umkehrung von claude_kennung(). Gibt "" zurueck, wenn es keine solche Kennung ist."""
    name = (kennung or "").strip()
    if not name.startswith(PRAEFIX):
        return ""
    kodiert = name[len(PRAEFIX):]
    auffuellen = "=" * (-len(kodiert) % 4)
    try:
        return base64.urlsafe_b64decode((kodiert + auffuellen).encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def modell_aus_slug(kennung: str, kandidaten=None) -> str:
    """Lesbare Kennung gegen die vorhandenen Modelle abgleichen.

    Die Kennung ist nicht mehr umkehrbar (aus 'qwen2-5-coder-7b' laesst sich 'qwen2.5-coder:7b'
    nicht rekonstruieren), deshalb wird verglichen: welches Modell ergibt denselben Slug?
    """
    name = (kennung or "").strip()
    if not name.startswith(PRAEFIX):
        return ""
    rest = name[len(PRAEFIX):]
    for modell in (kandidaten or []):
        if (modell or "").strip() and modell_slug(modell) == rest:
            return modell
    # Zusatz wegen Gleichstand abschneiden und erneut versuchen.
    ohne = re.sub(r"-[a-z0-9]{1,6}\d*$", "", rest)
    if ohne != rest:
        for modell in (kandidaten or []):
            if (modell or "").strip() and modell_slug(modell) == ohne:
                return modell
    return ""


def modell_aufloesen(angefragt: str, default_modell: str = "", erlaubte=None, kandidaten=None,
                     ziele=None) -> str:
    """Claude-Alias -> echtes Modell. Alles andere bleibt unveraendert.

    Ohne diese Abbildung schickt das Portal "claude-sonnet-4-5" an Ollama, und das Modell gibt es
    dort nicht (404). Nur Namen aus CLAUDE_ALIASE werden ersetzt, damit ein Konto nicht
    versehentlich umgebogen wird, das ein echtes Modell gleichen Namens meint.
    """
    name = (angefragt or "").strip()
    ziel = name
    # 1. Kennung eines bestimmten Modells. Zwei Formen:
    #    * lesbar (claude-custom-qwen2-5-coder-7b)  -> Abgleich mit den vorhandenen Modellen,
    #    * alt (claude-custom-<base64>)             -> rueckuebersetzen, damit nichts bricht.
    echt = modell_aus_slug(name, kandidaten or erlaubte) or modell_aus_kennung(name)
    if echt:
        ziel = echt
    # 2. Die drei festen Aliase zeigen auf das eingestellte Zielmodell.
    elif name in CLAUDE_ALIASE:
        # Eigenes Ziel des Alias, sonst das gemeinsame. `ziele` kommt aus den Einstellungen.
        ziel = str((ziele or {}).get(name) or "").strip() or alias_ziel(None, default_modell) or default_modell
    # 3. Alles andere ist ein echter Modellname und bleibt unangetastet.

    # Liegt das Ziel nicht in der Freigabeliste des Kontos, das erste freigegebene Modell nehmen.
    # Sonst scheitert der erste Chat mit 403, obwohl der Client nur einen Alias geschickt hat.
    # Nur wenn ein Alias oder eine Kennung im Spiel war. Ein echter Modellname, der nicht
    # freigegeben ist, muss weiter mit 403 scheitern - stillschweigend ein anderes Modell zu
    # liefern waere schlimmer als eine ehrliche Absage.
    # `name.startswith(PRAEFIX)` faengt auch die Kennung eines Modells ab, das nicht mehr im
    # Katalog steht: dann ist sie nicht aufloesbar, und ein Ausweichen ist besser als einen
    # unbrauchbaren Namen ans Backend zu schicken.
    if (ziel != name or name.startswith(PRAEFIX)) and erlaubte is not None:
        liste = [x for x in (erlaubte or []) if (x or "").strip()]
        if liste and ziel not in liste:
            return liste[0]
    return ziel


def register(app, *, default_modell: str) -> None:
    """Hängt die Anthropic-Route an die bestehende App.

    Der vorhandene OpenAI-Handler wird **zur Laufzeit** geholt (`from main import
    chat_completions`): dieselbe Funktion, damit Routing, Whitelist, Guthaben und Abrechnung nicht
    zweimal gepflegt werden. Ein Import auf Modulebene wäre ein Zyklus und würde beim Start
    fehlschlagen, weil `main` dieses Modul erst einbindet.
    """

    @app.post("/v1/messages")
    async def messages(
        request: Request,
        body: Dict[str, Any],
        user: User = Depends(get_current_user_any),
        db: Session = Depends(get_db),
    ):
        """Anthropic Messages API — von Claude Desktop als Gateway genutzt."""
        from pydantic import ValidationError

        from main import ChatCompletionRequest, chat_completions

        if not body.get("messages"):
            raise HTTPException(status_code=422, detail="messages fehlt")
        if not body.get("max_tokens"):
            # Anthropic verlangt es; ein Default waere geraten. Deshalb klar sagen.
            raise HTTPException(status_code=422, detail="max_tokens ist Pflicht (Anthropic Messages API)")

        offen = to_openai_request(body)
        offen["stream"] = False   # Streaming übersetzen wir selbst aus dem OpenAI-Strom
        # Claude schickt seinen eigenen Modellnamen; dahinter muss ein Modell des Pools laufen.
        # Wichtig: der Name wird IM KOERPER ersetzt, nicht nur in der Variable - sonst geht
        # "claude-sonnet-4-5" an das Backend und Ollama antwortet 404.
        try:
            _freigaben = user.get_allowed_models()
        except Exception:
            _freigaben = None
        # Lesbare Kennungen (claude-custom-qwen2-5-coder-7b) sind nicht umkehrbar; sie werden
        # gegen den aktuellen Katalog abgeglichen. Nur bei solchen Namen wird der Katalog geholt.
        _kandidaten = None
        _angefragt = str(offen.get("model") or "")
        if _angefragt.startswith("claude-custom-"):
            try:
                from main import _modell_katalog

                _kandidaten = [ (m.get("name") or m.get("model")) for m in await _modell_katalog(user, db) ]
            except Exception:
                _kandidaten = None
        # Ziele je Alias aus den Einstellungen; ohne sie zeigen alle drei Aliase auf dasselbe
        # Modell und die Auswahl in Claude waere wirkungslos.
        try:
            from main import _alias_ziele_aus_db

            _ziele = alias_ziele(_kandidaten or _freigaben, default_modell, _alias_ziele_aus_db(db))
        except Exception:
            _ziele = None
        modell = modell_aufloesen(_angefragt or default_modell, default_modell,
                                  _freigaben, _kandidaten, _ziele) or default_modell
        if modell:
            offen["model"] = modell

        try:
            anfrage = ChatCompletionRequest(**offen)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=f"Anfrage nicht übersetzbar: {e.errors()[:2]}")

        streaming, _, _ = _felder(body)
        if streaming:
            # Der bestehende Streaming-Weg liefert OpenAI-SSE; wir hängen uns davor.
            antwort = await chat_completions(request=request, body=anfrage.model_copy(update={"stream": True}), user=user, db=db)
            return StreamingResponse(
                stream_als_anthropic(antwort.body_iterator, modell, request),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
            )

        ergebnis = await chat_completions(request=request, body=anfrage, user=user, db=db)
        rohdaten = ergebnis.body if hasattr(ergebnis, "body") else ergebnis
        if isinstance(rohdaten, (bytes, bytearray)):
            rohdaten = json.loads(rohdaten.decode("utf-8"))
        elif isinstance(rohdaten, str):
            rohdaten = json.loads(rohdaten)
        elif hasattr(rohdaten, "model_dump"):
            rohdaten = rohdaten.model_dump()
        return to_anthropic_response(rohdaten, modell)

    return app
