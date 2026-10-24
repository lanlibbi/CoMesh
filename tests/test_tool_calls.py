"""Werkzeugaufrufe: kommt `tools` an, und kommt `tool_calls` zurück?

Ohne diese beiden Richtungen kann kein Agent über CoMesh arbeiten. Der Test prüft die drei
Stellen, an denen es schiefgehen kann, ohne echten Ollama:

  * das Anfrage-Schema nimmt Werkzeuge und Werkzeug-Antworten an,
  * die Nutzlast für Ollama enthält sie (und lässt `content: null` weg, wenn nur aufgerufen wird),
  * die Antwortform aus dem Pool behält `tool_calls` und meldet `finish_reason="tool_calls"`.
"""
from main import ChatCompletionRequest, _bau_ollama_payload
from pool import _ollama_to_openai_shape

WERKZEUG = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write text to a file",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
}


def test_request_akzeptiert_werkzeuge_und_antworten():
    req = ChatCompletionRequest(
        model="qwen3.8:latest",
        messages=[
            {"role": "user", "content": "Create hello.py"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "write_file", "arguments": "{\"path\":\"hello.py\"}"}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": "written"},
        ],
        tools=[WERKZEUG],
        tool_choice="auto",
    )
    assert req.tools[0]["function"]["name"] == "write_file"
    assert req.messages[1].tool_calls[0]["id"] == "call_1"
    assert req.messages[2].tool_call_id == "call_1"


def test_nutzlast_enthaelt_werkzeuge():
    req = ChatCompletionRequest(
        model="qwen3.8:latest",
        messages=[{"role": "user", "content": "hi"}],
        tools=[WERKZEUG],
        tool_choice="auto",
        max_tokens=256,
    )
    payload = _bau_ollama_payload("qwen3.8:latest", req)
    assert payload["tools"] == [WERKZEUG]
    assert payload["tool_choice"] == "auto"
    assert payload["options"]["num_predict"] == 256
    assert payload["messages"] == [{"role": "user", "content": "hi"}]


def test_nutzlast_ohne_werkzeuge_bleibt_schlank():
    req = ChatCompletionRequest(model="llama3.1:8b", messages=[{"role": "user", "content": "hi"}])
    payload = _bau_ollama_payload("llama3.1:8b", req)
    assert "tools" not in payload
    assert "tool_choice" not in payload


def test_aufruf_ohne_inhalt_laesst_content_weg():
    """Eine Assistenten-Nachricht, die nur Werkzeuge aufruft, hat keinen Text — Ollama
    lehnt `content: null` in dieser Form ab."""
    req = ChatCompletionRequest(
        model="qwen3.8:latest",
        messages=[{"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "write_file", "arguments": "{}"}}]}],
    )
    payload = _bau_ollama_payload("qwen3.8:latest", req)
    assert "content" not in payload["messages"][0]
    assert payload["messages"][0]["tool_calls"][0]["id"] == "c1"


def test_antwort_behaelt_werkzeugaufrufe():
    ollama_resp = {
        "model": "qwen3.8:latest",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "write_file", "arguments": "{\"path\":\"x\"}"}}],
        },
        "done_reason": "stop",
        "prompt_eval_count": 120,
        "eval_count": 40,
    }
    out = _ollama_to_openai_shape(ollama_resp, "qwen3.8:latest")
    wahl = out["choices"][0]
    assert wahl["message"]["tool_calls"][0]["function"]["name"] == "write_file"
    assert wahl["finish_reason"] == "tool_calls", "das Modell meldet einen Aufruf, nicht 'stop'"
    assert out["usage"]["total_tokens"] == 160


def test_antwort_ohne_aufruf_meldet_stop():
    out = _ollama_to_openai_shape(
        {"message": {"role": "assistant", "content": "hallo"}, "done_reason": "stop"}, "m")
    assert out["choices"][0]["finish_reason"] == "stop"
    assert out["choices"][0]["message"]["tool_calls"] is None
