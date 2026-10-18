"""LANA-48 / setup UX: `python agent.py --check` must honour the generated .env.

The interactive installer (node-agent/setup.py) writes a `.env` next to
`docker-compose.yml` and then tells the operator to verify the setup with
`docker compose run --rm agent python agent.py --check`. docs/node-agent.md
advertises the direct form `python agent.py --check` as well — and that path
used to ignore `.env` completely, so a correctly configured node was reported as
"PORTAL_URL is unset". These tests pin both directions: the file is read, and an
empty environment still reports a missing configuration instead of inventing one.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT = REPO_ROOT / "node-agent" / "agent.py"

# Anything the check reads from the environment would mask what .env provides.
_STRIPPED = {
    "PORTAL_URL",
    "PORTAL_USER_KEY",
    "NODE_ID",
    "NODE_API_KEY",
    "AGENT_TRANSPORT",
    "AGENT_PORT",
    "OLLAMA_URL",
    "INFERENCE_URL",
    "BACKEND",
    "ADVERTISE_HOST",
    "HEARTBEAT_SEC",
}


def _run_check(cwd: Path) -> str:
    env = {k: v for k, v in os.environ.items() if k not in _STRIPPED}
    proc = subprocess.run(
        [sys.executable, str(AGENT), "--check"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    # The check exits non-zero whenever the node cannot start (unreachable
    # portal, missing credentials); only the printed report is under test here.
    return proc.stdout + proc.stderr


def test_check_reads_the_dotenv_the_installer_writes(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "PORTAL_URL=http://127.0.0.1:9\n"
        "PORTAL_USER_KEY=dummy-account-key\n"
        "AGENT_TRANSPORT=ws\n",
        encoding="utf-8",
    )

    out = _run_check(tmp_path)

    assert "portal URL      : http://127.0.0.1:9" in out
    assert "transport       : ws" in out
    assert "(unset" not in out


def test_check_without_dotenv_still_reports_the_missing_configuration(
    tmp_path: Path,
) -> None:
    out = _run_check(tmp_path)

    assert "portal URL      : (unset" in out
    assert "transport       : http" in out
