# GPU-Pool Node-Agent

This is the agent that runs on **each contributor's machine** and connects
their GPU to the GPU-Pool community.

## What it does

1. **Heartbeat** — every `HEARTBEAT_SEC` seconds (default 30), it posts the
   GPU utilization, VRAM use, and active-job count to the portal at
   `POST /nodes/{id}/heartbeat`. The portal flips the node to "online" or
   "busy" based on the report.
2. **Request proxy** — exposes `POST /v1/chat/completions` (OpenAI-compatible)
   on `AGENT_PORT` (default 11435). The portal's load-balancer forwards
   community-pool jobs here, and the agent forwards them to the local
   Ollama daemon. Responses are reshaped back into the OpenAI shape and
   returned.

## Install with one command (no Python on the machine)

```bash
curl -fsSL https://<portal>/downloads/install.sh | sh     # macOS, Linux
```

```powershell
irm https://<portal>/downloads/install.ps1 | iex          # Windows
```

Both scripts download a **PyInstaller single binary**, verify its SHA-256 from a
sibling `.sha256` file (no checksum, no install), ask for the account key with a
hidden prompt, write `agent.env` with mode 600 and register a user-level service
(launchd / `systemd --user` / Task Scheduler) — no admin rights. Transport
defaults to `ws`, so no inbound port is needed. Build the binaries with
`./build.sh` / `.\build.ps1`. Details, removal and troubleshooting:
[`../docs/install.md`](../docs/install.md).

## Configuration (env vars)

| Variable      | Required | Default                          | Notes                                        |
|---------------|----------|----------------------------------|----------------------------------------------|
| `PORTAL_URL`  | yes      | (empty)                          | Base URL of the CoMesh portal, e.g. `http://portal-host:8765`. Deliberately no default: a wrong default sends heartbeats and keys to the wrong host. |
| `PORTAL_USER_KEY` | no   | (empty)                          | API key of an account with role provider/both. Set this *instead of* `NODE_ID`/`NODE_API_KEY` and the agent registers itself. |
| `ADVERTISE_HOST` | no    | auto-detected                    | Host the portal should dial. A name (DNS/mDNS/VPN) survives a DHCP lease change; an IP does not. |
| `NODE_ID`     | no       | (empty)                          | Numeric id returned by `POST /nodes/register` (fills itself in when the agent self-registers) |
| `NODE_API_KEY`| no       | (empty)                          | `agent_api_key` from registration            |
| `NODE_NAME`   | no       | hostname                         | Display name for a self-registered node      |
| `NODE_STATE_FILE` | no   | `<user config dir>/node-state.json` | Where self-registration stores the node credentials (mode 0600). The container sets `/data/node-state.json` explicitly. |
| `NODE_VRAM_GB` | no      | probed via NVML                  | VRAM this node offers. **Mandatory without an NVIDIA GPU** (macOS/Apple Silicon: unified memory) — otherwise 1 GB is assumed and the pool never routes a job here. |
| `NODE_SHARED_SECRET` | no | (empty)                         | Same value as the portal; the portal sends it as `X-Node-Secret` and the agent answers 401 without it. Empty = no lock (warns at start). |
| `OLLAMA_URL`  | no       | `http://localhost:11434`         | Local Ollama daemon                          |
| `AGENT_PORT`  | no       | `11435`                          | Port the agent listens on (HTTP transport only) |
| `HEARTBEAT_SEC` | no     | `30`                             | Heartbeat interval                           |
| `AGENT_TRANSPORT` | no   | `http`                           | `ws` = outbound WebSocket, no inbound port and no reachable address. The installer sets `ws`. |
| `COMESH_AGENT_ENV` | no  | `<user config dir>/agent.env`    | Config file to read; falls back to `.env` in the working directory. Real env vars always win. |
| `AGENT_LOG_FILE` | no    | (stdout only)                    | Rotated log file (2 MB × 3). Needed under launchd/Task Scheduler, where nothing captures stdout. |

## Run with Docker (recommended)

```bash
docker run -d --name gpu-pool-agent \
  --gpus all \
  --restart unless-stopped \
  -e PORTAL_URL=http://portal-host:8765 \
  -e NODE_ID=1 \
  -e NODE_API_KEY=node_xxxxx... \
  -p 11435:11435 \
  gpu-pool-node-agent
```

The agent needs `--gpus all` so NVML can see the device. It only reads
GPU stats — it does **not** need to share the GPU exclusively.

## Run without Docker (dev)

```bash
pip install -r requirements.txt
NODE_ID=1 NODE_API_KEY=node_xxx PORTAL_URL=http://portal-host:8765 \
  python agent.py
```

## Wire-up: addressing + security

The agent listens on port 11435. **Do not expose this port on the public
internet.** The portal needs to reach the agent at its `node_url`; a private
network (LAN, Docker network, or a mesh VPN if the hosts sit in different
places) is enough — no specific overlay is required.

Addressing is automatic: leave `node_url` empty at registration and the portal
takes the host from the agent's heartbeat (`ADVERTISE_HOST`, else the detected
outbound IP). Prefer a DNS/mDNS name over an IP so a DHCP lease change cannot
break the pool. See `../docs/network.md`.

If the portal cannot reach the agent at all (strict NAT, no inbound port), run
the agent with `AGENT_TRANSPORT=ws`: it opens an outbound WebSocket to the
portal, and the portal routes jobs over that connection instead.

## Build the single binary

```bash
./build.sh                 # macOS/Linux -> dist/comesh-agent-<os>-<arch> + .sha256
.\build.ps1                # Windows     -> dist\comesh-agent-windows-x86_64.exe + .sha256
```

`build.sh` creates a throwaway `.venv-build` from `requirements-build.txt` (no
`uvicorn[standard]` — the C/Rust extras are neither needed for a forwarding agent
nor buildable everywhere) and freezes `agent.py` with `comesh-agent.spec`. The spec
carries the hidden imports uvicorn resolves at runtime via `importlib`; without
them the binary starts and fails on the first request.

## Health & debug

```bash
curl -H "X-Node-Secret: $NODE_SHARED_SECRET" http://<node-host>:11435/health | jq
```

Returns Ollama reachability, GPU info, active jobs, and the node id. Without the
secret header `/health` answers `{"ok": true}` only. In **WS transport the HTTP
server does not start at all** — there is no local health endpoint to curl; watch
the log instead (`WS welcome received` means the portal accepted the node).

```bash
./comesh-agent --check      # config, portal reachability, advertised VRAM
./comesh-agent --version
```

`testkit/mock_portal.py` is a throwaway portal (API under `/api`, WebSocket under
`/agent/connect`, SPA fallback like nginx) for testing the installer without
touching the real portal:

```bash
MOCK_DOWNLOADS=$PWD/dist python -m uvicorn testkit.mock_portal:app --port 8799
```
