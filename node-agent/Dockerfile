FROM python:3.11-slim

WORKDIR /app

# System deps for psutil / nvidia-ml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnvidia-ml-550 || true \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .

EXPOSE 11435

ENV AGENT_PORT=11435

# Run uvicorn on AGENT_PORT (default 11435)
CMD ["sh", "-c", "uvicorn agent:app --host 0.0.0.0 --port ${AGENT_PORT:-11435}"]
