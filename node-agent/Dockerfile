FROM python:3.11-slim

WORKDIR /app

# Build-Kontext ist die **Repo-Wurzel** (docker-compose: context: .), damit die
# VERSION-Datei ins Image kommt. Mit dem alten Kontext ./node-agent fehlte sie,
# `_read_version()` fiel auf AGENT_VERSION_FALLBACK zurueck und der Agent meldete
# 0.6.0, waehrend das Portal 0.6.9 sagte. Direkt bauen daher:
#   docker build -f node-agent/Dockerfile -t comesh-agent:0.6.10 .
# (nicht `docker build node-agent/`).

# System deps for psutil / nvidia-ml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnvidia-ml-550 || true \
    && rm -rf /var/lib/apt/lists/*

COPY node-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY node-agent/agent.py node-agent/netinfo.py ./
# Eine Quelle fuer die Version: /version des Portals und die Kennung des Agenten
# lesen dieselbe Datei.
COPY VERSION ./VERSION
COPY AGENT_VERSION ./AGENT_VERSION
# Node credentials written by self-registration (LANA-89). Mount a volume here
# if you want them to survive a container rebuild.
ENV NODE_STATE_FILE=/data/node-state.json
RUN mkdir -p /data

EXPOSE 11435

ENV AGENT_PORT=11435

# Run uvicorn on AGENT_PORT (default 11435)
CMD ["sh", "-c", "uvicorn agent:app --host 0.0.0.0 --port ${AGENT_PORT:-11435}"]

# Setup check without starting the agent:
#   docker run --rm --env-file .env <image> python agent.py --check
