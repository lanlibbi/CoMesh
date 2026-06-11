"""
GPU-Pool Beispiel-Client

Zeigt, wie man den GPU-Pool als normalen OpenAI-kompatiblen Endpoint nutzt.
Funktioniert mit der `openai`-Bibliothek oder raw HTTP.

Verwendung:
    python client.py
    python client.py "Custom prompt"
    PORTAL_URL=http://localhost:8765 python client.py
"""

import os
import sys
import time
from typing import Optional

import httpx

PORTAL_URL = os.getenv("PORTAL_URL", "http://ai-lanlibbi:8765")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "qwen2.5-coder:14b")
DEFAULT_PROMPT = "Erkläre in zwei Sätzen, was ein GPU-Pool ist."


def chat_completion(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 500,
    timeout: float = 60.0,
) -> dict:
    """
    Schickt einen Chat-Completion-Request ans Portal.

    Returns dict mit:
      - content: assistant response
      - usage: token counts
      - headers: relevante Pool-Header
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    start = time.time()
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{PORTAL_URL}/v1/chat/completions",
            json=payload,
        )
    elapsed = time.time() - start

    response.raise_for_status()
    data = response.json()

    return {
        "content": data["choices"][0]["message"]["content"],
        "usage": data.get("usage", {}),
        "headers": {
            "node": response.headers.get("x-pool-node"),
            "tokens_in": response.headers.get("x-pool-tokens-in"),
            "tokens_out": response.headers.get("x-pool-tokens-out"),
            "cost_usd": response.headers.get("x-pool-cost-usd"),
        },
        "elapsed_s": round(elapsed, 2),
    }


def streaming_completion(
    prompt: str,
    model: str = DEFAULT_MODEL,
    timeout: float = 60.0,
):
    """
    Beispiel für Streaming-Responses (TODO im POC, OpenAI-kompatibel).
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }

    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "POST",
            f"{PORTAL_URL}/v1/chat/completions",
            json=payload,
        ) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    print(chunk, end="", flush=True)
    print()


def list_nodes() -> list:
    """Listet alle registrierten Nodes."""
    with httpx.Client() as client:
        response = client.get(f"{PORTAL_URL}/nodes/")
        response.raise_for_status()
        return response.json()


def pool_status() -> dict:
    """Holt den aktuellen Pool-Status."""
    with httpx.Client() as client:
        response = client.get(f"{PORTAL_URL}/pool/")
        response.raise_for_status()
        return response.json()


def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT

    print(f"=== GPU-Pool Client ===")
    print(f"Portal: {PORTAL_URL}")
    print(f"Model:  {DEFAULT_MODEL}")
    print(f"Prompt: {prompt}")
    print()

    # 1. Pool-Status
    print("--- Pool Status ---")
    status = pool_status()
    print(f"  Nodes total:   {status['total_nodes']}")
    print(f"  Nodes online:  {status['online_nodes']}")
    print(f"  Avg load:      {status['avg_load_pct']:.1f}%")
    print()

    # 2. Anfrage schicken
    print("--- Anfrage ---")
    result = chat_completion(prompt)

    print(f"Response ({result['elapsed_s']}s):")
    print(f"  {result['content']}")
    print()
    print(f"--- Pool-Details ---")
    print(f"  Verarbeitet von:  {result['headers']['node']}")
    print(f"  Tokens in:        {result['headers']['tokens_in']}")
    print(f"  Tokens out:       {result['headers']['tokens_out']}")
    print(f"  Kosten:           ${result['headers']['cost_usd']}")
    print()
    print(f"--- OpenAI-Usage ---")
    print(f"  {result['usage']}")


if __name__ == "__main__":
    main()
