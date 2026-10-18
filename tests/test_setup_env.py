"""LANA-133: a second `setup.py` run must replace .env keys, not append them.

The installer used to open the `.env` in append mode and print "ich
ueberschreibe nur die Backend-Zeilen" while doing the opposite: every run
appended another `BACKEND=` / `OLLAMA_URL=` / `AGENT_PORT=` /
`AGENT_TRANSPORT=` block (plus another `# --- Backend: ... ---` marker).
Docker's last-value-wins hid it, but the file grew and the message lied.

These tests pin the contract:

1. two runs in a row leave every managed key exactly once,
2. a file already damaged by the old installer is repaired on the next run,
3. re-running with Enter (all defaults) keeps the configured values instead of
   overwriting them with the placeholder defaults,
4. user-owned keys (`PORTAL_USER_KEY`, `NODE_ID`, ...) survive untouched.

The installer is still interactive, so the tests drive it through a patched
`input()` with a scripted answer list and `chdir` into a temp dir.
"""

import importlib.util
from pathlib import Path

import pytest

SETUP_PATH = Path(__file__).resolve().parents[1] / "node-agent" / "setup.py"


def _load_setup():
    spec = importlib.util.spec_from_file_location("node_agent_setup", SETUP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup = _load_setup()

MANAGED = ("BACKEND", "OLLAMA_URL", "INFERENCE_URL", "AGENT_PORT", "AGENT_TRANSPORT", "PORTAL_URL", "ADVERTISE_HOST")

# Answer order: backend, url, portal url, advertise host, port, transport, nvidia
FIRST_RUN = ["1", "http://192.0.2.10:11434", "http://portal.lan:8765", "node-a.lan", "11435", "1", "1"]
# All Enter -> take the values already in .env as defaults
SECOND_RUN = [""] * 7


def key_lines(text):
    """{KEY: [values]} for every uncommented KEY=VALUE line."""
    values = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values.setdefault(key.strip(), []).append(value.strip())
    return values


def run_installer(monkeypatch, workdir, answers):
    answers = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.chdir(workdir)
    setup.main()


def test_two_runs_do_not_duplicate_keys(monkeypatch, tmp_path, capsys):
    run_installer(monkeypatch, tmp_path, FIRST_RUN)
    env_path = tmp_path / ".env"
    after_first = env_path.read_text()
    capsys.readouterr()

    # the operator now fills in a real key - it must survive the second run
    env_path.write_text(after_first.replace("dein-account-api-key", "gpu_realkey123"))

    run_installer(monkeypatch, tmp_path, SECOND_RUN)
    after_second = env_path.read_text()
    captured = capsys.readouterr().out

    lines = key_lines(after_second)
    for key in MANAGED:
        assert len(lines.get(key, [])) <= 1, f"{key} duplicated: {lines.get(key)}"

    # no growth: same keys, same number of lines
    assert after_second == after_first.replace("dein-account-api-key", "gpu_realkey123")
    assert len(after_second.splitlines()) == len(after_first.splitlines())

    # the second run keeps the configured values (Enter == default, not placeholder)
    assert lines["PORTAL_URL"] == ["http://portal.lan:8765"]
    assert lines["OLLAMA_URL"] == ["http://192.0.2.10:11434"]
    assert lines["AGENT_PORT"] == ["11435"]
    assert lines["AGENT_TRANSPORT"] == ["ws"]
    assert lines["ADVERTISE_HOST"] == ["node-a.lan"]
    assert lines["PORTAL_USER_KEY"] == ["gpu_realkey123"]

    # exactly one generated marker, and the message matches the real behaviour
    assert after_second.count("# --- Backend: ollama ---") == 1
    assert "ueberschreibe nur die Backend-Zeilen" not in captured
    assert "ersetze" in captured


def test_repairs_env_damaged_by_the_old_installer(monkeypatch, tmp_path, capsys):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# GPU-Pool Node-Agent Environment\n"
        "PORTAL_URL=http://portal.lan:8765\n"
        "PORTAL_USER_KEY=gpu_realkey123\n"
        "ADVERTISE_HOST=node-a.lan\n"
        "\n# --- Backend: ollama ---\n"
        "BACKEND=ollama\n"
        "OLLAMA_URL=http://192.0.2.10:11434\n"
        "AGENT_PORT=11435\n"
        "AGENT_TRANSPORT=ws\n"
        "\n# --- Backend: lmstudio ---\n"
        "BACKEND=openai\n"
        "INFERENCE_URL=http://192.0.2.10:1234\n"
        "AGENT_PORT=11435\n"
        "AGENT_TRANSPORT=ws\n"
    )

    # same backend as the last legacy block (lmstudio), everything else via Enter
    run_installer(monkeypatch, tmp_path, ["2", "", "", "", "", "", ""])
    text = env_path.read_text()
    lines = key_lines(text)

    for key in MANAGED:
        assert len(lines.get(key, [])) <= 1, f"{key} duplicated: {lines.get(key)}"
    assert lines["BACKEND"] == ["openai"]
    assert lines["INFERENCE_URL"] == ["http://192.0.2.10:1234"]
    assert "OLLAMA_URL" not in lines  # stale backend URL from the ollama run
    assert text.count("# --- Backend:") == 1
    assert lines["PORTAL_USER_KEY"] == ["gpu_realkey123"]


def test_backend_switch_replaces_url_key(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("PORTAL_URL=http://portal.lan:8765\nBACKEND=ollama\nOLLAMA_URL=http://x:11434\n")

    replaced, added, removed = setup.upsert_env(
        str(env_path),
        {"BACKEND": "openai", "INFERENCE_URL": "http://x:8000"},
        remove=["OLLAMA_URL"],
    )

    lines = key_lines(env_path.read_text())
    assert lines["BACKEND"] == ["openai"]
    assert lines["INFERENCE_URL"] == ["http://x:8000"]
    assert "OLLAMA_URL" not in lines
    assert "BACKEND" in replaced and "INFERENCE_URL" in added
    assert removed == ["OLLAMA_URL"]


def test_upsert_is_idempotent(tmp_path):
    env_path = tmp_path / ".env"
    updates = {"BACKEND": "ollama", "OLLAMA_URL": "http://x:11434", "AGENT_PORT": "11435"}

    setup.upsert_env(str(env_path), updates)
    first = env_path.read_text()
    replaced, added, removed = setup.upsert_env(str(env_path), updates)

    assert env_path.read_text() == first
    assert added == [] and removed == []
    assert replaced == ["BACKEND", "OLLAMA_URL", "AGENT_PORT"]


def test_commented_keys_are_not_touched(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("# NODE_ID=1\n# NODE_API_KEY=node_abc\nPORTAL_URL=http://portal.lan:8765\n")

    setup.upsert_env(str(env_path), {"BACKEND": "ollama", "PORTAL_URL": "http://new.lan:8765"})

    text = env_path.read_text()
    assert "# NODE_ID=1" in text
    assert "# NODE_API_KEY=node_abc" in text
    assert key_lines(text)["PORTAL_URL"] == ["http://new.lan:8765"]


@pytest.mark.parametrize(
    "env_line, expected",
    [
        ("BACKEND=ollama", "ollama"),
        ("BACKEND=openai\nINFERENCE_URL=http://host:1234", "lmstudio"),
        ("BACKEND=openai\nINFERENCE_URL=http://host:4000", "litellm"),
        ("BACKEND=openai\nINFERENCE_URL=http://host:8000", "openai"),
        ("", None),
    ],
)
def test_guess_backend_key(env_line, expected):
    env = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in env_line.splitlines() if "=" in line}
    assert setup.guess_backend_key(env) == expected
