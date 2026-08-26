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
| `PORTAL_URL`  | yes      | `http://100.126.79.111:8765`     | Base URL of the GPU-Pool portal              |
| `NODE_ID`     | yes      | (empty)                          | Numeric id returned by `POST /nodes/register`|
| `NODE_API_KEY`| yes      | (empty)                          | `agent_api_key` from registration            |
| `OLLAMA_URL`  | no       | `http://localhost:11434`         | Local Ollama daemon                          |
| `AGENT_PORT`  | no       | `11435`                          | Port the agent listens on                    |
| `HEARTBEAT_SEC` | no     | `30`                             | Heartbeat interval                           |

## Run with Docker (recommended)

```bash
docker run -d --name gpu-pool-agent \
  --gpus all \
  --restart unless-stopped \
  -e PORTAL_URL=http://100.126.79.111:8765 \
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
NODE_ID=1 NODE_API_KEY=node_xxx PORTAL_URL=http://100.126.79.111:8765 \
  python agent.py
```

## Wire-up: Tailscale + security

The agent listens on port 11435. **Do not expose this port on the public
internet.** Use Tailscale (or another mesh VPN) so the portal can reach
the agent on `tailscale_ip:11435`. The portal uses the value you provided
to `POST /nodes/register` (`tailscale_ip` + `port`) when forwarding
community-pool jobs.

If the contributor's machine only listens on localhost, register the node
with `tailscale_ip` set to `127.0.0.1` and run the agent on the same
machine as the portal (e.g. on a multi-GPU rig).

## Health & debug

```bash
curl http://<tailscale_ip>:11435/health | jq
```

Returns Ollama reachability, GPU info, active jobs, and the node id.
