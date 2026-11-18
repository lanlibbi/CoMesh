# Security notes

What CoMesh does about the findings of the external review, what it deliberately does not do,
and what an operator has to decide.

## Node authentication (0.6.28)

The portal no longer sends the global `NODE_SHARED_SECRET` to node addresses. Requests to a node
carry a **per-node token**:

```
token = HMAC-SHA256( node.api_key_hash , "comesh-portal-v1" )
```

The agent computes the same value from its own node key (`NODE_API_KEY`, env or state file), so
nothing has to be distributed. A token is worthless for any other node — which is the point:
`node_url` is a free field at registration, and the previous shared secret opened *every* agent
in the pool at once.

The agent's gate now closes as soon as a node key exists, even without `NODE_SHARED_SECRET`.
Only an agent with neither (never registered) still answers openly, and says so at startup.

| Situation | Agent behaviour |
|---|---|
| node key present | requires the derived token |
| no node key, `NODE_SHARED_SECRET` set | requires the derived token |
| neither | open (warns at startup) — the old state |

Transitional flags, both defaulting to off:

- `ALLOW_LEGACY_NODE_SECRET=1` (portal) — sends the global secret again, logs a warning. Only
  while agents older than 0.6.28 are still serving.
- `NODE_ALLOW_LEGACY_SHARED_SECRET=1` (agent) — accepts the global secret again.

## Node addresses

`node_url` accepts `http` and `https` only. Loopback (`127.0.0.0/8`, `::1`), link-local
(`169.254.0.0/16`, including `169.254.169.254`), `0.0.0.0` and multicast are rejected, at
registration (HTTP 422) and again immediately before every request, with DNS resolution — a
record flipped after registration must not get through.

Private LAN ranges (`10/8`, `172.16/12`, `192.168/16`) stay allowed. CoMesh exists so that nodes
inside a LAN can be used; blocking them would break the product.

`ALLOW_RESTRICTED_NODE_URLS=1` is the escape hatch when somebody really runs an agent on
`127.0.0.1`.

## WebSocket chat

`/ws/chat` uses `auth.resolve_token()` — the same function as the HTTP path — so token expiry
and the registration status apply identically, and `limit_chat()` runs per message. The
`?api_key=` query fallback is gone; both frontends already send the key as the
`api-key.<key>` subprotocol.

## Known, accepted

- **The node key still travels in a query string** for the agent WebSocket
  (`/agent/connect?node_key=…`). The agent talks to the portal directly, so no proxy sees it in
  the reference setup — but behind a reverse proxy it lands in the access log. Moving it to a
  subprotocol is a follow-up that touches both sides at once.
- **The public catalogue is public** (`/nodes/list`) — that is intended.
- **`/net/echo` stays reachable without a token** for setup checks; it no longer reveals the
  portal's hostname, FQDN or outbound IP to anonymous callers.

## Operator checklist after upgrading

1. `git pull`, then `scripts/deploy.sh` (portal) and re-copy the agent sources on every node
   (`install-from-source.ps1 -KeyOnly` does that).
2. Revoke the key that was published in `POC-REPORT.md` — Profile → keys → delete.
3. Set `COMESH_PUBLIC_BASE_URL` if the portal is reached under a name other than `localhost`.
4. Do **not** set `PROMOTE_ADMIN_EMAIL` on any instance that is reachable from outside.

---

# Sicherheitshinweise (deutsch)

Die Kurzfassung zu den Änderungen steht im `CHANGELOG.md` unter 0.6.28. Drei Punkte, die für den
Betrieb zählen:

1. **Das globale Node-Geheimnis geht nicht mehr über die Leitung.** Jede Anfrage an einen Agenten
   trägt ein aus dem Node-Schlüssel abgeleitetes Token. Ein Angreifer, der eine Node mit eigener
   Adresse registriert, bekommt nur sein eigenes Token — vorher bekam er das Geheimnis *aller*
   Agenten und damit kostenlosen Zugriff auf fremde GPUs.
2. **Node-Adressen werden geprüft.** Nur `http`/`https`, kein Loopback, kein Link-Local. LAN-Adressen
   wie `192.168.1.50` bleiben erlaubt — sonst wäre das Produkt kaputt.
3. **Der Agent ist ohne Secret nicht mehr offen.** Sobald ein Node-Schlüssel existiert, verlangt er
   das abgeleitete Token. Vorher ließ er ohne `NODE_SHARED_SECRET` alles durch und warnte nur.

Nach dem Update: Agent-Quellen auf jeder Node neu kopieren (`install-from-source.ps1 -KeyOnly`),
sonst antworten alte Agenten mit 401. Wer übergangsweise nicht updaten kann, setzt auf beiden
Seiten die Legacy-Schalter (`ALLOW_LEGACY_NODE_SECRET=1` im Portal,
`NODE_ALLOW_LEGACY_SHARED_SECRET=1` im Agenten) — und macht das so kurz wie möglich.
