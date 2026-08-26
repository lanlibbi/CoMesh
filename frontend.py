"""
Minimal HTML frontend for the GPU-Pool POC.

Pages:
  /             -> login/register
  /chat         -> chat UI
  /credits      -> buy credit packages
  /pool         -> community pool overview (new)
  /nodes        -> "share my GPU" page (new)
  /earnings     -> node-owner earnings dashboard (new)
  /agent        -> node-agent setup instructions (new)

Pages are static HTML + a small JS file per page. The JS calls the API
directly. Auth: the user logs in (or registers) and gets an API key,
which is then sent as `Authorization: Bearer <key>` on every request.
"""
import logging
import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

log = logging.getLogger("gpu-pool.frontend")

router = APIRouter(tags=["frontend"])

# Where static assets live (templates + static dir). When running from
# /app (Docker), the build copies ./frontend into /app/frontend.
FRONTEND_DIR = Path(os.environ.get("FRONTEND_DIR", "/app/frontend"))
if not FRONTEND_DIR.exists():
    # Local dev fallback: relative to this file
    here = Path(__file__).resolve().parent
    candidate = here / "frontend"
    if candidate.exists():
        FRONTEND_DIR = candidate


def _read(name: str) -> str:
    p = FRONTEND_DIR / name
    if not p.exists():
        return f"<!-- {name} not found at {p} -->"
    return p.read_text(encoding="utf-8")


# --- HTML pages ---
PAGES = [
    ("/docs",       "docs.html"),
    ("/",            "index.html"),
    ("/chat",        "chat.html"),
    ("/credits",     "credits.html"),
    ("/pool",        "pool.html"),
    ("/nodes",       "nodes.html"),
    ("/earnings",    "earnings.html"),
    ("/agent",       "agent.html"),
]

# --- JS bundles (each page references one) ---
JS_BUNDLES = ["app.js", "nodes.js", "pool.js", "earnings.js", "agent.js"]


for path, filename in PAGES:
    def _make(filename=filename):
        def handler():
            return HTMLResponse(_read(filename))
        return handler
    router.add_api_route(path, _make(), methods=["GET"], response_class=HTMLResponse)


# --- Static assets ---
def _static_response(name: str, media_type: str):
    p = FRONTEND_DIR / "static" / name
    if not p.exists():
        return HTMLResponse(f"/* {name} missing */", status_code=404, media_type="text/plain")
    return HTMLResponse(p.read_text(encoding="utf-8"), media_type=media_type)


def _app_js():
    return _static_response("app.js", "application/javascript")


def _app_css():
    return _static_response("app.css", "text/css")


router.add_api_route("/static/app.js", _app_js, methods=["GET"])
router.add_api_route("/static/app.css", _app_css, methods=["GET"])

# page-specific JS bundles
for js in JS_BUNDLES:
    if js == "app.js":
        continue  # already registered above
    fn_name = f"_{js.replace('.', '_')}"
    def _make(js=js):
        def handler():
            return _static_response(js, "application/javascript")
        return handler
    router.add_api_route(f"/static/{js}", _make(), methods=["GET"])
