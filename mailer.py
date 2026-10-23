"""Mailversand für das Portal — Einstellungen in der Datenbank, Versand ohne neue Abhängigkeit.

Die Einstellungen liegen als Schlüssel/Werte in `system_settings` (dieselbe Tabelle, die schon
`credits_enabled` trägt), damit ein Administrator sie in der Oberfläche pflegen kann, ohne auf den
Server zu müssen. Das Kennwort wird nie über die API zurückgegeben — gelesen wird nur, **ob** eines
gesetzt ist.

Versand über `smtplib` aus der Standardbibliothek; drei Sicherheitsstufen: `starttls` (Port 587),
`ssl` (Port 465) und `none` (nur für einen lokalen Relay sinnvoll).

Benachrichtigungen laufen in einem eigenen Thread: eine Anmeldung darf nicht daran scheitern oder
darauf warten, dass ein fremder Mailserver antwortet.
"""
import json
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr, formatdate

from models import SystemSetting

SCHLUESSEL = {
    "enabled": "mail.enabled",
    "host": "mail.host",
    "port": "mail.port",
    "security": "mail.security",          # starttls | ssl | none
    "username": "mail.username",
    "password": "mail.password",
    "sender": "mail.from",
    "sender_name": "mail.from_name",
    "notify_to": "mail.notify_to",        # eine oder mehrere Adressen, Komma-getrennt
    "notify_pending": "mail.notify_pending",
}

VORGABEN = {
    "enabled": False,
    "host": "",
    "port": 587,
    "security": "starttls",
    "username": "",
    "password": "",
    "sender": "",
    "sender_name": "CoMesh",
    "notify_to": "",
    "notify_pending": True,
}


def _lies(db) -> dict:
    werte = dict(VORGABEN)
    for feld, schluessel in SCHLUESSEL.items():
        zeile = db.query(SystemSetting).filter(SystemSetting.key == schluessel).first()
        if zeile is None:
            continue
        roh = zeile.value
        vorgabe = VORGABEN[feld]
        if isinstance(vorgabe, bool):
            werte[feld] = roh in ("1", "true", "True", "ja")
        elif isinstance(vorgabe, int):
            try:
                werte[feld] = int(roh)
            except ValueError:
                pass
        else:
            werte[feld] = roh
    return werte


def lade(db) -> dict:
    """Einstellungen für die API — ohne Kennwort, dafür mit dem Hinweis, ob eines gesetzt ist."""
    werte = _lies(db)
    kennwort = werte.pop("password", "")
    werte["password_set"] = bool(kennwort)
    return werte


def speichere(db, daten: dict) -> dict:
    """Teil-Update. Ein leeres `password` lässt das gespeicherte stehen (Feld bleibt maskiert)."""
    for feld, wert in daten.items():
        if feld not in SCHLUESSEL or feld == "password_set":
            continue
        if feld == "password" and (wert is None or wert == ""):
            continue
        if isinstance(wert, bool):
            text = "1" if wert else "0"
        else:
            text = str(wert)
        zeile = db.query(SystemSetting).filter(SystemSetting.key == SCHLUESSEL[feld]).first()
        if zeile is None:
            db.add(SystemSetting(key=SCHLUESSEL[feld], value=text))
        else:
            zeile.value = text
    db.commit()
    return lade(db)


def _verbinde(werte: dict):
    host, port = werte["host"], int(werte["port"] or 587)
    if werte["security"] == "ssl":
        s = smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context())
    else:
        s = smtplib.SMTP(host, port, timeout=15)
        s.ehlo()
        if werte["security"] == "starttls":
            s.starttls(context=ssl.create_default_context())
            s.ehlo()
    if werte["username"]:
        s.login(werte["username"], werte["password"] or "")
    return s


def sende(db, an: str, betreff: str, text: str) -> tuple[bool, str]:
    """Eine Nachricht verschicken. Gibt (ok, Meldung) zurück und wirft nie."""
    werte = _lies(db)
    if not werte["host"]:
        return False, "Kein SMTP-Server eingetragen."
    absender = werte["sender"] or werte["username"]
    if not absender:
        return False, "Keine Absenderadresse eingetragen."
    empfaenger = [a.strip() for a in str(an).replace(";", ",").split(",") if a.strip()]
    if not empfaenger:
        return False, "Kein Empfänger angegeben."

    nachricht = EmailMessage()
    nachricht["From"] = formataddr((werte["sender_name"] or "CoMesh", absender))
    nachricht["To"] = ", ".join(empfaenger)
    nachricht["Subject"] = betreff
    nachricht["Date"] = formatdate(localtime=True)
    nachricht.set_content(text)

    try:
        with _verbinde(werte) as s:
            s.send_message(nachricht)
        return True, f"Nachricht an {len(empfaenger)} Empfänger übergeben."
    except Exception as e:                                     # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def sende_im_hintergrund(db, an: str, betreff: str, text: str) -> None:
    """Versand auslagern: eine Anmeldung darf nicht auf einen Mailserver warten."""
    def lauf():
        try:
            from database import SessionLocal
            eigene = SessionLocal()
            try:
                sende(eigene, an, betreff, text)
            finally:
                eigene.close()
        except Exception:
            pass

    threading.Thread(target=lauf, daemon=True).start()


def benachrichtige_freigabe(db, user) -> None:
    """Admin informieren, dass ein Konto auf Freigabe wartet. Fehler bleiben folgenlos."""
    try:
        werte = _lies(db)
        if not werte["enabled"] or not werte["notify_pending"] or not werte["notify_to"]:
            return
        betreff = f"CoMesh: {user.email} wartet auf Freigabe"
        text = (
            "Ein neues Konto wartet auf Freigabe.\n\n"
            f"E-Mail:   {user.email}\n"
            f"Name:     {user.name or '—'}\n"
            f"Rolle:    {user.role}\n"
            f"Konto-ID: {user.id}\n\n"
            "Freigeben oder ablehnen unter: Freigaben → Filter „Ausstehend“.\n"
        )
        sende_im_hintergrund(db, werte["notify_to"], betreff, text)
    except Exception:
        pass
