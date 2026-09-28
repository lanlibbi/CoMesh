"""
Usage analytics.

Aggregates the `usages` table (one row per /v1/chat/completions call) into the
shapes the dashboard needs:

  * GET /v1/me/usage     -> per-user totals, per-model breakdown, time series
                            and the most recent requests (see `router` below).
  * GET /admin/usage      -> company-wide per-user view (role-gated route lives
                            in admin.py and calls `build_admin_usage`).

Everything is a SQL GROUP BY, so the aggregation cost is paid by SQLite and not
by the API process. Two indexes keep it flat as the table grows
(`ensure_usage_indexes()` is idempotent and runs on startup).

Time handling: `Usage.created_at` is a naive UTC datetime (SQLAlchemy's
`datetime.utcnow` default), so every window boundary is computed from
`datetime.utcnow()` as well. Never mix in local time here.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import get_current_user
from database import engine, get_db
from models import PoolJob, Usage, User

log = logging.getLogger("gpu-pool")

# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------
# key -> (label, delta from now, bucket granularity). `None` delta = all time.
WINDOWS: Dict[str, Tuple[str, Optional[timedelta], str]] = {
    "24h": ("Letzte 24 Stunden", timedelta(hours=24), "hour"),
    "7d": ("Letzte 7 Tage", timedelta(days=7), "day"),
    "30d": ("Letzte 30 Tage", timedelta(days=30), "day"),
    "all": ("Gesamt", None, "day"),
}

# Lenient aliases so a hand-written curl does not need the exact key.
WINDOW_ALIASES = {
    "24h": "24h", "1d": "24h", "hour": "24h", "heute": "24h", "day": "24h",
    "7d": "7d", "week": "7d", "woche": "7d",
    "30d": "30d", "month": "30d", "monat": "30d",
    "all": "all", "gesamt": "all", "total": "all",
}

MAX_BUCKETS = 90          # bounded series length for window=all
DEFAULT_RECENT_LIMIT = 20
MAX_RECENT_LIMIT = 100


def resolve_window(raw: Optional[str]) -> str:
    """Map a caller-supplied window string to a canonical key (422 when unknown)."""
    key = (raw or "7d").strip().lower()
    resolved = WINDOW_ALIASES.get(key)
    if resolved is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown window '{raw}'. Use one of: {', '.join(sorted(WINDOWS))} "
                f"(aliases: {', '.join(sorted(set(WINDOW_ALIASES) - set(WINDOWS)))})"
            ),
        )
    return resolved


def window_start(window: str) -> Optional[datetime]:
    """UTC lower bound for a canonical window key, or None for all time."""
    delta = WINDOWS[window][1]
    if delta is None:
        return None
    return datetime.utcnow() - delta


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
class UsageModelOut(BaseModel):
    model: str
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    credits: float = 0.0
    share: float = 0.0                      # fraction of total_tokens in the window
    avg_latency_ms: Optional[int] = None
    first_seen: Optional[str] = None
    last_used: Optional[str] = None


class UsageTotalsOut(BaseModel):
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    credits: float = 0.0
    avg_latency_ms: Optional[int] = None
    models_used: int = 0


class UsageBucketOut(BaseModel):
    bucket: str                             # "2026-09-28" (day) or "2026-09-28T14" (hour)
    label: str                              # short German label for the chart
    requests: int = 0
    total_tokens: int = 0
    credits: float = 0.0


class UsageRecentOut(BaseModel):
    id: int
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    credits: float = 0.0
    created_at: str


class UsageSummaryOut(BaseModel):
    window: str
    window_label: str
    granularity: str                        # "hour" | "day"
    since: Optional[str] = None
    until: str
    generated_at: str
    totals: UsageTotalsOut
    models: List[UsageModelOut] = []
    series: List[UsageBucketOut] = []
    recent: List[UsageRecentOut] = []


class AdminUsageUserOut(BaseModel):
    user_id: int
    email: str
    name: Optional[str] = None
    role: str = "both"
    is_active: bool = True
    requests: int = 0
    total_tokens: int = 0
    credits: float = 0.0
    models_used: int = 0
    last_used: Optional[str] = None
    models: List[UsageModelOut] = []


class AdminUsageTotalsOut(BaseModel):
    requests: int = 0
    total_tokens: int = 0
    credits: float = 0.0
    active_users: int = 0
    models_used: int = 0


class AdminUsageOut(BaseModel):
    window: str
    window_label: str
    since: Optional[str] = None
    until: str
    generated_at: str
    totals: AdminUsageTotalsOut
    users: List[AdminUsageUserOut] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def _bucket_expr(granularity: str):
    """SQLite strftime format for the series buckets."""
    return func.strftime("%Y-%m-%dT%H" if granularity == "hour" else "%Y-%m-%d", Usage.created_at)


def _floor(dt: datetime, granularity: str) -> datetime:
    if granularity == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _step(granularity: str) -> timedelta:
    return timedelta(hours=1) if granularity == "hour" else timedelta(days=1)


def _bucket_key(dt: datetime, granularity: str) -> str:
    return dt.strftime("%Y-%m-%dT%H" if granularity == "hour" else "%Y-%m-%d")


def _bucket_label(dt: datetime, granularity: str) -> str:
    return dt.strftime("%d.%m. %H:00" if granularity == "hour" else "%d.%m.")


def _build_series(
    rows: List[Tuple[str, int, int, float]],
    since: Optional[datetime],
    granularity: str,
    until: datetime,
) -> List[UsageBucketOut]:
    """
    Turn grouped rows into a gap-filled series so the chart has a stable width.

    For window=all the series is clamped to the most recent MAX_BUCKETS buckets.
    """
    by_key = {r[0]: r for r in rows if r[0]}

    # Anchor: the window start, or the first observed bucket for all-time.
    if since is not None:
        start = _floor(since, granularity)
    else:
        if not by_key:
            return []
        start = _floor(min(datetime.strptime(k, "%Y-%m-%dT%H" if granularity == "hour" else "%Y-%m-%d")
                           for k in by_key), granularity)

    step = _step(granularity)
    last = _floor(until, granularity)

    # Clamp to the most recent MAX_BUCKETS buckets (all-time can span months).
    span = int((last - start) / step) + 1
    if span > MAX_BUCKETS:
        start = last - step * (MAX_BUCKETS - 1)

    out: List[UsageBucketOut] = []
    cursor = start
    while cursor <= last:
        key = _bucket_key(cursor, granularity)
        row = by_key.get(key)
        out.append(UsageBucketOut(
            bucket=key,
            label=_bucket_label(cursor, granularity),
            requests=int(row[1]) if row else 0,
            total_tokens=int(row[2]) if row else 0,
            credits=round(float(row[3] or 0.0), 6) if row else 0.0,
        ))
        cursor += step
    return out


def _latency_by_model(db: Session, since: Optional[datetime], user_id: Optional[int] = None) -> Tuple[Dict[str, int], Optional[int]]:
    """
    Average latency per model from `pool_jobs` (the only place latency is stored).

    Usage rows and pool_jobs are written in the same request but there is no FK
    between them, so they are joined on (user, model, window) instead. Requests
    that never reached a node (routing failures) have no latency and are absent
    from both sides of this average.
    """
    q = db.query(
        PoolJob.model,
        func.avg(PoolJob.latency_ms),
        func.count(PoolJob.id),
    ).filter(PoolJob.latency_ms > 0, PoolJob.status == "succeeded")
    if user_id is not None:
        q = q.filter(PoolJob.user_id == user_id)
    if since is not None:
        q = q.filter(PoolJob.finished_at >= since)

    per_model: Dict[str, int] = {}
    weighted = 0.0
    counted = 0
    for model, avg_ms, n in q.group_by(PoolJob.model).all():
        if model is None or not n:
            continue
        per_model[model] = int(round(float(avg_ms or 0)))
        weighted += float(avg_ms or 0) * int(n)
        counted += int(n)
    overall = int(round(weighted / counted)) if counted else None
    return per_model, overall


def _model_rows(db: Session, since: Optional[datetime], user_id: Optional[int] = None):
    """GROUP BY model over usages for one user (or all users when user_id is None)."""
    q = db.query(
        Usage.model,
        func.count(Usage.id),
        func.coalesce(func.sum(Usage.prompt_tokens), 0),
        func.coalesce(func.sum(Usage.completion_tokens), 0),
        func.coalesce(func.sum(Usage.total_tokens), 0),
        func.coalesce(func.sum(Usage.credits_charged), 0.0),
        func.min(Usage.created_at),
        func.max(Usage.created_at),
    )
    if user_id is not None:
        q = q.filter(Usage.user_id == user_id)
    if since is not None:
        q = q.filter(Usage.created_at >= since)
    return q.group_by(Usage.model).all()


def _model_out(rows, latency: Dict[str, int], total_tokens_window: int) -> List[UsageModelOut]:
    models: List[UsageModelOut] = []
    for model, requests, p_tok, c_tok, t_tok, credits, first_seen, last_used in rows:
        t_tok = int(t_tok or 0)
        models.append(UsageModelOut(
            model=model or "unknown",
            requests=int(requests or 0),
            prompt_tokens=int(p_tok or 0),
            completion_tokens=int(c_tok or 0),
            total_tokens=t_tok,
            credits=round(float(credits or 0.0), 6),
            share=round(t_tok / total_tokens_window, 6) if total_tokens_window else 0.0,
            avg_latency_ms=latency.get(model),
            first_seen=_iso(first_seen),
            last_used=_iso(last_used),
        ))
    # Heaviest first — the dashboard bar list is read top-down.
    models.sort(key=lambda m: (m.total_tokens, m.requests), reverse=True)
    return models


def _series_rows(db: Session, since: Optional[datetime], granularity: str, user_id: Optional[int] = None):
    q = db.query(
        _bucket_expr(granularity),
        func.count(Usage.id),
        func.coalesce(func.sum(Usage.total_tokens), 0),
        func.coalesce(func.sum(Usage.credits_charged), 0.0),
    )
    if user_id is not None:
        q = q.filter(Usage.user_id == user_id)
    if since is not None:
        q = q.filter(Usage.created_at >= since)
    return q.group_by(_bucket_expr(granularity)).order_by(_bucket_expr(granularity)).all()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/v1/me", tags=["usage"])


@router.get("/usage", response_model=UsageSummaryOut)
def my_usage(
    window: str = Query("7d", description="24h | 7d | 30d | all"),
    recent_limit: int = Query(DEFAULT_RECENT_LIMIT, ge=0, le=MAX_RECENT_LIMIT),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Token and credit usage of the calling user, aggregated per model."""
    key = resolve_window(window)
    label, _delta, granularity = WINDOWS[key]
    since = window_start(key)
    now = datetime.utcnow()

    rows = _model_rows(db, since, user_id=user.id)
    totals_tokens = sum(int(r[4] or 0) for r in rows)
    latency, overall_latency = _latency_by_model(db, since, user_id=user.id)
    models = _model_out(rows, latency, totals_tokens)

    series = _build_series(_series_rows(db, since, granularity, user_id=user.id), since, granularity, now)

    recent_q = db.query(Usage).filter(Usage.user_id == user.id)
    if since is not None:
        recent_q = recent_q.filter(Usage.created_at >= since)
    recent = [
        UsageRecentOut(
            id=u.id,
            model=u.model,
            prompt_tokens=int(u.prompt_tokens or 0),
            completion_tokens=int(u.completion_tokens or 0),
            total_tokens=int(u.total_tokens or 0),
            credits=round(float(u.credits_charged or 0.0), 6),
            created_at=_iso(u.created_at) or "",
        )
        for u in recent_q.order_by(Usage.created_at.desc(), Usage.id.desc()).limit(recent_limit).all()
    ]

    return UsageSummaryOut(
        window=key,
        window_label=label,
        granularity=granularity,
        since=_iso(since),
        until=now.isoformat(),
        generated_at=now.isoformat(),
        totals=UsageTotalsOut(
            requests=sum(m.requests for m in models),
            prompt_tokens=sum(m.prompt_tokens for m in models),
            completion_tokens=sum(m.completion_tokens for m in models),
            total_tokens=totals_tokens,
            credits=round(sum(m.credits for m in models), 6),
            avg_latency_ms=overall_latency,
            models_used=len(models),
        ),
        models=models,
        series=series,
        recent=recent,
    )


def build_admin_usage(
    db: Session,
    window: str = "7d",
    limit: int = 50,
    include_inactive: bool = True,
) -> AdminUsageOut:
    """Company-wide usage per user. Called by the role-gated /admin/usage route."""
    key = resolve_window(window)
    label, _delta, _granularity = WINDOWS[key]
    # The admin view has no series endpoint, so it always buckets by day.
    since = window_start(key)
    now = datetime.utcnow()

    per_user_latency: Dict[int, Dict[str, int]] = {}

    # Per (user, model) aggregation: one query, grouped twice in Python.
    q = db.query(
        Usage.user_id,
        Usage.model,
        func.count(Usage.id),
        func.coalesce(func.sum(Usage.prompt_tokens), 0),
        func.coalesce(func.sum(Usage.completion_tokens), 0),
        func.coalesce(func.sum(Usage.total_tokens), 0),
        func.coalesce(func.sum(Usage.credits_charged), 0.0),
        func.min(Usage.created_at),
        func.max(Usage.created_at),
    ).filter(Usage.user_id.isnot(None))
    if since is not None:
        q = q.filter(Usage.created_at >= since)
    q = q.group_by(Usage.user_id, Usage.model)

    grouped: Dict[int, List] = {}
    for row in q.all():
        grouped.setdefault(int(row[0]), []).append(row[1:])

    users: List[AdminUsageUserOut] = []
    if grouped:
        user_rows = db.query(User).filter(User.id.in_(list(grouped.keys()))).all()
        for u in user_rows:
            if not include_inactive and not u.is_active:
                continue
            model_rows = grouped.get(u.id, [])
            # row shape here is (model, count, prompt, completion, total, credits, min, max)
            user_tokens = sum(int(r[4] or 0) for r in model_rows)
            per_user_latency[u.id] = _latency_by_model(db, since, user_id=u.id)[0]
            models = _model_out(model_rows, per_user_latency[u.id], user_tokens)
            users.append(AdminUsageUserOut(
                user_id=u.id,
                email=u.email,
                name=u.name,
                role=getattr(u, "role", "both") or "both",
                is_active=bool(u.is_active),
                requests=sum(m.requests for m in models),
                total_tokens=user_tokens,
                credits=round(sum(m.credits for m in models), 6),
                models_used=len(models),
                last_used=max((m.last_used for m in models if m.last_used), default=None),
                models=models,
            ))

    users.sort(key=lambda u: u.total_tokens, reverse=True)
    users = users[:limit]

    return AdminUsageOut(
        window=key,
        window_label=label,
        since=_iso(since),
        until=now.isoformat(),
        generated_at=now.isoformat(),
        totals=AdminUsageTotalsOut(
            requests=sum(u.requests for u in users),
            total_tokens=sum(u.total_tokens for u in users),
            credits=round(sum(u.credits for u in users), 6),
            active_users=sum(1 for u in users if u.requests > 0),
            models_used=len({m.model for u in users for m in u.models}),
        ),
        users=users,
    )


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
def ensure_usage_indexes():
    """
    Add the indexes the aggregation queries rely on (idempotent).

    Without these, every dashboard load is a full scan of `usages` — fine for a
    few thousand rows, visibly slow past ~100k. The composite (user_id,
    created_at) covers the per-user window filter; the model index covers the
    GROUP BY on the admin path.
    """
    try:
        with engine.begin() as conn:
            existing = {row[1] for row in conn.exec_driver_sql("PRAGMA index_list(usages)").fetchall()}
            if "ix_usages_user_created" not in existing:
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_usages_user_created ON usages (user_id, created_at)"
                )
                log.info("Added index ix_usages_user_created on usages(user_id, created_at)")
            if "ix_usages_model" not in existing:
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_usages_model ON usages (model)")
                log.info("Added index ix_usages_model on usages(model)")
    except Exception as e:  # pragma: no cover - non-fatal, endpoint still works
        log.warning(f"Could not ensure usage indexes: {e}")
