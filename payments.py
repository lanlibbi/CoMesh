"""
Payment processing for the GPU-Pool POC.

Supports multiple providers in test/mock mode:
  - Stripe (test mode)  -> /payments/stripe/*
  - PayPal (sandbox)    -> /payments/paypal/*
  - Alipay (via Stripe) -> /payments/alipay/*
  - Apple Pay (Stripe)  -> /payments/applepay/*

In POC we keep all SDKs OPTIONAL: if the corresponding library is not
installed, the endpoints fall back to a deterministic mock so the flow
can be tested end-to-end without real credentials.
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from netinfo import request_base_url

from auth import get_current_user
from database import get_db
from models import CreditTransaction, Payment, User, get_user_credits

log = logging.getLogger("gpu-pool.payments")

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")          # sk_test_...
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")  # pk_test_...
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")  # 'sandbox' | 'live'
# Empfaengerkonto, gegen das jede IPN geprueft wird. Im Live-Betrieb Pflicht:
# ohne diese Adresse kann die Anwendung nicht feststellen, ob das Geld wirklich
# bei ihr angekommen ist.
PAYPAL_RECEIVER_EMAIL = os.environ.get("PAYPAL_RECEIVER_EMAIL", "").strip().lower()
# Verifikations-Endpunkt. Standard folgt PAYPAL_MODE (PayPals dokumentiertes
# IPN-Verfahren: die Meldung unveraendert mit cmd=_notify-validate zurueckschicken).
PAYPAL_IPN_URL = os.environ.get("PAYPAL_IPN_URL", "").strip()
PAYPAL_IPN_TIMEOUT = float(os.environ.get("PAYPAL_IPN_TIMEOUT", "15") or 15)
# Stripe-API (nur genutzt, wenn STRIPE_SECRET_KEY gesetzt ist).
STRIPE_API_BASE = os.environ.get("STRIPE_API_BASE", "https://api.stripe.com").rstrip("/")
# Public base URL of this portal. Required in production (payment providers have to
# redirect the buyer back). Left unset, the portal derives it from the request that
# started the checkout, so a deployment on DHCP needs no fixed address.
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "").rstrip("/")

# Optional SDKs
try:
    import stripe  # type: ignore
    stripe.api_key = STRIPE_SECRET_KEY or "sk_test_mock"
    STRIPE_AVAILABLE = True
except Exception:  # pragma: no cover
    STRIPE_AVAILABLE = False
    stripe = None  # type: ignore

try:
    import paypalrestsdk  # type: ignore
    PAYPAL_AVAILABLE = True
except Exception:  # pragma: no cover
    PAYPAL_AVAILABLE = False
    paypalrestsdk = None  # type: ignore


def public_base_url(request: Optional[Request] = None) -> str:
    """Base URL for provider return links: APP_PUBLIC_URL, else the caller's own view.

    Deriving it from the request means a fresh deployment on a DHCP LAN works
    without configuring anything; set APP_PUBLIC_URL when the portal is reached
    through a different name than the provider redirect comes back to.
    """
    if APP_PUBLIC_URL:
        return APP_PUBLIC_URL
    derived = request_base_url(request)
    if derived:
        return derived
    return "http://localhost:8000"

# ----------------------------------------------------------------------------
# Credit packages (canonical, single source of truth)
# ----------------------------------------------------------------------------
CREDIT_PACKAGES: Dict[str, Dict[str, Any]] = {
    "starter":    {"name": "Starter",    "credits": 1_000,  "price_eur": 10,   "bonus": 0},
    "pro":        {"name": "Pro",        "credits": 5_000,  "price_eur": 45,   "bonus": 500},
    "business":   {"name": "Business",   "credits": 20_000, "price_eur": 160,  "bonus": 4_000},
    "enterprise": {"name": "Enterprise", "credits": 100_000,"price_eur": 700,  "bonus": 25_000},
}

def package_total_credits(pkg: Dict[str, Any]) -> int:
    return int(pkg["credits"]) + int(pkg.get("bonus", 0))


# ----------------------------------------------------------------------------
# Sicherheits-Gates (Fix 2026-11-02)
# ----------------------------------------------------------------------------
def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def mock_payments_allowed() -> bool:
    """Duerfen Mock-/Simulationspfade Guthaben gutschreiben?

    Default: nein. Frueher fuehrten /payments/paypal/capture?mock=1,
    /payments/stripe/simulate-success und die "success"-Rueckkehr-URLs ohne
    jede Anbieter-Bestaetigung zur Gutschrift — in Produktion ein offenes Tor.
    Nur mit PAYMENTS_ALLOW_MOCK=1 (Entwicklung/Tests) sind sie erlaubt.
    """
    return _env_truthy("PAYMENTS_ALLOW_MOCK", False)


def paypal_ipn_url() -> str:
    """PayPals IPN-Verifikationsendpunkt (per PAYPAL_IPN_URL ueberschreibbar)."""
    override = (os.environ.get("PAYPAL_IPN_URL", PAYPAL_IPN_URL) or "").strip()
    if override:
        return override
    mode = (os.environ.get("PAYPAL_MODE", PAYPAL_MODE) or "sandbox").strip().lower()
    host = "ipnpb.paypal.com" if mode == "live" else "ipnpb.sandbox.paypal.com"
    return f"https://{host}/cgi-bin/webscr"


def _expected_receiver() -> str:
    return (os.environ.get("PAYPAL_RECEIVER_EMAIL", PAYPAL_RECEIVER_EMAIL) or "").strip().lower()


def _paypal_mode() -> str:
    return (os.environ.get("PAYPAL_MODE", PAYPAL_MODE) or "sandbox").strip().lower()


async def _paypal_verify_ipn(raw_body: bytes, transport: Optional[Any] = None) -> bool:
    """PayPals dokumentierte IPN-Pruefung.

    Der *unveraenderte* Rohtext der Meldung wird — in derselben Kodierung und
    Reihenfolge — um ``cmd=_notify-validate`` ergaenzt und an PayPal
    zurueckgeschickt. Nur die Antwort ``VERIFIED`` gilt als Beleg dafuer, dass
    PayPal diese Meldung tatsaechlich erzeugt hat.

    Fehler (Netz, Timeout, unerwartete Antwort) zaehlen als *nicht* verifiziert:
    die Funktion schlaegt geschlossen fehl, nie offen.
    """
    body = (raw_body or b"").strip()
    if not body:
        log.warning("PayPal IPN rejected: leerer Body")
        return False

    payload = body + b"&cmd=_notify-validate"
    url = paypal_ipn_url()
    try:
        async with httpx.AsyncClient(timeout=PAYPAL_IPN_TIMEOUT, transport=transport) as client:
            resp = await client.post(
                url,
                content=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "CoMesh-IPN-Verify/1.0",
                },
            )
    except Exception as e:  # noqa: BLE001 - jede Stoerung ist ein "nicht verifiziert"
        log.error("PayPal IPN verification unreachable (%s): %s", url, e)
        return False

    verdict = (resp.text or "").strip()
    if verdict == "VERIFIED":
        log.info("PayPal IPN verified via %s", url)
        return True
    log.warning(
        "PayPal IPN rejected via %s: HTTP %s, Antwort %r",
        url, resp.status_code, verdict[:80],
    )
    return False


async def _stripe_get(path: str) -> Optional[Dict[str, Any]]:
    """GET gegen die Stripe-API mit dem Secret Key; None bei jedem Fehler."""
    key = os.environ.get("STRIPE_SECRET_KEY", STRIPE_SECRET_KEY)
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{STRIPE_API_BASE}{path}", auth=(key, ""))
    except Exception as e:  # noqa: BLE001
        log.error("Stripe API unreachable (%s): %s", path, e)
        return None
    if resp.status_code != 200:
        log.error("Stripe API %s: HTTP %s %r", path, resp.status_code, resp.text[:120])
        return None
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return None


async def _confirm_stripe_payment(
    payment: Payment,
    *,
    session_id: Optional[str] = None,
    payment_intent: Optional[str] = None,
) -> None:
    """Bestaetigt bei Stripe, dass *payment* wirklich bezahlt wurde.

    Die "success"-Rueckkehr-URLs sind reine Browser-Redirects und beweisen
    nichts — sie werden von jedem aufrufbar, der die payment_id kennt. Ohne
    bestaetigte Zahlung wird kein Guthaben gutgeschrieben. Ohne Stripe-
    Konfiguration geht das nur im ausdruecklichen Mock-Modus.
    """
    key = os.environ.get("STRIPE_SECRET_KEY", STRIPE_SECRET_KEY)
    if not key:
        if mock_payments_allowed():
            log.warning(
                "Stripe-Bestaetigung uebersprungen: PAYMENTS_ALLOW_MOCK=1 und kein Secret Key "
                "(payment #%s)", payment.id,
            )
            return
        log.error("Stripe-Rueckkehr abgelehnt: STRIPE_SECRET_KEY fehlt (payment #%s)", payment.id)
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    obj: Optional[Dict[str, Any]] = None
    if session_id:
        obj = await _stripe_get(f"/v1/checkout/sessions/{quote(session_id, safe='')}")
        if not obj or obj.get("payment_status") != "paid":
            log.error("Stripe-Session %s nicht bezahlt (payment #%s)", session_id, payment.id)
            raise HTTPException(status_code=402, detail="Stripe session is not paid")
    elif payment_intent:
        obj = await _stripe_get(f"/v1/payment_intents/{quote(payment_intent, safe='')}")
        if not obj or obj.get("status") != "succeeded":
            log.error("Stripe-PaymentIntent %s nicht erfolgreich (payment #%s)", payment_intent, payment.id)
            raise HTTPException(status_code=402, detail="Stripe payment intent not succeeded")
    else:
        log.error("Stripe-Rueckkehr ohne session_id/payment_intent (payment #%s)", payment.id)
        raise HTTPException(status_code=400, detail="Missing Stripe reference")

    meta = obj.get("metadata") or {}
    if meta.get("payment_id") and str(meta["payment_id"]) != str(payment.id):
        log.error(
            "Stripe-Objekt gehoert zu payment #%s, nicht #%s", meta.get("payment_id"), payment.id
        )
        raise HTTPException(status_code=400, detail="Stripe object belongs to another payment")

    amount = obj.get("amount_total", obj.get("amount"))
    if amount is not None and int(amount) != int(round(float(payment.amount) * 100)):
        log.error(
            "Stripe-Betrag passt nicht: %s != %s (payment #%s)",
            amount, int(round(float(payment.amount) * 100)), payment.id,
        )
        raise HTTPException(status_code=400, detail="Stripe amount mismatch")

    currency = (obj.get("currency") or "").upper()
    if currency and currency != (payment.currency or "EUR").upper():
        log.error("Stripe-Waehrung %s != %s (payment #%s)", currency, payment.currency, payment.id)
        raise HTTPException(status_code=400, detail="Stripe currency mismatch")


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------
router = APIRouter(prefix="/payments", tags=["payments"])


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class CheckoutRequest(BaseModel):
    package_id: str  # starter | pro | business | enterprise
    provider: str    # stripe | paypal | alipay | applepay
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CheckoutResponse(BaseModel):
    payment_id: int
    provider: str
    status: str
    # Stripe
    checkout_url: Optional[str] = None
    session_id: Optional[str] = None
    client_secret: Optional[str] = None
    # PayPal
    approval_url: Optional[str] = None
    paypal_order_id: Optional[str] = None
    # Alipay / Apple Pay
    payment_url: Optional[str] = None
    # Mock fallback
    mock: bool = False
    message: Optional[str] = None


class PaymentInfo(BaseModel):
    id: int
    provider: str
    amount_eur: float
    credits_added: int
    status: str
    transaction_id: Optional[str]
    created_at: str


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _get_package(package_id: str) -> Dict[str, Any]:
    pkg = CREDIT_PACKAGES.get(package_id.lower())
    if not pkg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown package '{package_id}'. Valid: {list(CREDIT_PACKAGES)}",
        )
    return pkg


def _serialize_payment(p: Payment) -> PaymentInfo:
    return PaymentInfo(
        id=p.id,
        provider=p.provider,
        amount_eur=p.amount,
        credits_added=p.credits_added,
        status=p.status,
        transaction_id=p.transaction_id,
        created_at=p.created_at.isoformat(),
    )


def _create_pending_payment(
    db: Session, user_id: int, provider: str, amount: float, credits: int, transaction_id: str
) -> Payment:
    payment = Payment(
        user_id=user_id,
        provider=provider,
        amount=float(amount),
        currency="EUR",
        status="pending",
        credits_added=int(credits),
        transaction_id=transaction_id,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def _fulfill_payment(db: Session, payment: Payment) -> Payment:
    """Mark a pending payment as succeeded and add credits to the user."""
    if payment.status == "succeeded":
        return payment  # idempotent

    if payment.status in ("cancelled", "failed"):
        # Ein abgebrochener/fehlgeschlagener Auftrag darf nie nachtraeglich
        # Guthaben erzeugen.
        log.error(
            "Refusing to fulfil payment #%s: status=%s", payment.id, payment.status
        )
        raise HTTPException(
            status_code=409, detail=f"Payment #{payment.id} is {payment.status}"
        )

    user = db.query(User).filter(User.id == payment.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found for payment")

    balance = get_user_credits(db, user.id)
    new_balance = round(balance + payment.credits_added, 6)

    db.add(CreditTransaction(
        user_id=user.id,
        amount=float(payment.credits_added),
        balance_after=new_balance,
        reason=f"topup: {payment.provider} payment #{payment.id} ({payment.credits_added} credits)",
    ))
    payment.status = "succeeded"
    db.commit()
    db.refresh(payment)
    log.info(f"Fulfilled payment #{payment.id} for user {user.email}: +{payment.credits_added} credits (balance {new_balance})")
    return payment


# ----------------------------------------------------------------------------
# Public config (so the frontend knows which providers are wired)
# ----------------------------------------------------------------------------
@router.get("/config")
def payments_config(_user: User = Depends(get_current_user)):
    from config import credits_enabled
    billing = credits_enabled()
    return {
        # With credits_enabled: false the packages are returned for information
        # only. The flag is what the UI keys off to hide buy/top-up surfaces, so
        # an older cached frontend also learns the current mode from here.
        "credits_enabled": billing,
        "packages": [
            {
                "id": k,
                "name": v["name"],
                "credits": v["credits"],
                "bonus": v.get("bonus", 0),
                "total_credits": package_total_credits(v),
                "price_eur": v["price_eur"],
            }
            for k, v in CREDIT_PACKAGES.items()
        ],
        "providers": {
            "stripe": {
                "available": bool(STRIPE_SECRET_KEY) and STRIPE_AVAILABLE,
                "publishable_key": STRIPE_PUBLISHABLE_KEY if STRIPE_SECRET_KEY else None,
                "test_cards": {"visa": "4242 4242 4242 4242"},
            },
            "paypal": {
                "available": bool(PAYPAL_CLIENT_ID) and PAYPAL_AVAILABLE,
                "sandbox_buyer": "sb-buyer@example.com",
            },
            "alipay": {
                "available": bool(STRIPE_SECRET_KEY) and STRIPE_AVAILABLE,
                "note": "Routed via Stripe Checkout (Alipay is an automatic payment method).",
            },
            "applepay": {
                "available": bool(STRIPE_SECRET_KEY) and STRIPE_AVAILABLE,
                "note": "Routed via Stripe Payment Request Button (Apple Pay).",
            },
        },
        "mode": "test" if not os.environ.get("PAYMENTS_LIVE") else "live",
    }


# ----------------------------------------------------------------------------
# Provider endpoints - all share the same /{provider}/checkout signature
# ----------------------------------------------------------------------------
def _stripe_checkout(req: CheckoutRequest, user: User, db: Session, request: Optional[Request] = None) -> CheckoutResponse:
    base = public_base_url(request)
    pkg = _get_package(req.package_id)
    total_credits = package_total_credits(pkg)
    txn_id = f"cs_test_{secrets.token_hex(12)}"

    payment = _create_pending_payment(
        db, user.id, "stripe", pkg["price_eur"], total_credits, txn_id
    )

    success_url = req.success_url or f"{base}/payments/stripe/success?payment_id={payment.id}"
    cancel_url = req.cancel_url or f"{base}/payments/stripe/cancel?payment_id={payment.id}"

    if not (STRIPE_SECRET_KEY and STRIPE_AVAILABLE):
        # Mock mode: return a URL the user can hit to simulate success
        return CheckoutResponse(
            payment_id=payment.id,
            provider="stripe",
            status="pending",
            checkout_url=f"{base}/payments/stripe/success?payment_id={payment.id}&mock=1",
            session_id=txn_id,
            mock=True,
            message="Stripe SDK not configured — using mock checkout. Click the URL to simulate success.",
        )

    try:
        session = stripe.checkout.Session.create(  # type: ignore[attr-defined]
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": f"GPU-Pool {pkg['name']} Package",
                        "description": f"{total_credits} credits ({pkg['credits']} + {pkg.get('bonus', 0)} bonus)",
                    },
                    "unit_amount": int(pkg["price_eur"] * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            metadata={"payment_id": str(payment.id), "user_id": str(user.id)},
        )
        payment.transaction_id = session.id
        db.commit()
        return CheckoutResponse(
            payment_id=payment.id,
            provider="stripe",
            status="pending",
            checkout_url=session.url,
            session_id=session.id,
        )
    except Exception as e:
        log.error(f"Stripe checkout failed: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")


def _paypal_checkout(req: CheckoutRequest, user: User, db: Session, request: Optional[Request] = None) -> CheckoutResponse:
    base = public_base_url(request)
    pkg = _get_package(req.package_id)
    total_credits = package_total_credits(pkg)
    txn_id = f"PAYPAL-{secrets.token_hex(8).upper()}"

    payment = _create_pending_payment(
        db, user.id, "paypal", pkg["price_eur"], total_credits, txn_id
    )

    if not (PAYPAL_CLIENT_ID and PAYPAL_AVAILABLE):
        return CheckoutResponse(
            payment_id=payment.id,
            provider="paypal",
            status="pending",
            approval_url=f"{base}/payments/paypal/capture?payment_id={payment.id}&token=mock&mock=1",
            paypal_order_id=txn_id,
            mock=True,
            message="PayPal SDK not configured — using mock checkout. Open the URL to simulate approval.",
        )

    try:
        import paypalrestsdk as pp  # type: ignore
        pp.configure({
            "mode": PAYPAL_MODE,
            "client_id": PAYPAL_CLIENT_ID,
            "client_secret": PAYPAL_CLIENT_SECRET,
        })
        order = pp.Payment({
            "intent": "sale",
            "payer": {"payment_method": "paypal"},
            "redirect_urls": {
                "return_url": f"{base}/payments/paypal/capture?payment_id={payment.id}",
                "cancel_url": f"{base}/payments/paypal/cancel?payment_id={payment.id}",
            },
            "transactions": [{
                "item_list": {
                    "items": [{
                        "name": f"GPU-Pool {pkg['name']}",
                        "sku": req.package_id,
                        "price": f"{pkg['price_eur']:.2f}",
                        "currency": "EUR",
                        "quantity": 1,
                    }]
                },
                "amount": {"total": f"{pkg['price_eur']:.2f}", "currency": "EUR"},
                "description": f"{total_credits} credits for GPU-Pool",
            }],
        })
        if order.create():
            payment.transaction_id = order.id
            db.commit()
            for link in order.links:
                if link.rel == "approval_url":
                    return CheckoutResponse(
                        payment_id=payment.id,
                        provider="paypal",
                        status="pending",
                        approval_url=link.href,
                        paypal_order_id=order.id,
                    )
            raise HTTPException(status_code=502, detail="PayPal did not return approval_url")
        else:
            raise HTTPException(status_code=502, detail=f"PayPal error: {order.error}")
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"PayPal checkout failed: {e}")
        raise HTTPException(status_code=502, detail=f"PayPal error: {e}")


def _alipay_checkout(req: CheckoutRequest, user: User, db: Session, request: Optional[Request] = None) -> CheckoutResponse:
    base = public_base_url(request)
    """Alipay is exposed via Stripe Checkout (Alipay is a Stripe payment_method)."""
    pkg = _get_package(req.package_id)
    total_credits = package_total_credits(pkg)
    txn_id = f"cs_alipay_{secrets.token_hex(10)}"

    payment = _create_pending_payment(
        db, user.id, "alipay", pkg["price_eur"], total_credits, txn_id
    )

    success_url = req.success_url or f"{base}/payments/alipay/success?payment_id={payment.id}"
    cancel_url = req.cancel_url or f"{base}/payments/alipay/cancel?payment_id={payment.id}"

    if not (STRIPE_SECRET_KEY and STRIPE_AVAILABLE):
        return CheckoutResponse(
            payment_id=payment.id,
            provider="alipay",
            status="pending",
            payment_url=f"{base}/payments/alipay/success?payment_id={payment.id}&mock=1",
            mock=True,
            message="Stripe not configured — using mock Alipay flow.",
        )

    try:
        session = stripe.checkout.Session.create(  # type: ignore[attr-defined]
            payment_method_types=["alipay"],
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"GPU-Pool {pkg['name']} (Alipay)"},
                    "unit_amount": int(pkg["price_eur"] * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            metadata={"payment_id": str(payment.id), "user_id": str(user.id), "channel": "alipay"},
        )
        payment.transaction_id = session.id
        db.commit()
        return CheckoutResponse(
            payment_id=payment.id,
            provider="alipay",
            status="pending",
            payment_url=session.url,
            session_id=session.id,
        )
    except Exception as e:
        log.error(f"Alipay (via Stripe) checkout failed: {e}")
        raise HTTPException(status_code=502, detail=f"Alipay/Stripe error: {e}")


def _applepay_checkout(req: CheckoutRequest, user: User, db: Session, request: Optional[Request] = None) -> CheckoutResponse:
    base = public_base_url(request)
    """Apple Pay via Stripe — server returns a PaymentIntent client_secret."""
    pkg = _get_package(req.package_id)
    total_credits = package_total_credits(pkg)
    txn_id = f"pi_applepay_{secrets.token_hex(10)}"

    payment = _create_pending_payment(
        db, user.id, "applepay", pkg["price_eur"], total_credits, txn_id
    )

    if not (STRIPE_SECRET_KEY and STRIPE_AVAILABLE):
        return CheckoutResponse(
            payment_id=payment.id,
            provider="applepay",
            status="pending",
            client_secret=f"pi_mock_{payment.id}_secret_mock",
            mock=True,
            message="Stripe not configured — using mock Apple Pay (no real SDK available server-side).",
        )

    try:
        intent = stripe.PaymentIntent.create(  # type: ignore[attr-defined]
            amount=int(pkg["price_eur"] * 100),
            currency="eur",
            payment_method_types=["card"],  # Apple Pay surfaces as 'card' on Stripe
            metadata={"payment_id": str(payment.id), "user_id": str(user.id), "channel": "applepay"},
            description=f"GPU-Pool {pkg['name']}",
        )
        payment.transaction_id = intent.id
        db.commit()
        return CheckoutResponse(
            payment_id=payment.id,
            provider="applepay",
            status="pending",
            client_secret=intent.client_secret,
        )
    except Exception as e:
        log.error(f"Apple Pay (via Stripe) failed: {e}")
        raise HTTPException(status_code=502, detail=f"Apple Pay/Stripe error: {e}")


_PROVIDER_HANDLERS = {
    "stripe": _stripe_checkout,
    "paypal": _paypal_checkout,
    "alipay": _alipay_checkout,
    "applepay": _applepay_checkout,
}


@router.post("/{provider}/checkout", response_model=CheckoutResponse)
def create_checkout(
    provider: str,
    req: CheckoutRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unified checkout endpoint for every provider.

    The request is passed through so provider return URLs can be derived from the
    host the buyer is actually using (see `public_base_url`).
    """
    handler = _PROVIDER_HANDLERS.get(provider.lower())
    if not handler:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{provider}'. Valid: {list(_PROVIDER_HANDLERS)}",
        )
    # Make sure provider on the request matches the path
    if req.provider.lower() != provider.lower():
        req = req.model_copy(update={"provider": provider.lower()})
    return handler(req, user, db, request)


# ----------------------------------------------------------------------------
# Provider-specific webhook + return endpoints
# ----------------------------------------------------------------------------
@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe webhook receiver. Validates signature if STRIPE_WEBHOOK_SECRET is set.

    Ohne Secret gibt es keine Signaturpruefung — dann wird die Meldung nur noch
    im ausdruecklichen Mock-Modus (PAYMENTS_ALLOW_MOCK=1) angenommen. Frueher
    akzeptierte der Endpunkt in Produktion beliebiges JSON und schrieb Guthaben gut.
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if STRIPE_WEBHOOK_SECRET:
        if not STRIPE_AVAILABLE:
            log.error("Stripe webhook rejected: STRIPE_WEBHOOK_SECRET gesetzt, aber SDK fehlt")
            raise HTTPException(
                status_code=503, detail="Stripe SDK missing, cannot verify webhook signature"
            )
        try:
            event = stripe.Webhook.construct_event(  # type: ignore[attr-defined]
                payload, sig, STRIPE_WEBHOOK_SECRET
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")
    elif mock_payments_allowed():
        # Entwicklungsmodus: ungeprueftes JSON, nur mit PAYMENTS_ALLOW_MOCK=1
        log.warning("Stripe webhook im Mock-Modus angenommen (keine Signaturpruefung)")
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
    else:
        log.error("Stripe webhook rejected: STRIPE_WEBHOOK_SECRET nicht gesetzt und PAYMENTS_ALLOW_MOCK=0")
        raise HTTPException(status_code=503, detail="Stripe webhook not configured")

    etype = event.get("type") if isinstance(event, dict) else event.type
    data = event.get("data", {}).get("object", {}) if isinstance(event, dict) else event.data.object

    if etype in ("checkout.session.completed", "payment_intent.succeeded"):
        metadata = data.get("metadata", {}) or {}
        payment_id = metadata.get("payment_id")
        if payment_id:
            payment = db.query(Payment).filter(Payment.id == int(payment_id)).first()
            if payment:
                _fulfill_payment(db, payment)
                return {"received": True, "payment_id": payment.id, "status": "succeeded"}
    return {"received": True, "handled": False, "type": etype}


@router.get("/stripe/success")
async def stripe_success(
    payment_id: int,
    session_id: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stripe Checkout return URL (after user is redirected back).

    Reiner Browser-Redirect: die Zahlung wird deshalb aktiv bei Stripe
    nachgefragt, bevor Guthaben entsteht.
    """
    payment = db.query(Payment).filter(
        Payment.id == payment_id, Payment.user_id == user.id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "succeeded":
        await _confirm_stripe_payment(payment, session_id=session_id)
        _fulfill_payment(db, payment)
    return {"status": "succeeded", "payment": _serialize_payment(payment).model_dump()}


@router.get("/stripe/cancel")
def stripe_cancel(
    payment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payment = db.query(Payment).filter(
        Payment.id == payment_id, Payment.user_id == user.id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    payment.status = "cancelled"
    db.commit()
    return {"status": "cancelled", "payment": _serialize_payment(payment).model_dump()}


@router.post("/stripe/simulate-success")
def stripe_simulate_success(
    payment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dev/test helper: pretend Stripe sent us a successful webhook.

    Nur mit PAYMENTS_ALLOW_MOCK=1. In Produktion bewusst 404, damit der
    Endpunkt nicht einmal als vorhanden erkennbar ist.
    """
    if not mock_payments_allowed():
        raise HTTPException(status_code=404, detail="Not found")
    payment = db.query(Payment).filter(
        Payment.id == payment_id, Payment.user_id == user.id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    _fulfill_payment(db, payment)
    return _serialize_payment(payment)


@router.get("/paypal/capture")
def paypal_capture(
    payment_id: int,
    token: Optional[str] = None,
    PayerID: Optional[str] = None,
    mock: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return URL after user approved the PayPal order."""
    payment = db.query(Payment).filter(
        Payment.id == payment_id, Payment.user_id == user.id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == "succeeded":
        return {"status": "already_succeeded", "payment": _serialize_payment(payment).model_dump()}

    if PAYPAL_CLIENT_ID and PAYPAL_AVAILABLE and not mock:
        try:
            import paypalrestsdk as pp  # type: ignore
            pp.configure({
                "mode": PAYPAL_MODE,
                "client_id": PAYPAL_CLIENT_ID,
                "client_secret": PAYPAL_CLIENT_SECRET,
            })
            order = pp.Payment.find(payment.transaction_id)
            if order.execute({"payer_id": PayerID}):
                _fulfill_payment(db, payment)
            else:
                raise HTTPException(status_code=402, detail=f"PayPal execute failed: {order.error}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"PayPal capture error: {e}")
    else:
        # Mock-Pfad: frueher der Weg zu kostenlosem Guthaben. Jetzt nur mit
        # PAYMENTS_ALLOW_MOCK=1 (Entwicklung). Der Parameter ?mock=1 kann den
        # echten Pfad nicht mehr erzwingen, wenn Zugangsdaten gesetzt sind.
        if not mock_payments_allowed():
            log.error(
                "PayPal capture (mock) refused for payment #%s: PayPal not configured "
                "and PAYMENTS_ALLOW_MOCK=0", payment.id,
            )
            raise HTTPException(status_code=503, detail="PayPal is not configured")
        _fulfill_payment(db, payment)

    return {"status": "succeeded", "payment": _serialize_payment(payment).model_dump()}


@router.post("/paypal/ipn")
async def paypal_ipn(request: Request, db: Session = Depends(get_db)):
    """PayPal Instant Payment Notification (IPN) webhook.

    Reihenfolge (PayPal-Dokumentation):
      1. Rohtext der Meldung unveraendert an PayPal zurueckschicken
         (+ cmd=_notify-validate). Nur "VERIFIED" wird akzeptiert.
      2. payment_status muss "Completed" sein.
      3. Empfaengerkonto und Betrag/Waehrung muessen zum Auftrag passen.
      4. txn_id darf nur einmal gutschreiben (Idempotenz, DB-Unique).
    Ohne bestandene Pruefung: HTTP 400, kein Guthaben.
    """
    raw = await request.body()
    form = dict(parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True))

    # 1. Beim Anbieter verifizieren — der einzige Schritt, der die Meldung
    #    ueberhaupt glaubwuerdig macht.
    if not await _paypal_verify_ipn(raw):
        raise HTTPException(status_code=400, detail="IPN verification failed")

    log.info(
        "PayPal IPN verified: txn_id=%s txn_type=%s payment_status=%s",
        form.get("txn_id"), form.get("txn_type"), form.get("payment_status"),
    )

    # 2. Nur abgeschlossene Zahlungen.
    if form.get("payment_status") != "Completed":
        return {"ok": True, "handled": False, "payment_status": form.get("payment_status")}

    # 3a. Empfaengerkonto.
    expected = _expected_receiver()
    actual = (form.get("receiver_email") or form.get("business") or "").strip().lower()
    if expected:
        if actual != expected:
            log.error("PayPal IPN rejected: Empfaenger %r != erwartet %r", actual, expected)
            raise HTTPException(status_code=400, detail="IPN receiver mismatch")
    elif _paypal_mode() == "live":
        log.error("PayPal IPN rejected: PAYPAL_RECEIVER_EMAIL ist im Livebetrieb nicht gesetzt")
        raise HTTPException(status_code=400, detail="IPN receiver not configured")

    # 3b. Zuordnung zum Auftrag.
    custom = form.get("custom") or ""
    if not custom.startswith("payment_id:"):
        log.warning("PayPal IPN ohne payment_id im custom-Feld: %r", custom)
        raise HTTPException(status_code=400, detail="IPN not bound to a payment")
    try:
        pid = int(custom.split(":", 1)[1])
    except ValueError:
        raise HTTPException(status_code=400, detail="IPN custom field malformed")

    payment = db.query(Payment).filter(
        Payment.id == pid, Payment.provider == "paypal"
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # 3c. Betrag und Waehrung.
    try:
        gross = float(form.get("mc_gross") or "")
    except ValueError:
        raise HTTPException(status_code=400, detail="IPN without mc_gross")
    currency = (form.get("mc_currency") or "").strip().upper()
    expected_currency = (payment.currency or "EUR").upper()
    if abs(gross - float(payment.amount)) > 0.01 or currency != expected_currency:
        log.error(
            "PayPal IPN Betrag passt nicht: %s %s != %s %s (payment #%s)",
            gross, currency, payment.amount, expected_currency, payment.id,
        )
        raise HTTPException(status_code=400, detail="IPN amount mismatch")

    # 4. Idempotenz: dieselbe txn_id nie zweimal gutschreiben.
    txn_id = (form.get("txn_id") or "").strip()
    if not txn_id:
        raise HTTPException(status_code=400, detail="IPN without txn_id")

    if payment.provider_event_id == txn_id and payment.status == "succeeded":
        return {"ok": True, "payment_id": payment.id, "status": "already_succeeded"}

    already = db.query(Payment).filter(
        Payment.provider_event_id == txn_id, Payment.id != payment.id
    ).first()
    if already:
        log.error(
            "PayPal IPN replay rejected: txn_id %s gehoert bereits zu payment #%s",
            txn_id, already.id,
        )
        raise HTTPException(status_code=400, detail="IPN already processed")

    payment.provider_event_id = txn_id
    _fulfill_payment(db, payment)
    return {"ok": True, "payment_id": payment.id, "status": "succeeded"}


@router.get("/alipay/success")
async def alipay_success(
    payment_id: int,
    session_id: Optional[str] = None,
    mock: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alipay laeuft ueber Stripe Checkout — die Session wird bei Stripe geprueft."""
    payment = db.query(Payment).filter(
        Payment.id == payment_id, Payment.user_id == user.id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "succeeded":
        await _confirm_stripe_payment(payment, session_id=session_id)
        _fulfill_payment(db, payment)
    return {"status": "succeeded", "payment": _serialize_payment(payment).model_dump()}


@router.get("/applepay/success")
async def applepay_success(
    payment_id: int,
    payment_intent: Optional[str] = None,
    payment_intent_client_secret: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apple Pay laeuft ueber Stripe — das PaymentIntent wird bei Stripe geprueft."""
    payment = db.query(Payment).filter(
        Payment.id == payment_id, Payment.user_id == user.id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "succeeded":
        await _confirm_stripe_payment(payment, payment_intent=payment_intent)
        _fulfill_payment(db, payment)
    return {"status": "succeeded", "payment": _serialize_payment(payment).model_dump()}


# ----------------------------------------------------------------------------
# History + lookups
# ----------------------------------------------------------------------------
@router.get("/history", response_model=List[PaymentInfo])
def payment_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(Payment).filter(Payment.user_id == user.id).order_by(Payment.id.desc()).all()
    return [_serialize_payment(p) for p in rows]


@router.get("/{payment_id}", response_model=PaymentInfo)
def get_payment(
    payment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.query(Payment).filter(
        Payment.id == payment_id, Payment.user_id == user.id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    return _serialize_payment(p)
