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

## Configuration (env vars)

| Variable      | Required | Default                          | Notes                                        |
|---------------|----------|----------------------------------|----------------------------------------------|
| `PORTAL_URL`  | yes      | (empty)                          | Base URL of the CoMesh portal, e.g. `http://portal-host:8765`. Deliberately no default: a wrong default sends heartbeats and keys to the wrong host. |
| `PORTAL_USER_KEY` | no   | (empty)                          | API key of an account with role provider/both. Set this *instead of* `NODE_ID`/`NODE_API_KEY` and the agent registers itself. |
| `ADVERTISE_HOST` | no    | auto-detected                    | Host the portal should dial. A name (DNS/mDNS/VPN) survives a DHCP lease change; an IP does not. |
| `NODE_ID`     | no       | (empty)                          | Numeric id returned by `POST /nodes/register` (fills itself in when the agent self-registers) |
| `NODE_API_KEY`| no       | (empty)                          | `agent_api_key` from registration            |
| `NODE_NAME`   | no       | hostname                         | Display name for a self-registered node      |
| `NODE_STATE_FILE` | no   | `/data/node-state.json`         | Where self-registration stores the node credentials (mode 0600) |
| `OLLAMA_URL`  | no       | `http://localhost:11434`         | Local Ollama daemon                          |
| `AGENT_PORT`  | no       | `11435`                          | Port the agent listens on                    |
| `HEARTBEAT_SEC` | no     | `30`                             | Heartbeat interval                           |

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

## Health & debug

```bash
curl http://<node-host>:11435/health | jq
```

Returns Ollama reachability, GPU info, active jobs, and the node id.
