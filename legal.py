"""Rechtstexte aus der Umgebung: Impressum, Datenschutz, Nutzungsbedingungen.

Diese drei Seiten sind für ein öffentlich erreichbares Angebot Pflicht (§ 5 DDG,
Art. 13 DSGVO). Sie stehen bewusst **nicht** als fertige Datei im Image: die
Angaben des Betreibers gehören in die Umgebung, nicht in den Quelltext — und
fehlende Angaben müssen sichtbar sein, statt still ein unvollständiges Impressum
auszuliefern.

Fehlt eine Pflichtangabe, erscheint oben ein roter Hinweis mit genau der Liste
der fehlenden Variablen. Sobald sie gesetzt sind, verschwindet der Hinweis.
"""
import html
import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/legal", tags=["legal"])

PFLICHT = {
    "IMPRESSUM_FIRMA": "Firma oder Name",
    "IMPRESSUM_STRASSE": "Straße und Hausnummer",
    "IMPRESSUM_PLZ_ORT": "Postleitzahl und Ort",
    "IMPRESSUM_EMAIL": "E-Mail-Adresse",
    "DATENSCHUTZ_EMAIL": "E-Mail-Adresse für Datenschutzanfragen",
}


def _wert(name: str, standard: str = "") -> str:
    return (os.environ.get(name) or standard).strip()


def _fehlend() -> list:
    return [f"{k} ({v})" for k, v in PFLICHT.items() if not _wert(k)]


def _seite(titel: str, inhalt: str) -> HTMLResponse:
    fehlt = _fehlend()
    banner = ""
    if fehlt:
        banner = (
            "<div class=\"warnung\"><b>Diese Seite ist noch nicht vollständig.</b> "
            "Vor dem Betrieb müssen folgende Angaben gesetzt werden: "
            + html.escape("; ".join(fehlt)) + "</div>"
        )
    doc = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{html.escape(titel)} · CoMesh</title>
<style>
  :root {{ color-scheme: dark light; }}
  body {{ margin:0; padding:48px 20px; background:#0e1116; color:#e6e9ef;
         font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif; }}
  main {{ max-width:760px; margin:0 auto; }}
  h1 {{ font-size:28px; margin:0 0 8px; }}
  h2 {{ font-size:19px; margin:32px 0 6px; }}
  a {{ color:#7fb2ff; }}
  .zurueck {{ display:inline-block; margin-bottom:28px; color:#9aa4b2; text-decoration:none; }}
  .warnung {{ background:#3a1114; border:1px solid #a33; padding:14px 16px; border-radius:10px;
             margin-bottom:28px; color:#ffd9d9; }}
  p, li {{ color:#c8cdd6; }}
  code {{ background:#1a1f27; padding:1px 5px; border-radius:4px; }}
  .stand {{ margin-top:40px; color:#7b8494; font-size:14px; }}
</style>
</head>
<body><main>
<a class="zurueck" href="/index.html">← CoMesh</a>
{banner}
{inhalt}
</main></body></html>"""
    return HTMLResponse(doc, headers={"X-Robots-Tag": "index, follow"} if not fehlt else {"X-Robots-Tag": "noindex"})


@router.get("/impressum", response_class=HTMLResponse)
def impressum() -> HTMLResponse:
    firma = _wert("IMPRESSUM_FIRMA")
    zeilen = [
        firma,
        _wert("IMPRESSUM_STRASSE"),
        _wert("IMPRESSUM_PLZ_ORT"),
        _wert("IMPRESSUM_LAND", "Deutschland"),
    ]
    kontakt = []
    if _wert("IMPRESSUM_TELEFON"):
        kontakt.append("Telefon: " + _wert("IMPRESSUM_TELEFON"))
    if _wert("IMPRESSUM_EMAIL"):
        kontakt.append('E-Mail: <a href="mailto:{0}">{0}</a>'.format(html.escape(_wert("IMPRESSUM_EMAIL"))))
    register = []
    if _wert("IMPRESSUM_VERTRETEN"):
        register.append("Vertreten durch: " + html.escape(_wert("IMPRESSUM_VERTRETEN")))
    if _wert("IMPRESSUM_REGISTER"):
        register.append("Registereintrag: " + html.escape(_wert("IMPRESSUM_REGISTER")))
    if _wert("IMPRESSUM_USTID"):
        register.append("Umsatzsteuer-Identifikationsnummer: " + html.escape(_wert("IMPRESSUM_USTID")))

    inhalt = (
        "<h1>Impressum</h1>"
        "<h2>Angaben gemäß § 5 DDG</h2><p>"
        + "<br />".join(html.escape(z) for z in zeilen if z)
        + "</p>"
        + ("<h2>Kontakt</h2><p>" + "<br />".join(kontakt) + "</p>" if kontakt else "")
        + ("<h2>Weitere Angaben</h2><p>" + "<br />".join(register) + "</p>" if register else "")
        + "<h2>Verantwortlich für den Inhalt</h2><p>"
        + html.escape(_wert("IMPRESSUM_VERTRETEN") or firma or "siehe oben")
        + "</p>"
        "<h2>Streitbeilegung</h2><p>Wir sind nicht verpflichtet und nicht bereit, an "
        "Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle teilzunehmen.</p>"
    )
    return _seite("Impressum", inhalt)


@router.get("/datenschutz", response_class=HTMLResponse)
def datenschutz() -> HTMLResponse:
    mail = html.escape(_wert("DATENSCHUTZ_EMAIL") or _wert("IMPRESSUM_EMAIL"))
    hosting = html.escape(_wert("HOSTING_ANBIETER") or "den Betreiber dieser Instanz")
    inhalt = f"""
<h1>Datenschutzerklärung</h1>
<p>Diese Instanz betreibt eine Vermittlungsplattform für KI-Modelle. Nachfolgend steht, welche
Daten dabei verarbeitet werden, zu welchem Zweck und wie lange.</p>

<h2>1. Verantwortlicher</h2>
<p>{html.escape(_wert("IMPRESSUM_FIRMA"))}, {html.escape(_wert("IMPRESSUM_STRASSE"))},
{html.escape(_wert("IMPRESSUM_PLZ_ORT"))} — Kontakt: <a href="mailto:{mail}">{mail}</a></p>

<h2>2. Welche Daten verarbeitet werden</h2>
<ul>
  <li><b>Konto:</b> E-Mail-Adresse, Name, Passwort-Hash (PBKDF2-SHA256), Rolle, Guthaben, Zeitpunkt
      der Registrierung. Rechtsgrundlage: Vertragserfüllung (Art. 6 Abs. 1 lit. b DSGVO).</li>
  <li><b>Nutzung:</b> welche Modelle mit welcher Tokenzahl aufgerufen wurden, Zeitpunkt, Statuscode.
      Das ist die Abrechnungsgrundlage und zugleich die Mißbrauchserkennung
      (Art. 6 Abs. 1 lit. b und f DSGVO).</li>
  <li><b>Anfrageinhalte:</b> Prompts und Antworten werden zur Beantwortung an den Rechner
      weitergegeben, der das Modell betreibt. Eine dauerhafte Speicherung der Inhalte findet
      nicht statt; gespeichert werden Metadaten (Länge, Modell, Zeitpunkt).</li>
  <li><b>Technisch:</b> IP-Adresse im Zugriffsprotokoll und für die Anmeldesperre nach
      Fehlversuchen (Art. 6 Abs. 1 lit. f DSGVO).</li>
  <li><b>Zahlungen</b> (falls aktiviert): Abwicklung über den jeweiligen Zahlungsdienstleister;
      dort gelten dessen Bedingungen. Bei uns werden nur Zahlungsstatus und Betrag gespeichert.</li>
</ul>

<h2>3. Betrieb und Auftragsverarbeitung</h2>
<p>Die Instanz läuft auf Infrastruktur von {hosting}. Zugriffe können über ein Content Delivery
Network (Cloudflare) geleitet werden; dabei wird die IP-Adresse an den Anbieter übertragen. Soweit
dabei personenbezogene Daten verarbeitet werden, geschieht das auf Grundlage eines
Auftragsverarbeitungsvertrags.</p>

<h2>4. Speicherdauer</h2>
<p>Kontodaten bis zur Löschung des Kontos. Nutzungsdaten zur Abrechnung bis zum Ende der
Aufbewahrungsfristen. Zugriffsprotokolle werden regelmäßig verdrängt.</p>

<h2>5. Betroffenenrechte</h2>
<p>Auskunft, Berichtigung, Löschung, Einschränkung, Datenübertragbarkeit und Widerspruch. Eine
Anfrage genügt an <a href="mailto:{mail}">{mail}</a>. Außerdem steht ein Beschwerderecht bei einer
Datenschutz-Aufsichtsbehörde zu.</p>

<h2>6. Keine automatisierte Entscheidungsfindung</h2>
<p>Es findet keine automatisierte Entscheidungsfindung mit rechtlicher Wirkung statt.</p>
"""
    return _seite("Datenschutz", inhalt)


@router.get("/agb", response_class=HTMLResponse)
def agb() -> HTMLResponse:
    inhalt = """
<h1>Nutzungsbedingungen</h1>
<p>Diese Bedingungen gelten für die Nutzung dieser Instanz. Mit der Registrierung werden sie
anerkannt.</p>

<h2>1. Leistung</h2>
<p>Die Plattform vermittelt Anfragen an KI-Modelle, die auf Rechnern Dritter (Provider) betrieben
werden. Ein Anspruch auf ständige Verfügbarkeit, auf ein bestimmtes Modell oder auf eine bestimmte
Antwortqualität besteht nicht.</p>

<h2>2. Konto</h2>
<p>Zugangsdaten sind geheim zu halten. Die Weitergabe des Kontos oder eines API-Schlüssels an
Dritte ist nicht gestattet; für alle Aktivitäten unter einem Konto haftet die Person, die es
eingerichtet hat.</p>

<h2>3. Zulässige Nutzung</h2>
<p>Untersagt sind rechtswidrige Inhalte, Angriffe auf die Infrastruktur, das Ausspähen fremder
Daten sowie die Nutzung zur Erstellung von Inhalten, die Rechte Dritter verletzen. Der Betreiber
kann Konten sperren, wenn ein begründeter Verdacht besteht.</p>

<h2>4. Guthaben und Abrechnung</h2>
<p>Soweit Guthaben verwendet werden, richten sich Preis und Verbrauch nach der jeweils
veröffentlichten Übersicht. Guthaben sind nicht übertragbar; ein Anspruch auf Auszahlung besteht
nur, soweit gesetzlich zwingend.</p>

<h2>5. Haftung</h2>
<p>Der Betreiber haftet unbeschränkt für Vorsatz und grobe Fahrlässigkeit sowie nach dem
ProdHaftG. Im Übrigen ist die Haftung auf den vertragstypischen, vorhersehbaren Schaden begrenzt.
Antworten eines KI-Modells sind keine Rechts-, Steuer- oder Medizinberatung; die Prüfung der
Ergebnisse obliegt der nutzenden Stelle.</p>

<h2>6. Änderungen</h2>
<p>Änderungen dieser Bedingungen werden mindestens zwei Wochen vor Inkrafttreten angekündigt.
Widerspricht niemand, gelten sie als angenommen.</p>
"""
    return _seite("Nutzungsbedingungen", inhalt)
