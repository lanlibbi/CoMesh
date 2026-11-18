"""pytest-Tests für die Anthropic-Übersetzung (reine Funktionen, keine GPU, kein Netz).

Der Ende-zu-Ende-Lauf gegen das Ollama-Testdoppel steckt in `tests/testkit/` und wurde separat
ausgeführt; hier stehen die Prüfungen, die ohne laufende API auskommen und deshalb in jedem Gate
mitlaufen können.
"""

import importlib.util
import json
import pathlib

BASIS = pathlib.Path(__file__).resolve().parent.parent
MODUL = BASIS / "anthropic_api.py"


def _lade():
    spec = importlib.util.spec_from_file_location("anthropic_api_test", MODUL)
    modul = importlib.util.module_from_spec(spec)
    # FastAPI/SQLAlchemy sind zum Prüfen der reinen Funktionen nicht nötig, werden aber beim
    # Import des Moduls verlangt - im API-Abbild vorhanden, lokal meist auch.
    spec.loader.exec_module(modul)
    return modul


def test_system_und_textbloecke_werden_zu_nachrichten():
    a = _lade()
    offen = a.to_openai_request({
        "system": [{"type": "text", "text": "Antworte knapp."}],
        "messages": [{"role": "user", "content": [{"type": "text", "text": "Hallo"}]}],
        "max_tokens": 50,
    })
    assert offen["messages"][0] == {"role": "system", "content": "Antworte knapp."}
    assert offen["messages"][1] == {"role": "user", "content": "Hallo"}
    assert offen["max_tokens"] == 50
    assert offen["stream"] is False


def test_werkzeuge_werden_uebersetzt():
    a = _lade()
    offen = a.to_openai_request({
        "messages": [{"role": "user", "content": "Wie spät?"}],
        "max_tokens": 10,
        "tools": [{"name": "uhrzeit", "description": "Uhrzeit",
                   "input_schema": {"type": "object", "properties": {"zone": {"type": "string"}}}}],
        "tool_choice": {"type": "any"},
    })
    werkzeug = offen["tools"][0]
    assert werkzeug["type"] == "function"
    assert werkzeug["function"]["name"] == "uhrzeit"
    assert werkzeug["function"]["parameters"]["properties"]["zone"]["type"] == "string"
    assert offen["tool_choice"] == "required"


def test_tool_use_und_tool_result_werden_zu_rollen():
    a = _lade()
    offen = a.to_openai_request({
        "max_tokens": 10,
        "messages": [
            {"role": "assistant", "content": [
                {"type": "text", "text": "Ich schaue nach."},
                {"type": "tool_use", "id": "toolu_1", "name": "uhrzeit", "input": {"zone": "UTC"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": [{"type": "text", "text": "12:00"}]},
            ]},
        ],
    })
    assistent = offen["messages"][0]
    assert assistent["role"] == "assistant"
    assert assistent["tool_calls"][0]["id"] == "toolu_1"
    assert json.loads(assistent["tool_calls"][0]["function"]["arguments"]) == {"zone": "UTC"}
    werkzeug_antwort = offen["messages"][1]
    assert werkzeug_antwort["role"] == "tool"
    assert werkzeug_antwort["tool_call_id"] == "toolu_1"
    assert werkzeug_antwort["content"] == "12:00"


def test_antwort_wird_zur_anthropic_message():
    a = _lade()
    m = a.to_anthropic_response({
        "model": "testmodell:7b",
        "choices": [{"message": {"role": "assistant", "content": "Servus"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }, "testmodell:7b")
    assert m["type"] == "message" and m["role"] == "assistant"
    assert m["content"] == [{"type": "text", "text": "Servus"}]
    assert m["stop_reason"] == "end_turn"
    assert m["usage"]["input_tokens"] == 11 and m["usage"]["output_tokens"] == 7
    # Kein erfundenes Cache-Ergebnis
    assert m["usage"]["cache_read_input_tokens"] == 0


def test_werkzeugantwort_wird_zum_tool_use_block():
    a = _lade()
    m = a.to_anthropic_response({
        "choices": [{
            "message": {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_1", "function": {"name": "uhrzeit", "arguments": "{\"zone\": \"UTC\"}"}},
            ]},
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    }, "testmodell:7b")
    block = m["content"][0]
    assert block["type"] == "tool_use"
    assert block["name"] == "uhrzeit"
    assert block["input"] == {"zone": "UTC"}
    assert m["stop_reason"] == "tool_use"


def test_modellliste_in_anthropic_form():
    a = _lade()
    d = a.models_antwort_anthropic([{"id": "testmodell:7b", "created": 0}])
    assert d["data"][0]["id"] == "testmodell:7b"
    assert d["data"][0]["display_name"] == "testmodell:7b"
    assert d["has_more"] is False
