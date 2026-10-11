#!/usr/bin/env python3
"""CoMesh Alpine-UI ausliefern — statische Dateien plus /api/*-Proxy auf das Portal.

Ersetzt das, was im Produktions-Container nginx tut: `frontend-alpine/nginx.conf`
serviert die Oberflaeche und proxied `/api/*` an die API, wobei das Praefix
abgeschnitten wird (`/api/v1/me` -> `/v1/me`).

Warum nicht `python -m http.server`: der kennt nur GET und HEAD. Die Oberflaeche
schickt aber POST (`/api/auth/login`), PUT (`/api/admin/settings`) und PATCH
(`/api/admin/users/{id}/quota`). Ohne Proxy antwortet der Datei-Server mit
`501 Unsupported method ('POST')` — und genau das sieht man dann im Login-Formular
als rohe HTML-Fehlerseite.

Betrieb:
    PORTAL_URL=http://127.0.0.1:8941 PORT=8942 python3 tools/ui_server.py

Damit ist die Oberflaeche same-origin mit der API: man braucht kein `?api=` mehr,
und es gibt keine CORS-Sonderfaelle.
"""

from __future__ import annotations

import os
import posixpath
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORTAL_URL = os.environ.get("PORTAL_URL", "http://127.0.0.1:8941").rstrip("/")
ROOT = os.environ.get("UI_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
) + "/frontend-alpine"

# Hop-by-hop headers duerfen nicht weitergereicht werden (RFC 7230 6.1); die
# Laenge setzen wir selbst, sonst haetten wir sie doppelt.
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length",
}
# Weiterreichen, was die API auswertet. Authorization traegt den Bearer-Key,
# Idempotency-Key schuetzt die schreibenden Admin-Routen gegen Doppelklick.
_FORWARD = ("authorization", "content-type", "accept", "idempotency-key")


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, format, *args):  # ruhigeres Log, eine Zeile pro Request
        print(f"{self.address_string()} {format % args}", flush=True)

    # --- alles unter /api/ geht an das Portal ---------------------------------
    def _is_api(self) -> bool:
        return self.path == "/api" or self.path.startswith("/api/")

    def _proxy(self, method: str) -> None:
        target = PORTAL_URL + self.path[len("/api"):]
        body = None
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            body = self.rfile.read(length) if length else b""

        req = urllib.request.Request(target, data=body, method=method)
        for header in _FORWARD:
            value = self.headers.get(header)
            if value:
                req.add_header(header, value)

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                self._relay(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as exc:
            # 4xx/5xx sind regulaere Antworten der API (401 beim Login, 403 ohne
            # Adminrolle) — die muessen unveraendert beim Client ankommen.
            self._relay(exc.code, exc.headers, exc.read())
        except Exception as exc:  # Portal nicht erreichbar
            payload = f'{{"detail":"Portal {PORTAL_URL} nicht erreichbar: {exc}"}}'.encode()
            self._relay(502, {"Content-Type": "application/json"}, payload)

    def _relay(self, status: int, headers, payload: bytes) -> None:
        self.send_response(status)
        for name, value in (headers.items() if hasattr(headers, "items") else []):
            if name.lower() not in _HOP_BY_HOP:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self._is_api():
            return self._proxy("GET")
        return super().do_GET()

    def do_HEAD(self):
        if self._is_api():
            return self._proxy("HEAD")
        return super().do_HEAD()

    def do_POST(self):
        return self._proxy("POST")

    def do_PUT(self):
        return self._proxy("PUT")

    def do_PATCH(self):
        return self._proxy("PATCH")

    def do_DELETE(self):
        return self._proxy("DELETE")

    # SPA-Fallback wie in nginx.conf: unbekannter Pfad ohne Dateiendung -> index.html
    def send_head(self):
        path = self.translate_path(self.path)
        if not os.path.exists(path) and "." not in posixpath.basename(self.path):
            self.path = "/index.html"
        return super().send_head()


def main() -> None:
    port = int(os.environ.get("PORT", "8942"))
    if not os.path.isdir(ROOT):
        raise SystemExit(f"UI_ROOT existiert nicht: {ROOT}")
    print(f"CoMesh UI auf http://0.0.0.0:{port}  (statisch aus {ROOT})", flush=True)
    print(f"  /api/* -> {PORTAL_URL}/*", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
