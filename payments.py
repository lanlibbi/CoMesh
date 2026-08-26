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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "http://100.126.79.111:8765")

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
    return {
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
def _stripe_checkout(req: CheckoutRequest, user: User, db: Session) -> CheckoutResponse:
    pkg = _get_package(req.package_id)
    total_credits = package_total_credits(pkg)
    txn_id = f"cs_test_{secrets.token_hex(12)}"

    payment = _create_pending_payment(
        db, user.id, "stripe", pkg["price_eur"], total_credits, txn_id
    )

    success_url = req.success_url or f"{APP_PUBLIC_URL}/payments/stripe/success?payment_id={payment.id}"
    cancel_url = req.cancel_url or f"{APP_PUBLIC_URL}/payments/stripe/cancel?payment_id={payment.id}"

    if not (STRIPE_SECRET_KEY and STRIPE_AVAILABLE):
        # Mock mode: return a URL the user can hit to simulate success
        return CheckoutResponse(
            payment_id=payment.id,
            provider="stripe",
            status="pending",
            checkout_url=f"{APP_PUBLIC_URL}/payments/stripe/success?payment_id={payment.id}&mock=1",
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


def _paypal_checkout(req: CheckoutRequest, user: User, db: Session) -> CheckoutResponse:
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
            approval_url=f"{APP_PUBLIC_URL}/payments/paypal/capture?payment_id={payment.id}&token=mock&mock=1",
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
                "return_url": f"{APP_PUBLIC_URL}/payments/paypal/capture?payment_id={payment.id}",
                "cancel_url": f"{APP_PUBLIC_URL}/payments/paypal/cancel?payment_id={payment.id}",
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


def _alipay_checkout(req: CheckoutRequest, user: User, db: Session) -> CheckoutResponse:
    """Alipay is exposed via Stripe Checkout (Alipay is a Stripe payment_method)."""
    pkg = _get_package(req.package_id)
    total_credits = package_total_credits(pkg)
    txn_id = f"cs_alipay_{secrets.token_hex(10)}"

    payment = _create_pending_payment(
        db, user.id, "alipay", pkg["price_eur"], total_credits, txn_id
    )

    success_url = req.success_url or f"{APP_PUBLIC_URL}/payments/alipay/success?payment_id={payment.id}"
    cancel_url = req.cancel_url or f"{APP_PUBLIC_URL}/payments/alipay/cancel?payment_id={payment.id}"

    if not (STRIPE_SECRET_KEY and STRIPE_AVAILABLE):
        return CheckoutResponse(
            payment_id=payment.id,
            provider="alipay",
            status="pending",
            payment_url=f"{APP_PUBLIC_URL}/payments/alipay/success?payment_id={payment.id}&mock=1",
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


def _applepay_checkout(req: CheckoutRequest, user: User, db: Session) -> CheckoutResponse:
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unified checkout endpoint for every provider."""
    handler = _PROVIDER_HANDLERS.get(provider.lower())
    if not handler:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{provider}'. Valid: {list(_PROVIDER_HANDLERS)}",
        )
    # Make sure provider on the request matches the path
    if req.provider.lower() != provider.lower():
        req = req.model_copy(update={"provider": provider.lower()})
    return handler(req, user, db)


# ----------------------------------------------------------------------------
# Provider-specific webhook + return endpoints
# ----------------------------------------------------------------------------
@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe webhook receiver. Validates signature if STRIPE_WEBHOOK_SECRET is set.
    Events handled: checkout.session.completed, payment_intent.succeeded
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if STRIPE_WEBHOOK_SECRET and STRIPE_AVAILABLE:
        try:
            event = stripe.Webhook.construct_event(  # type: ignore[attr-defined]
                payload, sig, STRIPE_WEBHOOK_SECRET
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")
    else:
        # Mock mode: accept JSON payload directly
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

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
def stripe_success(
    payment_id: int,
    session_id: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stripe Checkout return URL (after user is redirected back)."""
    payment = db.query(Payment).filter(
        Payment.id == payment_id, Payment.user_id == user.id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "succeeded":
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
    """Dev/test helper: pretend Stripe sent us a successful webhook."""
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
        # Mock path
        _fulfill_payment(db, payment)

    return {"status": "succeeded", "payment": _serialize_payment(payment).model_dump()}


@router.post("/paypal/ipn")
async def paypal_ipn(request: Request, db: Session = Depends(get_db)):
    """PayPal Instant Payment Notification (IPN) webhook."""
    form = dict(await request.form())
    log.info(f"PayPal IPN received: {form.get('txn_type')} payment_status={form.get('payment_status')}")
    if form.get("payment_status") == "Completed":
        custom = form.get("custom") or ""
        # Expecting "payment_id:<id>" in custom
        if custom.startswith("payment_id:"):
            try:
                pid = int(custom.split(":", 1)[1])
                payment = db.query(Payment).filter(Payment.id == pid).first()
                if payment:
                    _fulfill_payment(db, payment)
            except Exception as e:
                log.warning(f"Bad IPN custom field: {custom} ({e})")
    return {"ok": True}


@router.get("/alipay/success")
def alipay_success(
    payment_id: int,
    session_id: Optional[str] = None,
    mock: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payment = db.query(Payment).filter(
        Payment.id == payment_id, Payment.user_id == user.id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "succeeded":
        _fulfill_payment(db, payment)
    return {"status": "succeeded", "payment": _serialize_payment(payment).model_dump()}


@router.get("/applepay/success")
def applepay_success(
    payment_id: int,
    payment_intent: Optional[str] = None,
    payment_intent_client_secret: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payment = db.query(Payment).filter(
        Payment.id == payment_id, Payment.user_id == user.id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "succeeded":
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
