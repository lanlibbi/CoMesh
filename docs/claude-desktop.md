# Claude Desktop mit dem CoMesh-Pool / Claude Desktop with the CoMesh pool

Colleagues who already work in Claude Desktop can use the pool's models **without installing
anything else**: Claude Desktop can talk to a self-hosted gateway, and CoMesh now speaks the
required API.

## What Claude Desktop expects

From Anthropic's docs ("Deploy Claude Desktop on 3P with an LLM gateway"):

- `inferenceProvider = gateway` — a self-hosted gateway as the inference provider.
- The gateway **must implement the Anthropic Messages API**: `POST /v1/messages` with streaming
  and tool use.
- `GET /v1/models` is **optional** — if implemented, Claude Desktop discovers the available models
  by itself. That is the part that makes the pool's local models appear in the model picker.

## What CoMesh provides

| Endpoint | Purpose |
|---|---|
| `POST /v1/messages` | Anthropic Messages API (`stream`, `tools`, `system`, `max_tokens`) |
| `GET /v1/models` | Model list. Answer depends on the client: `x-api-key` → Anthropic shape, `Authorization: Bearer` → unchanged OpenAI shape |

Authentication accepts **either** `x-api-key: gpu_…` (what Claude Desktop sends) or
`Authorization: Bearer gpu_…` (existing clients). Requests are routed, whitelisted, billed and
logged through the same code path as `/v1/chat/completions` — no second implementation.

Not translated (on purpose): prompt caching. The pool does not cache across requests, and
`cache_read_input_tokens` is reported as `0` rather than a made-up hit count.

## Setup on a user's machine

1. In Claude Desktop: **Help → Troubleshooting → Enable Developer Mode**.
2. **Developer → Configure Third-Party Inference…**
3. Connection:
   - Inference provider: **Gateway**
   - Credential kind: **API key**
   - Gateway base URL: the address of your portal, **without** `/api` and without trailing slash,
     e.g. `https://comesh.example.org` or `http://192.168.1.38:8767`
   - Gateway API key: the user's own `gpu_…` key (Profile → Keys → Create key)
4. Restart Claude Desktop. The pool's models appear in the model picker.

For a fleet, the same values go into a managed configuration (MDM profile, `.reg` on Windows, or
the Enterprise Admin Console) — see Anthropic's configuration reference for
`inferenceGatewayBaseUrl`, `inferenceGatewayApiKey` and `inferenceModels`.

## Verification (no GPU needed)

`tests/testkit/stub_ollama.py` is a stand-in for Ollama. `tests/test_anthropic_kompat.py` checks the
translation in both directions; `anthropic_api.py` additionally carries an end-to-end run against
the stub:

- model list in both shapes,
- non-streaming answer with `content[]`, `stop_reason`, `usage.input_tokens`/`output_tokens`,
- streaming event order `message_start → content_block_delta* → message_stop`,
- tool use: `tools` (Anthropic) → `tool_calls` (OpenAI) → `tool_use` block with `input` object,
- error cases: missing `max_tokens` → 422, wrong key → 401, no credentials → 401.

---

# Claude Desktop mit dem CoMesh-Pool

Wer ohnehin in Claude Desktop arbeitet, kann die Modelle des Pools nutzen, **ohne etwas zu
installieren**: Claude Desktop kann einen eigenen Gateway als Inferenz-Anbieter verwenden, und
CoMesh spricht die dafür nötige Schnittstelle.

## Was Claude Desktop erwartet

Aus Anthropics Doku („Deploy Claude Desktop on 3P with an LLM gateway"):

- `inferenceProvider = gateway` — ein selbst betriebener Gateway als Anbieter.
- Der Gateway **muss die Anthropic Messages API können**: `POST /v1/messages` mit Streaming und
  Werkzeugaufrufen.
- `GET /v1/models` ist **optional** — ist es vorhanden, findet Claude Desktop die Modelle selbst.
  Genau darüber erscheinen die lokalen Modelle in der Modellauswahl.

## Was CoMesh bereitstellt

| Endpunkt | Zweck |
|---|---|
| `POST /v1/messages` | Anthropic Messages API (`stream`, `tools`, `system`, `max_tokens`) |
| `GET /v1/models` | Modellliste. Die Form hängt am Client: mit `x-api-key` die Anthropic-Form, mit `Authorization: Bearer` unverändert die OpenAI-Form |

Der Zugang akzeptiert **beides**: `x-api-key: gpu_…` (so sendet es Claude Desktop) und
`Authorization: Bearer gpu_…` (bestehende Clients). Routing, Freigaben, Abrechnung und Protokoll
laufen über denselben Weg wie `/v1/chat/completions` — keine zweite Implementierung.

Bewusst nicht übersetzt: Prompt-Caching. Der Pool cached nicht über Anfragen hinweg, und
`cache_read_input_tokens` wird ehrlich mit `0` gemeldet statt mit erfundenen Trefferzahlen.

## Einrichtung auf dem Rechner eines Nutzers

1. In Claude Desktop: **Help → Troubleshooting → Enable Developer Mode**.
2. **Developer → Configure Third-Party Inference…**
3. Verbindung:
   - Inference provider: **Gateway**
   - Credential kind: **API key**
   - Gateway base URL: die Adresse des Portals, **ohne** `/api` und ohne Schrägstrich am Ende,
     z. B. `https://comesh.example.org` oder `http://192.168.1.38:8767`
   - Gateway API key: der eigene `gpu_…`-Schlüssel (Profil → Schlüssel → Schlüssel erzeugen)
4. Claude Desktop neu starten. Die Modelle des Pools stehen in der Auswahl.

Für viele Rechner gehen dieselben Werte in eine verwaltete Konfiguration (MDM-Profil, `.reg` unter
Windows oder die Enterprise-Admin-Konsole) — Schlüssel dafür sind `inferenceGatewayBaseUrl`,
`inferenceGatewayApiKey` und `inferenceModels`.

## Nachweis (ohne GPU)

`tests/testkit/stub_ollama.py` ersetzt Ollama. `tests/test_anthropic_kompat.py` prüft die
Übersetzung in beide Richtungen; der Ende-zu-Ende-Lauf im Modulkopf von `anthropic_api.py` deckt ab:

- Modellliste in beiden Formen,
- Antwort ohne Streaming mit `content[]`, `stop_reason`, `usage.input_tokens`/`output_tokens`,
- Reihenfolge im Streaming `message_start → content_block_delta* → message_stop`,
- Werkzeuge: `tools` (Anthropic) → `tool_calls` (OpenAI) → `tool_use`-Block mit `input`-Objekt,
- Fehlerfälle: fehlendes `max_tokens` → 422, falscher Schlüssel → 401, ohne Zugangsdaten → 401.

## Model names for Claude (Code and Desktop)

Claude Code and Claude Desktop only accept **Claude-style model names** from a gateway's
`GET /v1/models`. A catalogue that lists only local Ollama names (`qwen3-vl:8b`, `gemma4:12b`)
produces "Gateway returned no usable models" — the endpoint works, the names are rejected.

CoMesh therefore advertises three aliases next to the real models:

| Alias | Served by |
|---|---|
| `claude-sonnet-4-5` | `ANTHROPIC_ALIAS_TARGET`, else `DEFAULT_MODEL`, else the first available model |
| `claude-opus-4-1` | same |
| `claude-haiku-4-5` | same |

`POST /v1/messages` maps an alias to that target before routing, so Claude works without further
configuration. Each alias entry carries `comesh_target` so you can see what it resolves to.
Set `ANTHROPIC_ALIAS_TARGET` to pin it to one model, for example `qwen3-vl:8b`.

Base URL for Claude: the portal address **without** `/v1` — Claude appends `/v1/messages` and
`/v1/models` itself. OpenAI-compatible clients use the address **with** `/v1`.

---

## Modellnamen fuer Claude (Code und Desktop)

Claude Code und Claude Desktop akzeptieren von einem Gateway nur **Modellnamen im Claude-Stil**.
Eine Liste, die ausschliesslich lokale Ollama-Namen fuehrt, ergibt "Gateway returned no usable
models" — die Route arbeitet, die Namen werden abgelehnt.

Deshalb bietet CoMesh drei Aliase neben den echten Modellen an (`claude-sonnet-4-5`,
`claude-opus-4-1`, `claude-haiku-4-5`). Sie zeigen auf `ANTHROPIC_ALIAS_TARGET`, sonst auf
`DEFAULT_MODEL`, sonst auf das erste verfuegbare Modell; `POST /v1/messages` loest den Namen vor
dem Routing auf. Basisadresse fuer Claude: die Portal-Adresse **ohne** `/v1`.

### One entry per model (since 0.6.38)

Next to the three fixed aliases, **every** model gets its own Claude-compatible identifier:
`claude-custom-<base64url(model name)>`. The encoding is reversible, so a request with that id is
mapped back to the exact model — no table, no catalogue lookup, and a model installed later works
immediately without touching any configuration. Each entry carries the real name as `display_name`
and `comesh_target`, so the picker shows what actually answers.

### Ein Eintrag je Modell (ab 0.6.38)

Neben den drei festen Aliasen bekommt **jedes** Modell eine eigene Claude-taugliche Kennung
`claude-custom-<base64url(Modellname)>`. Die Kodierung ist umkehrbar, ein Aufruf mit dieser Kennung
landet also exakt beim richtigen Modell — ohne Tabelle und ohne Katalogabruf. Ein spaeter
installiertes Modell funktioniert sofort, ohne dass etwas nachgetragen wird. Der echte Name steht
als `display_name` und `comesh_target` daneben.
