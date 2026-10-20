# CoMesh — Anleitung für Einsteiger

Diese Seite erklärt CoMesh für Menschen, die es nicht kennen. Die kurze Fassung liegt als
`frontend-alpine/hilfe.html` im Portal und ist dort ohne Anmeldung erreichbar (Menü „Anleitung").

## Was CoMesh ist

Ein gemeinschaftlicher Zugang zu Rechenleistung für KI-Modelle. Wer einen Rechner mit freier
Grafikkarte hat, stellt sie dem Pool zur Verfügung. Wer Modelle nutzen will, holt sie über eine
einzige Schnittstelle, die genauso aussieht wie die von OpenAI — ohne eigene Hardware und ohne Abo.

Zwei Rollen, kombinierbar:

* **Nutzer** — braucht nichts zu installieren. Ein OpenAI-kompatibler Client und ein Schlüssel
  genügen: die Weboberfläche, LM Studio, oder ein eigenes Skript.
* **Anbieter** — betreibt den Node-Agenten als Container. Er meldet die GPU an den Pool und nimmt
  Aufträge an. Welche Modelle der Rechner anbietet, legt der Betreiber fest.

## Erste Schritte

1. **Konto anlegen** auf `/register.html`. Danach ist das Konto angemeldet, aber nicht freigegeben.
2. **Freigabe abwarten** — ein Administrator schaltet es frei. Erst dann sind Modelle erreichbar.
3. **Schlüssel holen** im Profil. Er wird **einmal** angezeigt; ein neuer Schlüssel macht den alten
   ungültig.
4. **Ersten Aufruf machen** gegen `<portal>:8765/v1`.
5. **Verbrauch ansehen** unter „Mein Verbrauch".

## Erster Aufruf

```bash
curl -s http://PORTAL:8765/v1/chat/completions \
  -H "Authorization: Bearer DEIN-SCHLUESSEL" \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2", "messages": [{"role": "user", "content": "Sag kurz hallo"}]}'
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://PORTAL:8765/v1", api_key="DEIN-SCHLUESSEL")
antwort = client.chat.completions.create(
    model="llama3.2",
    messages=[{"role": "user", "content": "Sag kurz hallo"}],
    stream=True,
)
for stueck in antwort:
    print(stueck.choices[0].delta.content or "", end="", flush=True)
```

**Streaming einschalten.** Ohne `stream=True` kann eine lange Antwort an Zwischenschichten hängen
bleiben (524). Mit Streaming kommen die Wörter, während sie entstehen.

Welche Modelle gerade verfügbar sind: `GET /v1/models` mit demselben Schlüssel. Ein Modell kann
zusätzlich pro Konto freigegeben werden müssen.

## Credits

Kein Geld. Der Verbrauch wird in Credits gemessen, die jedem Konto zugeteilt werden. Wer eine GPU
beisteuert, bekommt Credits gutgeschrieben — so trägt sich der Pool selbst. Sind die Credits
aufgebraucht, antwortet der Dienst mit einer Fehlermeldung statt still weiterzurechnen.

## Fehlercodes

| Code | Bedeutung | Was tun |
| --- | --- | --- |
| 401 | Schlüssel fehlt oder ungültig | vollständig kopiert? Neuer Schlüssel macht den alten ungültig |
| 403 | Modell nicht freigegeben oder Konto nicht freigeschaltet | Administrator fragen |
| 429 | zu schnell hintereinander | kurz warten, Grenze gilt je Adresse |
| 502 | kein Rechner bietet das Modell gerade an | später erneut versuchen |
| 524 | Zeitüberschreitung | `stream=True` benutzen |

## Grenzen, die man kennen muss

* **Eingaben laufen über einen fremden Rechner.** Wer die GPU beisteuert, kann technisch sehen, was
  durchläuft. Keine Passwörter, keine Personalakten, keine vertraulichen Verträge.
* **Keine Verfügbarkeitsgarantie.** Der Pool besteht aus privaten Rechnern; fällt einer aus, gibt es
  einen Fehler, keine späte Antwort.
* **Modelle bleiben kontrollierbar** — pro Rechner und pro Konto als Liste.
