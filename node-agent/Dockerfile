FROM python:3.11-slim

WORKDIR /app

# System deps for psutil / nvidia-ml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnvidia-ml-550 || true \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py netinfo.py ./
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
