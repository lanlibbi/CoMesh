"""Rechtstexte: Impressum, Datenschutz, Nutzungsbedingungen — pro Instanz.

Die Rechtstexte gehören zum **Betreiber einer Instanz**, nicht zum Projekt. Wer
das Repo klont und seine Instanz öffentlich betreibt, ist der Impressumspflichtige
— nicht der Autor der Software. Deshalb stehen hier nirgends feste Angaben:

  * Der Betreiber trägt sie in der Admin-Konsole ein (``/admin/legal``); sie landen
    in ``system_settings`` unter ``legal.<feld>``.
  * Ist dort nichts gesetzt, gilt die Umgebungsvariable (``IMPRESSUM_*``) — das ist
    der Weg für automatisierte Installationen und Container ohne Admin-Login.
  * Ist beides leer, sagt die Seite das ausdrücklich: roter Hinweis mit der Liste
    der fehlenden Pflichtangaben, Verweis auf das Upstream-Projekt und ``noindex``.
    Eine leere Seite, die wie ein vollständiges Impressum aussieht, wäre schlimmer
    als eine ehrliche Baustelle.

Damit kann keine fremde Instanz versehentlich mit den Daten eines anderen
Betreibers auftreten.
"""
import html
import os
from typing import Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models import AdminAuditLog, SystemSetting, User

router = APIRouter(prefix="/legal", tags=["legal"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])

UPSTREAM_URL = "https://github.com/lanlibbi/CoMesh"
SETTING_PREFIX = "legal."

# (Feldname, Bezeichnung für die Admin-Maske, Pflichtangabe?)
FELDER: List[Tuple[str, str, bool]] = [
    ("IMPRESSUM_FIRMA", "Firma oder Name", True),
    ("IMPRESSUM_STRASSE", "Straße und Hausnummer", True),
    ("IMPRESSUM_PLZ_ORT", "Postleitzahl und Ort", True),
    ("IMPRESSUM_LAND", "Land", False),
    ("IMPRESSUM_EMAIL", "E-Mail-Adresse", True),
    ("IMPRESSUM_TELEFON", "Telefon", False),
    ("IMPRESSUM_VERTRETEN", "Vertreten durch", False),
    ("IMPRESSUM_REGISTER", "Registereintrag", False),
    ("IMPRESSUM_USTID", "Umsatzsteuer-Identifikationsnummer", False),
    ("DATENSCHUTZ_EMAIL", "E-Mail für Datenschutzanfragen", True),
    ("HOSTING_ANBIETER", "Hosting-Anbieter", False),
]
FELD_NAMEN = [f[0] for f in FELDER]
PFLICHT = [f[0] for f in FELDER if f[2]]


# --------------------------------------------------------------------------- Werte
def _aus_datenbank(db: Session) -> Dict[str, str]:
    rows = db.query(SystemSetting).filter(SystemSetting.key.like(SETTING_PREFIX + "%")).all()
    werte = {}
    for row in rows:
        name = row.key[len(SETTING_PREFIX):].upper()
        if row.value and row.value.strip():
            werte[name] = row.value.strip()
    return werte


def _wert(name: str, db: Session = None, standard: str = "") -> str:
    """Datenbank gewinnt gegen Umgebung, Umgebung gegen den Standardwert."""
    if db is not None:
        row = db.query(SystemSetting).filter(SystemSetting.key == SETTING_PREFIX + name.lower()).first()
        if row is not None and (row.value or "").strip():
            return row.value.strip()
    return (os.environ.get(name) or standard).strip()


def werte_mit_quelle(db: Session) -> Dict[str, Dict[str, str]]:
    """Für die Admin-Maske: Wert und woher er kommt."""
    db_werte = _aus_datenbank(db)
    out = {}
    for name, _, _ in FELDER:
        if name in db_werte:
            out[name] = {"wert": db_werte[name], "quelle": "datenbank"}
        elif (os.environ.get(name) or "").strip():
            out[name] = {"wert": os.environ[name].strip(), "quelle": "umgebung"}
        else:
            out[name] = {"wert": "", "quelle": "leer"}
    return out


def fehlende_pflichtangaben(db: Session) -> List[str]:
    return [n for n in PFLICHT if not _wert(n, db)]


def speichern(db: Session, neue_werte: Dict[str, str]) -> None:
    """Nur bekannte Felder, leere Werte löschen den Eintrag (dann gilt wieder die Umgebung)."""
    for name, wert in neue_werte.items():
        if name not in FELD_NAMEN:
            continue
        key = SETTING_PREFIX + name.lower()
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        sauber = (wert or "").strip()
        if sauber:
            if row is None:
                db.add(SystemSetting(key=key, value=sauber))
            else:
                row.value = sauber
        elif row is not None:
            db.delete(row)
    db.commit()


# --------------------------------------------------------------------------- Seiten
def _kopf(titel: str, db: Session) -> Tuple[str, bool]:
    fehlt = fehlende_pflichtangaben(db)
    banner = ""
    if fehlt:
        labels = {name: label for name, label, _ in FELDER}
        banner = (
            "<div class=\"warnung\"><b>Diese Seite ist noch nicht vollständig.</b> "
            "Der Betreiber dieser Instanz hat folgende Pflichtangaben noch nicht eingetragen: "
            + html.escape("; ".join(labels[n] for n in fehlt))
            + ".<br /><span class=\"klein\">Betrieben wird diese Instanz von der Person oder "
            "Organisation, die sie bereitstellt — nicht vom Autor der Software "
            f"(<a href=\"{UPSTREAM_URL}\">{UPSTREAM_URL}</a>).</span></div>"
        )
    return banner, bool(fehlt)


def _seite(titel: str, inhalt: str, db: Session) -> HTMLResponse:
    banner, unvollstaendig = _kopf(titel, db)
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
  .warnung .klein {{ color:#ffb9b9; font-size:14px; }}
  p, li {{ color:#c8cdd6; }}
  code {{ background:#1a1f27; padding:1px 5px; border-radius:4px; }}
</style>
</head>
<body><main>
<a class="zurueck" href="/index.html">← CoMesh</a>
{banner}
{inhalt}
</main></body></html>"""
    return HTMLResponse(doc, headers={"X-Robots-Tag": "noindex" if unvollstaendig else "index, follow"})


@router.get("/impressum", response_class=HTMLResponse)
def impressum(db: Session = Depends(get_db)) -> HTMLResponse:
    w = lambda n, s="": _wert(n, db, s)  # noqa: E731
    zeilen = [w("IMPRESSUM_FIRMA"), w("IMPRESSUM_STRASSE"), w("IMPRESSUM_PLZ_ORT"),
              w("IMPRESSUM_LAND", "Deutschland")]
    kontakt = []
    if w("IMPRESSUM_TELEFON"):
        kontakt.append("Telefon: " + html.escape(w("IMPRESSUM_TELEFON")))
    if w("IMPRESSUM_EMAIL"):
        kontakt.append('E-Mail: <a href="mailto:{0}">{0}</a>'.format(html.escape(w("IMPRESSUM_EMAIL"))))
    register = []
    if w("IMPRESSUM_VERTRETEN"):
        register.append("Vertreten durch: " + html.escape(w("IMPRESSUM_VERTRETEN")))
    if w("IMPRESSUM_REGISTER"):
        register.append("Registereintrag: " + html.escape(w("IMPRESSUM_REGISTER")))
    if w("IMPRESSUM_USTID"):
        register.append("Umsatzsteuer-Identifikationsnummer: " + html.escape(w("IMPRESSUM_USTID")))

    inhalt = (
        "<h1>Impressum</h1>"
        "<h2>Angaben gemäß § 5 DDG</h2><p>"
        + "<br />".join(html.escape(z) for z in zeilen if z)
        + "</p>"
        + ("<h2>Kontakt</h2><p>" + "<br />".join(kontakt) + "</p>" if kontakt else "")
        + ("<h2>Weitere Angaben</h2><p>" + "<br />".join(register) + "</p>" if register else "")
        + "<h2>Verantwortlich für den Inhalt</h2><p>"
        + html.escape(w("IMPRESSUM_VERTRETEN") or w("IMPRESSUM_FIRMA") or "siehe oben")
        + "</p>"
        "<h2>Streitbeilegung</h2><p>Wir sind nicht verpflichtet und nicht bereit, an "
        "Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle teilzunehmen.</p>"
    )
    return _seite("Impressum", inhalt, db)


@router.get("/datenschutz", response_class=HTMLResponse)
def datenschutz(db: Session = Depends(get_db)) -> HTMLResponse:
    mail = html.escape(_wert("DATENSCHUTZ_EMAIL", db) or _wert("IMPRESSUM_EMAIL", db))
    hosting = html.escape(_wert("HOSTING_ANBIETER", db) or "den Betreiber dieser Instanz")
    inhalt = f"""
<h1>Datenschutzerklärung</h1>
<p>Diese Instanz betreibt eine Vermittlungsplattform für KI-Modelle. Nachfolgend steht, welche
Daten dabei verarbeitet werden, zu welchem Zweck und wie lange.</p>

<h2>1. Verantwortlicher</h2>
<p>{html.escape(_wert("IMPRESSUM_FIRMA", db))}, {html.escape(_wert("IMPRESSUM_STRASSE", db))},
{html.escape(_wert("IMPRESSUM_PLZ_ORT", db))} — Kontakt: <a href="mailto:{mail}">{mail}</a></p>

<h2>2. Welche Daten verarbeitet werden</h2>
<ul>
  <li><b>Konto:</b> E-Mail-Adresse, Name, Passwort-Hash (PBKDF2-SHA256), Rolle, Guthaben,
      Zeitpunkt der Registrierung. Rechtsgrundlage: Vertragserfüllung (Art. 6 Abs. 1 lit. b DSGVO).</li>
  <li><b>Nutzung:</b> welches Modell mit welcher Tokenzahl aufgerufen wurde, Zeitpunkt und
      Statuscode. Das ist die Abrechnungsgrundlage und zugleich Mißbrauchserkennung
      (Art. 6 Abs. 1 lit. b und f DSGVO).</li>
  <li><b>Anfrageinhalte:</b> Prompts und Antworten werden zur Beantwortung an den Rechner
      weitergegeben, der das Modell betreibt. Eine dauerhafte Speicherung der Inhalte findet
      nicht statt; gespeichert werden Metadaten (Modell, Tokenzahlen, Zeitpunkt).</li>
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
    return _seite("Datenschutz", inhalt, db)


@router.get("/agb", response_class=HTMLResponse)
def agb(db: Session = Depends(get_db)) -> HTMLResponse:
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
    return _seite("Nutzungsbedingungen", inhalt, db)


# --------------------------------------------------------------------------- Admin-API
class LegalWerteIn(BaseModel):
    """Alle Felder optional: gesetzt = speichern, leer = Eintrag löschen."""

    IMPRESSUM_FIRMA: str = ""
    IMPRESSUM_STRASSE: str = ""
    IMPRESSUM_PLZ_ORT: str = ""
    IMPRESSUM_LAND: str = ""
    IMPRESSUM_EMAIL: str = ""
    IMPRESSUM_TELEFON: str = ""
    IMPRESSUM_VERTRETEN: str = ""
    IMPRESSUM_REGISTER: str = ""
    IMPRESSUM_USTID: str = ""
    DATENSCHUTZ_EMAIL: str = ""
    HOSTING_ANBIETER: str = ""


class LegalStand(BaseModel):
    werte: Dict[str, Dict[str, str]]
    fehlend: List[str]
    felder: List[Dict[str, object]]
    upstream: str
    vollstaendig: bool


def _stand(db: Session) -> LegalStand:
    fehlend = fehlende_pflichtangaben(db)
    return LegalStand(
        werte=werte_mit_quelle(db),
        fehlend=fehlend,
        felder=[{"name": n, "label": l, "pflicht": p} for n, l, p in FELDER],
        upstream=UPSTREAM_URL,
        vollstaendig=not fehlend,
    )


@admin_router.get("/legal", response_model=LegalStand)
def legal_stand(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> LegalStand:
    """Aktuelle Rechtstext-Angaben dieser Instanz samt Quelle (Datenbank/Umgebung/leer)."""
    return _stand(db)


@admin_router.put("/legal", response_model=LegalStand)
def legal_setzen(req: LegalWerteIn, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)) -> LegalStand:
    """Angaben des Betreibers speichern. Sie ersetzen die Umgebungsvariablen."""
    speichern(db, req.model_dump())
    try:
        db.add(AdminAuditLog(
            admin_user_id=getattr(admin, "id", 0),
            action="legal.update",
            target_type="settings",
            target_id=None,
            idempotency_key=None,
            payload="{}",
            result=json.dumps({"fehlend": fehlende_pflichtangaben(db)}),
        ))
        db.commit()
    except Exception:  # Audit darf die Änderung nie verhindern
        db.rollback()
    return _stand(db)
