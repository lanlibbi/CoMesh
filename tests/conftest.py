"""
Shared pytest fixtures for the GPU-Pool portal test suite.

Import order matters: `database.py` resolves its SQLite path from DATA_DIR at
import time, so we point DATA_DIR at a throwaway directory *before* importing
anything that pulls in the app.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# `test_features.py`, `test_ws_connectivity.py`, `test_ws_job_stream.py` and
# `test_ws_phase3_stream.py` are standalone check-scripts, not pytest modules:
# they drive a *running* portal over HTTP/WebSocket, print PASS/FAIL lines and
# exit via sys.exit(). Collecting them turns a green suite into 3 failures and
# 11 setup errors (async entrypoints without pytest-asyncio, no live server).
# Run them directly or via scripts/test_live.sh.
collect_ignore = [
    "test_features.py",
    "test_ws_connectivity.py",
    "test_ws_job_stream.py",
    "test_ws_phase3_stream.py",
    "e2e_dhcp_flow.py",
    # Standalone check-script: `python3 tests/test_auth_hardening.py`
    # (spawns uvicorn via tests/_testutil.py, has no pytest fixtures).
    "test_auth_hardening.py",
]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="gpu-pool-tests-")
os.environ.setdefault("DATA_DIR", _TMP_DATA_DIR)
os.environ.setdefault("SEED_KEY_PATH", os.path.join(_TMP_DATA_DIR, "seed_api_key.txt"))
# Deterministic admin bootstrap for the suite (documented bootstrap path).
TEST_ADMIN_KEY = "gpu_testadmin000000000000000000000000000000"
TEST_ADMIN_EMAIL = "admin@gpu-pool.local"
os.environ.setdefault("ADMIN_API_KEY", TEST_ADMIN_KEY)
os.environ.setdefault("ADMIN_EMAIL", TEST_ADMIN_EMAIL)
# LANA-139: `auth.require_admin` ist default-deny und antwortet 401 "Admin API
# is not configured", solange weder ADMIN_TOKEN noch ADMIN_EMAILS gesetzt sind —
# danach zaehlt `is_admin()` (role == "admin" ODER E-Mail in ADMIN_EMAILS). Ohne
# diese Zeile laeuft die halbe Suite in den Default-Deny, obwohl die Fixtures
# einen admin-Rollen-User anlegen. Wir setzen die dokumentierte Bootstrap-Adresse,
# nicht ADMIN_TOKEN: so wird der Rollen-Pfad von `is_admin()` mitgetestet.
os.environ.setdefault("ADMIN_EMAILS", TEST_ADMIN_EMAIL)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """
    LANA-139: die Token-Buckets sind prozessglobal und pro Scope/IP gekeyed.
    TestClient liefert fuer alle Tests dieselbe Client-IP ("testclient"), also
    lief die Session nach ~10 Registrierungen in 429 auf register:ip — ein
    Artefakt der Testreihenfolge, kein Verhalten des Codes. Vor jedem Test
    zuruecksetzen; wer ein Limit pruefen will, baut es im Test selbst auf.
    """
    from ratelimit import LIMITER

    LIMITER.reset()
    yield
    LIMITER.reset()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_headers():
    return {"Authorization": f"Bearer {os.environ['ADMIN_API_KEY']}"}


@pytest.fixture(scope="session")
def db_session():
    """Direct DB session for assertions that have no API surface (audit rows)."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
