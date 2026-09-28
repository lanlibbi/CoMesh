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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="gpu-pool-tests-")
os.environ.setdefault("DATA_DIR", _TMP_DATA_DIR)
os.environ.setdefault("SEED_KEY_PATH", os.path.join(_TMP_DATA_DIR, "seed_api_key.txt"))
# Deterministic admin bootstrap for the suite (documented bootstrap path).
TEST_ADMIN_KEY = "gpu_testadmin000000000000000000000000000000"
os.environ.setdefault("ADMIN_API_KEY", TEST_ADMIN_KEY)
os.environ.setdefault("ADMIN_EMAIL", "admin@gpu-pool.local")


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
