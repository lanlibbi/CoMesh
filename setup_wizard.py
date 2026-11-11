"""Erstinstallation im Browser: den Superadmin anlegen.

Solange kein Konto mit der Rolle ``admin`` existiert, ist das Setup offen — aber
nicht für jeden: der Aufruf braucht das Einmal-Token, das beim Start in
``$DATA_DIR/setup_token.txt`` geschrieben und ins Log ausgegeben wird. Wer die
Instanz einrichtet, sitzt davor und liest es ab. Eine frische Instanz, die im
Internet hängt, ist damit **nicht** für den ersten Fremden übernehmbar.

Nach dem Abschluss ist der Endpunkt dauerhaft zu (``410 Gone``); Token und die
vom Start erzeugten Notfall-Dateien (``admin_api_key.txt``, ``admin_password.txt``)
sind gelöscht. Der Admin-Bootstrap in ``main.py`` fasst das Konto danach nicht mehr
an — sonst würde der nächste Neustart das eben gewählte Passwort überschreiben.
"""
import logging
import os
import re
import secrets
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import hash_password
from database import DATA_DIR, SessionLocal, get_db
from models import ADMIN_ROLE, SystemSetting, User
from ratelimit import client_ip, limit_login

log = logging.getLogger("comesh.setup")

router = APIRouter(prefix="/setup", tags=["setup"])

SETUP_FLAG = "setup_completed_at"
SETUP_TOKEN_FILE = os.path.join(DATA_DIR, "setup_token.txt")
ADMIN_KEY_FILE = os.path.join(DATA_DIR, "admin_api_key.txt")
ADMIN_PW_FILE = os.path.join(DATA_DIR, "admin_password.txt")

MIN_PASSWORD = 10
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")

# Ein Prozess, ein Anlegen: der Dienst läuft bewusst mit einem Uvicorn-Worker
# (WS-Registry und Auftrags-Futures sind prozesslokal). Der Riegel verhindert,
# dass zwei gleichzeitige Aufrufe beide "noch kein Admin" sehen und zwei Konten
# anlegen. Bei mehreren Workern gehört hier ein Datenbank-Riegel hin.
_create_lock = threading.Lock()


# --------------------------------------------------------------------------- Zustand
def _flag(db: Session) -> Optional[SystemSetting]:
    return db.query(SystemSetting).filter(SystemSetting.key == SETUP_FLAG).first()


def setup_completed(db: Optional[Session] = None) -> bool:
    """True, sobald die Einrichtung abgeschlossen ist (oder ein Admin existiert)."""
    eigene = db is None
    db = db or SessionLocal()
    try:
        if _flag(db) is not None:
            return True
        return db.query(User).filter(User.role == ADMIN_ROLE).count() > 0
    finally:
        if eigene:
            db.close()


def setup_required() -> bool:
    """Nur wahr, wenn weder Abschluss-Marke noch Admin-Konto existieren."""
    db = SessionLocal()
    try:
        if _flag(db) is not None:
            return False
        return db.query(User).filter(User.role == ADMIN_ROLE).count() == 0
    finally:
        db.close()


def ensure_setup_token() -> Optional[str]:
    """Token für die Erstinstallation bereitstellen (idempotent).

    Wird beim Start aufgerufen: schreibt das Token in ``$DATA_DIR/setup_token.txt``
    (mode 0600) und ins Log. Ist das Setup erledigt, werden die Datei und der
    Token gelöscht statt erzeugt.
    """
    if not setup_required():
        # Nur das Setup-Token aufraeumen. Die Dateien admin_api_key.txt und
        # admin_password.txt gehoeren zum Umgebungs-Weg (ADMIN_API_KEY) und werden
        # dort weiter gebraucht: loescht man sie, erzeugt der Bootstrap beim
        # naechsten Start ein NEUES Passwort und setzt den Hash neu — das
        # dokumentierte Passwort waere dann stillschweigend ungueltig.
        _remove(SETUP_TOKEN_FILE)
        return None

    token = ""
    try:
        if os.path.exists(SETUP_TOKEN_FILE):
            with open(SETUP_TOKEN_FILE, "r", encoding="utf-8") as fh:
                token = fh.read().strip()
    except OSError as e:
        log.warning(f"setup token unreadable: {e}")

    if not token:
        token = secrets.token_urlsafe(24)
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            fd = os.open(SETUP_TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(token + "\n")
        except OSError as e:
            log.error(f"setup token not writable ({SETUP_TOKEN_FILE}): {e}")
            return None

    log.warning("=" * 68)
    log.warning("Setup-Token für die Ersteinrichtung: %s", token)
    log.warning("Aufrufen: http://<host>:<port>/setup.html  (Datei: %s)", SETUP_TOKEN_FILE)
    log.warning("Dieser Hinweis erscheint nur, solange kein Administrator existiert.")
    log.warning("=" * 68)
    return token


def _remove(pfad: str) -> None:
    try:
        os.remove(pfad)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning(f"{pfad} not removed: {e}")


# --------------------------------------------------------------------------- Schemas
class SetupStatus(BaseModel):
    required: bool
    token_required: bool = True
    min_password: int = MIN_PASSWORD


class SetupAdminIn(BaseModel):
    token: str = Field(..., max_length=128)
    email: str = Field(..., max_length=200)
    name: str = Field("Administrator", max_length=80)
    password: str = Field(..., max_length=200)


class SetupAdminOut(BaseModel):
    email: str
    name: str
    role: str


# --------------------------------------------------------------------------- Endpunkte
@router.get("/status", response_model=SetupStatus)
def status() -> SetupStatus:
    """Öffentlich: braucht diese Instanz noch eine Ersteinrichtung?

    Verrät nur einen Boolean, keine Konten, keine Adressen.
    """
    return SetupStatus(required=setup_required())


@router.post("/admin", response_model=SetupAdminOut, status_code=201)
def create_admin(req: SetupAdminIn, request: Request, db: Session = Depends(get_db)) -> SetupAdminOut:
    """Legt den ersten Administrator an. Nur einmal, nur mit Token."""
    if setup_completed(db):
        raise HTTPException(status_code=410, detail="Setup already completed")

    email = (req.email or "").strip().lower()
    name = (req.name or "").strip() or "Administrator"
    token = (req.token or "").strip()

    # Fehlversuche zählen gegen IP + Adresse — das Token ist kein Freibrief zum Raten.
    limit_login(client_ip(request), email or "setup")

    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Invalid email address")
    if len(req.password or "") < MIN_PASSWORD:
        raise HTTPException(status_code=422, detail=f"Password needs at least {MIN_PASSWORD} characters")

    erwartet = ""
    try:
        with open(SETUP_TOKEN_FILE, "r", encoding="utf-8") as fh:
            erwartet = fh.read().strip()
    except OSError:
        erwartet = ""

    if not erwartet:
        # Kein Token vorhanden, aber Setup offen: dann ist die Instanz über den
        # Umgebungsweg eingerichtet (ADMIN_API_KEY) — hier nichts anlegen.
        raise HTTPException(status_code=409, detail="Setup is not available; use ADMIN_API_KEY or restart the service")

    if not token or not secrets.compare_digest(token, erwartet):
        raise HTTPException(status_code=403, detail="Invalid setup token")

    with _create_lock:
        if setup_completed(db):
            raise HTTPException(status_code=410, detail="Setup already completed")
        if db.query(User).filter(User.email == email).first() is not None:
            raise HTTPException(status_code=409, detail="Email already registered")

        user = User(
            email=email,
            name=name,
            role=ADMIN_ROLE,
            is_active=True,
            registration_status="approved",
            password_hash=hash_password(req.password),
        )
        db.add(user)
        db.flush()
        db.add(SystemSetting(key=SETUP_FLAG, value="manual-wizard"))
        db.commit()
        db.refresh(user)

    # Ab hier gibt es keine Hintertür mehr: Token und die vom Start erzeugten
    # Notfall-Dateien verschwinden, der Bootstrap lässt das Konto in Ruhe.
    _remove(SETUP_TOKEN_FILE)
    _remove(ADMIN_KEY_FILE)
    _remove(ADMIN_PW_FILE)
    log.warning("Setup abgeschlossen: Administrator %s angelegt (id %s)", user.email, user.id)

    return SetupAdminOut(email=user.email, name=user.name, role=user.role)
