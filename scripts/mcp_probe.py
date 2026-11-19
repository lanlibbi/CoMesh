#!/usr/bin/env python3
"""MCP-Sonde: prueft einen CoMesh-MCP-Endpunkt so, wie Claude ihn anspricht.

Nur Standardbibliothek, damit sie ueberall laeuft. Der Schluessel kommt aus der Umgebung und wird
nie ausgegeben — die Ausgabe ist zum Weitergeben geeignet.

    MCP_KEY=gpu_... python3 mcp_probe.py https://comesh.example.com

Geprueft wird: Selbstauskunft, Anmeldung, Handshake, Werkzeugliste, whoami, list_models und eine
echte Anfrage ueber `ask`.
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASIS = (sys.argv[1] if len(sys.argv) > 1 else "").rstrip("/")
KEY = (os.environ.get("MCP_KEY") or "").strip()
URL = BASIS + "/mcp"


def rpc(koerper, key=None):
    kopf = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if key:
        kopf["Authorization"] = "Bearer " + key
    req = urllib.request.Request(URL, data=json.dumps(koerper).encode(), headers=kopf, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            roh = r.read().decode()
            return r.status, (json.loads(roh) if roh else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def zeile(titel, wert):
    print(f"{titel:<24}{wert}")


print(f"Ziel: {URL}\n")

# 1. Selbstauskunft
try:
    with urllib.request.urlopen(URL, timeout=30) as r:
        d = json.load(r)
    zeile("Selbstauskunft", f"{r.status} | Protokoll {d.get('protocol')} | Werkzeuge {d.get('tools')}")
except Exception as e:  # noqa: BLE001
    zeile("Selbstauskunft", f"FEHLER {e}")

# 2. Ohne Schluessel
st, _ = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
zeile("ohne Schluessel", f"{st} (erwartet 401)")

if not KEY:
    print("\nKein MCP_KEY gesetzt - Ende. Der Rest braucht einen Konto-Schluessel.")
    sys.exit(0)

# 3. Handshake
st, d = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "mcp-probe", "version": "1"}}}, KEY)
if st != 200 or not isinstance(d, dict) or "result" not in d:
    zeile("Handshake", f"FEHLGESCHLAGEN {st} {d}")
    sys.exit(1)
zeile("Handshake", f"{st} | {d['result']['protocolVersion']} | "
                   f"{d['result']['serverInfo']['name']} {d['result']['serverInfo']['version']}")

# 4. Benachrichtigung
st, _ = rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, KEY)
zeile("Benachrichtigung", f"{st} (erwartet 202)")

# 5. Werkzeuge
st, d = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, KEY)
namen = [w["name"] for w in d["result"]["tools"]] if st == 200 and "result" in d else d
zeile("Werkzeuge", str(namen))

# 6. whoami
st, d = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "whoami", "arguments": {}}}, KEY)
if st == 200 and isinstance(d, dict) and "result" in d:
    zeile("whoami", d["result"]["content"][0]["text"].replace("\n", " | ")[:150])
else:
    zeile("whoami", f"{st} {d}")

# 7. list_models
st, d = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "list_models", "arguments": {}}}, KEY)
if st == 200 and isinstance(d, dict) and "result" in d:
    text = d["result"]["content"][0]["text"]
    modelle = [z for z in text.splitlines() if z.strip().startswith("- ")]
    zeile("list_models", f"{len(modelle)} Modelle | erste: {modelle[0][2:] if modelle else '—'}")
else:
    zeile("list_models", f"{st} {d}")

# 8. Echte Anfrage
st, d = rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
             "params": {"name": "ask",
                        "arguments": {"prompt": "Antworte nur mit dem Wort ok", "max_tokens": 8}}}, KEY)
if st == 200 and isinstance(d, dict) and "result" in d:
    erg = d["result"]
    zeile("ask", f"isError={erg.get('isError')} | {repr(erg['content'][0]['text'][:80])}")
else:
    zeile("ask", f"{st} {d}")

print("\nFertig.")
