# Tailscale-Setup

Der gesamte GPU-Pool läuft ausschließlich über ein privates Tailscale-Netzwerk. Das bedeutet:

- **Keine Public-IPs** für Portal oder Node-Agents
- **Keine Firewall-Regeln** nötig
- **WireGuard-Verschlüsselung** out-of-the-box
- **MagicDNS** für Hostnamen statt IPs

> Diese Lösung ersetzt frühere Setups wie Twingate oder direkte Port-Forwardings.

## Architektur im Tailscale-Netz

```
Tailscale-Coordinator (controlplane.tailscale.com)
       │
       │ Schlüsselaustausch, ACLs
       │
       ├─── portal-host (portal-ip)     [Portal]
       ├─── node-host (node-ip)           [Node-Agent]
       ├─── gaming-pc (100.x.x.x)            [Node-Agent]
       ├─── workstation (100.x.x.x)          [Node-Agent]
       └─── laptop (100.x.x.x)               [Node-Agent]
       
Alle Hosts sehen sich direkt im 100.64.0.0/10-Range (CGNAT).
WireGuard-Tunnel zwischen jedem Paar.
```

## Setup-Schritte

### 1. Tailscale-Account

1. Account auf [tailscale.com](https://tailscale.com) erstellen
2. Im Admin-Panel: **Access Controls** → MagicDNS aktivieren

### 2. Portal-Host (`portal-host`)

```bash
# Installieren
curl -fsSL https://tailscale.com/install.sh | sh

# Starten + Account zuordnen
sudo tailscale up

# MagicDNS-Hostname setzen
sudo tailscale set --hostname=portal-host

# Status prüfen
tailscale ip -4
# portal-ip
tailscale status
```

### 3. Node-Agent-Hosts

Auf jedem Contributor-Host gleich:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale set --hostname=node-host  # eindeutig pro Host!
```

> **Wichtig:** Jeder Host braucht einen eindeutigen MagicDNS-Namen. Sonst gibt's Konflikte.

### 4. ACLs (optional für POC, Pflicht für Prod)

In Tailscale Admin → Access Controls:

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["tag:portal"],
      "dst": ["tag:node:8080"]
    },
    {
      "action": "accept",
      "src": ["tag:node"],
      "dst": ["tag:portal:8765"]
    },
    {
      "action": "accept",
      "src": ["group:admins"],
      "dst": ["*:*"]
    }
  ],
  "tagOwners": {
    "tag:portal": ["group:admins"],
    "tag:node": ["group:admins"]
  }
}
```

Tags setzen:
```bash
# Portal
sudo tailscale set --advertise-tags=tag:portal

# Node-Agents
sudo tailscale set --advertise-tags=tag:node
```

Tags müssen im Admin-Panel **approviert** werden, bevor sie wirken.

## Verifizierung

### Alle Hosts im Netz

```bash
tailscale status
# portal-ip   portal-host      admin@   linux   active; direct 100.0.0.1, tx 15820 rx 9456
# node-ip   node-host            admin@   linux   active; direct 100.0.0.2, tx 9456 rx 7892
# 100.x.x.x        gaming-pc        admin@   linux   active; relayed via fra
```

### Ping zwischen Hosts

```bash
# Auf portal-host:
tailscale ping node-host
# pong from node-host (node-ip) via direct in 12ms
```

### MagicDNS testen

```bash
# Auf jedem Host:
ping portal-host
ping node-host
# Sollte via 100.x.x.x auflösen
```

## Firewall-Hinweise

Tailscale braucht **ausgehende** Verbindungen:
- UDP 41641 (WireGuard) — direkter Pfad
- TCP 443 (Fallback über DERP-Relay)

Eingehend: **nichts**. Das ist der Witz daran.

Falls dein Netzwerk restriktiv ist (z. B. öffentliches WLAN):
- UDP 41641 sollte offen sein
- TCP 443 als Fallback reicht für relayed traffic (langsamer, aber funktional)

## Häufige Probleme

### Host ist "offline" obwohl er online ist

- NAT-Traversal scheitert → wird relayed
- Tailscale-Service läuft? `sudo systemctl status tailscaled`
- MagicDNS: `tailscale status` zeigt alle Hosts?

### Verbindungen extrem langsam

- Wahrscheinlich über DERP-Relay statt direkt
- Beide Hosts hinter strict NAT? → DERP ist normal
- Im Status-Output: "via direct" = gut, "relayed" = langsamer

### Node-Agent kann Portal nicht erreichen

```bash
# Vom Node-Agent-Host:
curl http://portal-host:8765/health
# Falls Timeout:
tailscale status  # Portal online?
ping portal-host
```

### Portal sieht Node nicht

- Firewall auf Node-Agent? Sollte nichts nötig sein, Tailscale ist eingehend offen
- Agent-Logs: `docker compose logs agent` → "Registering with portal" + Fehler?

## Sicherheit (POC vs. Prod)

| Aspekt | POC (jetzt) | Prod (TODO) |
|---|---|---|
| Netz-Zugriff | Tailscale-Account | + ACLs (Tags) |
| API-Auth | keine | API-Keys + mTLS |
| Portal-Auth | keine | OAuth / Basic-Auth |
| Heartbeat-Signatur | keine | HMAC mit Node-spezifischem Secret |
| MagicDNS | öffentlich im Tailnet | private + internes DNS |

## Backup-Strategie

Tailscale speichert die Topologie in der Cloud. Bei Komplett-Verlust:
1. Neuen Host mit Tailscale hochfahren
2. `sudo tailscale up` mit demselben Account
3. MagicDNS-Name wird automatisch wieder aktiv
4. Node-Agent liest seine Tailscale-IP per `tailscale ip -4` und registriert sich neu

**Wichtig:** Tailscale-Auth-Key sicher aufbewahren. Bei Verlust → alle Hosts manuell re-authentifizieren.
