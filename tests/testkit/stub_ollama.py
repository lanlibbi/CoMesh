"""Testdoppel für Ollama — damit die Anthropic-Schnittstelle ohne GPU prüfbar ist.

Nur die zwei Endpunkte, die der Pool anspricht: `/api/tags` (Modellkatalog) und `/api/chat`
(Antwort, wahlweise als NDJSON-Strom). Kein Anspruch auf Vollständigkeit — es soll belegen, dass
die Überschicht stimmt, nicht Ollama ersetzen.
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELLE = [{"name": "testmodell:7b", "model": "testmodell:7b", "modified_at": "2026-11-18T10:00:00Z"}]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):        # kein Zugriffslog im Testlauf
        return

    def _json(self, daten, status=200):
        roh = json.dumps(daten).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self):
        if self.path.startswith("/api/tags"):
            self._json({"models": MODELLE})
        else:
            self._json({"error": "nicht vorhanden"}, 404)

    def do_POST(self):
        laenge = int(self.headers.get("Content-Length") or 0)
        anfrage = json.loads(self.rfile.read(laenge) or b"{}")

        if not self.path.startswith("/api/chat"):
            self._json({"error": "nicht vorhanden"}, 404)
            return

        werkzeuge = anfrage.get("tools") or []
        stream = bool(anfrage.get("stream"))

        # Fragt der Aufrufer ein Werkzeug an? Dann eine tool_calls-Antwort liefern, damit die
        # Übersetzung in beide Richtungen geprüft wird.
        letzte = (anfrage.get("messages") or [{}])[-1]
        will_werkzeug = bool(werkzeuge) and "WERKZEUG" in json.dumps(anfrage, ensure_ascii=False)

        if not stream:
            if will_werkzeug:
                self._json({
                    "model": anfrage.get("model"),
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "function": {"name": "uhrzeit", "arguments": json.dumps({"zone": "UTC"})}
                        }],
                    },
                    "done": True,
                    "prompt_eval_count": 11,
                    "eval_count": 7,
                })
                return
            self._json({
                "model": anfrage.get("model"),
                "message": {"role": "assistant", "content": "Antwort vom Testdoppel."},
                "done": True,
                "prompt_eval_count": 11,
                "eval_count": 7,
            })
            return

        # Streaming: NDJSON, wie Ollama es liefert
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Connection", "close")
        self.end_headers()
        for stueck in ("Antwort ", "vom ", "Testdoppel."):
            zeile = json.dumps({"model": anfrage.get("model"),
                                "message": {"role": "assistant", "content": stueck},
                                "done": False})
            self.wfile.write((zeile + "\n").encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.01)
        self.wfile.write((json.dumps({"model": anfrage.get("model"), "message": {"role": "assistant", "content": ""},
                                      "done": True, "prompt_eval_count": 11, "eval_count": 7}) + "\n").encode("utf-8"))
        self.wfile.flush()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 11888
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
