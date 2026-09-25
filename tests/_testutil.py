"""
Shared helpers for the GPU-Pool test scripts.

Kept deliberately small: the suites are plain scripts (run with `python3`), not
pytest modules, so they can run against either a live portal (GPU_POOL_API) or
an in-process uvicorn server with a throwaway SQLite DB.

`start_test_server()` boots the real `main:app` on a free port with
DATA_DIR pointing at a temp directory, and pre-configures the deployment
switches the tests need:

  * X-Admin-Token / ADMIN_TOKEN   - the suite registers users through the
    admin-authenticated path (POST /admin/users) where it matters; /auth/register
    stays public and is used where the public signup path is under test.
  * LOGIN_MAX_FAILURES etc.       - left at their defaults so the brute-force
    test exercises real production thresholds.
"""
import os
import socket
import sys
import time

TEST_ADMIN_TOKEN = "test-admin-token"
ADMIN_HEADERS = {"X-Admin-Token": TEST_ADMIN_TOKEN}


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def configure_test_env(data_dir: str) -> None:
    """Environment the in-process server must see. Call before importing main."""
    os.environ["DATA_DIR"] = data_dir
    os.environ["SEED_KEY_PATH"] = os.path.join(data_dir, "seed_api_key.txt")
    os.environ.setdefault("ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    os.environ.setdefault("ADMIN_EMAILS", "admin@example.com")


async def start_test_server(*, purge_modules: bool = True):
    """
    Start uvicorn in a background asyncio task against a private DATA_DIR.

    Returns (port, app, server, task, test_data_dir). The caller owns shutdown.
    """
    import asyncio
    import uvicorn

    proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if proj_root not in sys.path:
        sys.path.insert(0, proj_root)

    test_data_dir = os.path.join("/tmp", f"gpu_pool_test_{os.getpid()}_{int(time.time())}")
    os.makedirs(test_data_dir, exist_ok=True)
    configure_test_env(test_data_dir)

    if purge_modules:
        for mod in ("main", "database", "models", "ws", "pool", "auth",
                    "nodes", "payments", "frontend", "ratelimit"):
            sys.modules.pop(mod, None)

    import main as main_mod  # noqa: E402
    app = main_mod.app
    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.1)
    else:
        raise RuntimeError("test server failed to start")
    return port, app, server, task, test_data_dir


async def stop_test_server(server, task, data_dir) -> None:
    import asyncio
    import shutil
    try:
        if server:
            server.should_exit = True
        if task:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                task.cancel()
    finally:
        if data_dir and os.path.isdir(data_dir):
            shutil.rmtree(data_dir, ignore_errors=True)
