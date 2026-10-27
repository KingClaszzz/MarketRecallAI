import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import desc, func, select

from app.config import get_settings
from app.data.collector import collect_hour
from app.db import (
    Candle, Forecast, IntegrationLog, Lesson, MarketSnapshot, MemoryRef, OnchainSnapshot,
    get_session, init_db,
)
from app.db import CreditEntry, Pick, PredictSession, User
from app.live import engine
from app.agent import guide
from app.security import RateLimit, client_ip
from app.users import auth, credits, picks, sessions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("marketrecall")

SERVICES = ["tatum_ohlcv", "tatum_grpc", "binance", "coingecko", "walrus", "llm"]
WALRUS_AGGREGATOR = "https://aggregator.walrus-mainnet.walrus.space/v1/blobs/"


async def run_hour() -> dict:
    collected = await asyncio.to_thread(collect_hour)
    cycle = await asyncio.to_thread(engine.hourly_cycle)
    log.info("hour: collected=%s cycle=%s", collected, cycle)
    return {"collected": collected, "cycle": cycle}


async def run_day() -> dict:
    result = await asyncio.to_thread(engine.daily_cycle)
    log.info("day: %s", result)
    return result


JOBS = {"hour": run_hour, "day": run_day}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    missing = [a for a in get_settings().assets if engine.latest_policy_state(a) is None]
    if missing:
        log.warning("no learned policy state for %s: run backend/scripts/bootstrap.py (Recall stays at baseline)", missing)
    scheduler = None
    if get_settings().scheduler_enabled:
        scheduler = AsyncIOScheduler(timezone="UTC")
        # 30s past the hour so the just-closed candle is available upstream.
        scheduler.add_job(run_hour, "cron", minute=0, second=30, id="hour", coalesce=True, max_instances=1)
        scheduler.add_job(run_day, "cron", hour=0, minute=10, id="day", coalesce=True, max_instances=1)
        scheduler.start()
        asyncio.create_task(run_hour())
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


_docs = get_settings().expose_docs
app = FastAPI(title="MarketRecall AI", lifespan=lifespan, docs_url="/docs" if _docs else None,
              redoc_url=None, openapi_url="/openapi.json" if _docs else None)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type"], max_age=600)

MAX_BODY = 32 * 1024
PRIVATE_PATHS = ("/api/me", "/api/sessions", "/api/auth")


@app.middleware("http")
async def harden(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_BODY):
        return JSONResponse({"detail": "request too large"}, status_code=413)
    if "chunked" in request.headers.get("transfer-encoding", "").lower():
        return JSONResponse({"detail": "length required"}, status_code=411)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Cross-Origin-Resource-Policy"] = "same-site"
    if request.url.path.startswith(PRIVATE_PATHS):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health() -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    services = {}
    with get_session() as session:
        for name in SERVICES:
            last = session.exec(
                select(IntegrationLog).where(IntegrationLog.service == name).order_by(desc(IntegrationLog.ts)).limit(1)
            ).first()
            recent = session.exec(
                select(IntegrationLog).where(IntegrationLog.service == name, IntegrationLog.ts >= since)
            ).all()
            services[name] = {
                "last_ok": last.ok if last else None,
                "last_ts": last.ts.isoformat() if last else None,
                "last_error": last.error.split(":", 1)[0] if last and not last.ok and last.error else None,
                "calls_24h": len(recent),
                "errors_24h": sum(not r.ok for r in recent),
            }
    return {"status": "ok", "services": services}


@app.get("/api/assets")
def assets() -> list[str]:
    return get_settings().assets


def _asset(asset: str) -> str:
    asset = asset.upper()
    if asset not in get_settings().assets:
        raise HTTPException(status_code=404, detail=f"unknown asset {asset}")
    return asset


@app.get("/api/candles")
def candles(asset: str = "SUI", limit: int = Query(168, ge=1, le=5000),
            source: str = Query("merged", pattern="^(merged|tatum|binance)$")) -> list[Candle]:
    """Newest `limit` hourly candles. `merged` prefers Tatum and fills older hours from Binance."""
    asset = _asset(asset)
    sources = ["tatum", "binance"] if source == "merged" else [source]
    by_time: dict[int, Candle] = {}
    with get_session() as session:
        for src in sources:
            rows = session.exec(
                select(Candle).where(Candle.source == src, Candle.symbol == asset)
                .order_by(desc(Candle.open_time)).limit(limit)
            ).all()
            for row in rows:
                by_time.setdefault(row.open_time, row)
    return [by_time[t] for t in sorted(by_time)[-limit:]]


@app.get("/api/onchain")
def onchain_snapshots(limit: int = Query(168, ge=1, le=5000)) -> list[OnchainSnapshot]:
    with get_session() as session:
        rows = session.exec(select(OnchainSnapshot).order_by(desc(OnchainSnapshot.hour_ts)).limit(limit)).all()
    return list(reversed(rows))


@app.get("/api/market")
def market_overview() -> MarketSnapshot | None:
    with get_session() as session:
        return session.exec(select(MarketSnapshot).order_by(desc(MarketSnapshot.ts)).limit(1)).first()


@app.get("/api/live")
def live() -> dict:
    out = {}
    with get_session() as session:
        for asset in get_settings().assets:
            out[asset] = session.exec(
                select(Forecast).where(Forecast.asset == asset, Forecast.source == "live").order_by(desc(Forecast.t)).limit(1)
            ).first()
    return {"forecasts": out, "rules": {a: engine.lesson_status(a) for a in get_settings().assets}}


@app.get("/api/forecasts")
def forecasts(asset: str | None = None, limit: int = Query(200, ge=1, le=2000),
              status: str | None = Query(None, max_length=20)) -> list[Forecast]:
    query = select(Forecast).where(Forecast.source == "live")
    if asset:
        query = query.where(Forecast.asset == _asset(asset))
    if status:
        query = query.where(Forecast.status == status)
    with get_session() as session:
        return session.exec(query.order_by(desc(Forecast.t)).limit(limit)).all()


@app.get("/api/forecasts/{forecast_id}")
def forecast_detail(forecast_id: int) -> dict:
    with get_session() as session:
        f = session.get(Forecast, forecast_id)
        if f is None:
            raise HTTPException(status_code=404)
        memory = session.get(MemoryRef, f.episode_memory_id) if f.episode_memory_id else None
    return {"forecast": f, "episode_memory": memory}


@app.get("/api/race")
def race(asset: str | None = None) -> dict:
    """Cumulative Brier of Amnesiac vs Recall over resolved live forecasts."""
    query = select(Forecast).where(Forecast.source == "live", Forecast.status == "RESOLVED")
    if asset:
        query = query.where(Forecast.asset == _asset(asset))
    with get_session() as session:
        rows = session.exec(query.order_by(Forecast.t)).all()
    series, a_sum, r_sum = [], 0.0, 0.0
    for i, f in enumerate(rows, 1):
        a_sum += f.amnesiac_brier
        r_sum += f.recall_brier
        series.append({"t": f.t, "asset": f.asset, "amnesiac": a_sum / i, "recall": r_sum / i, "action": f.recall_action})
    return {"n": len(rows), "series": series, "coin_flip": 0.25}


@app.get("/api/stats")
def stats() -> dict:
    with get_session() as session:
        stored = session.exec(select(MemoryRef.kind, func.count()).where(MemoryRef.status == "STORED").group_by(MemoryRef.kind)).all()
        live = session.exec(select(Forecast.status, func.count()).where(Forecast.source == "live").group_by(Forecast.status)).all()
        users = session.exec(select(func.count()).select_from(User)).one()
        picks_n = session.exec(select(func.count()).select_from(Pick)).one()
        sessions_n = session.exec(select(func.count()).select_from(PredictSession)).one()
        episodes = sum(
            (engine.latest_policy_state(a).book.get("episodes", 0) if engine.latest_policy_state(a) else 0)
            for a in get_settings().assets
        )
    by_kind = dict(stored)
    return {
        "assets": get_settings().assets,
        "memories_stored": sum(by_kind.values()),
        "memories_by_kind": by_kind,
        "forecasts": dict(live),
        "episodes_learned": episodes,
        "users": users,
        "calls": picks_n,
        "sessions": sessions_n,
    }


@app.get("/api/memories")
def memories(kind: str | None = Query(None, max_length=30), limit: int = Query(200, ge=1, le=2000)) -> list[dict]:
    # user histories are private (see /api/me/record)
    query = select(MemoryRef).where(~MemoryRef.namespace.startswith("mr-user-"))
    if kind:
        query = query.where(MemoryRef.kind == kind)
    with get_session() as session:
        rows = session.exec(query.order_by(desc(MemoryRef.id)).limit(limit)).all()
    return [r.model_dump() | {"blob_url": WALRUS_AGGREGATOR + r.blob_id if r.blob_id else None} for r in rows]


@app.get("/api/lessons")
def lessons(asset: str | None = None) -> list[Lesson]:
    query = select(Lesson)
    if asset:
        query = query.where(Lesson.asset == _asset(asset))
    with get_session() as session:
        return session.exec(query.order_by(desc(Lesson.id))).all()


@app.get("/api/policy")
def policy(asset: str = "SUI") -> dict:
    asset = _asset(asset)
    state = engine.latest_policy_state(asset)
    book, covers_until = engine.current_book(asset)
    return {
        "asset": asset,
        "active_rules": engine.lesson_status(asset),
        "snapshot": None if state is None else {"id": state.snapshot_id, "source": state.source, "ts": state.ts},
        "episodes": book.episodes,
        "covers_until": covers_until,
        "credibility": {k: {v: s.summary() for v, s in b.items()} for k, b in book.stats.items()},
    }


@app.post("/api/admin/run/{job}")
async def run_job(job: str, x_admin_token: str = Header(default="")) -> dict:
    token = get_settings().admin_token
    if not token or not secrets.compare_digest(x_admin_token.encode(), token.encode()):
        raise HTTPException(status_code=401, detail="invalid admin token")
    if job not in JOBS:
        raise HTTPException(status_code=404, detail=f"unknown job {job}")
    return await JOBS[job]()


class ChallengeIn(BaseModel):
    address: str = Field(max_length=70)


class LoginIn(BaseModel):
    address: str = Field(max_length=70)
    nonce: str = Field(max_length=64)
    signature: str = Field(max_length=8192)  # zkLogin signatures are a few KB


class SessionIn(BaseModel):
    asset: str = Field(max_length=10)
    mode: str = Field(max_length=10)  # own | model
    direction: str | None = Field(None, max_length=10)


class CallIn(BaseModel):
    direction: str = Field(max_length=10)


class QuestionIn(BaseModel):
    text: str = Field(max_length=1000)


class GuideTurn(BaseModel):
    role: str = Field(max_length=20)
    text: str = Field(max_length=1000)


class GuideIn(BaseModel):
    text: str = Field(max_length=1000)
    history: list[GuideTurn] = Field(default=[], max_length=24)


challenge_limit = RateLimit(10, 60)
login_limit = RateLimit(10, 60)
session_limit = RateLimit(10, 60)
question_limit = RateLimit(15, 60, "You're asking too quickly. Wait a moment and try again.")


def _token(authorization: str) -> str:
    return authorization.removeprefix("Bearer ").strip()[:200]


def current_address(authorization: str = Header(default="")) -> str:
    token = _token(authorization)
    try:
        return auth.address_for_token(token)
    except auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.post("/api/auth/challenge")
def auth_challenge(body: ChallengeIn, request: Request) -> dict:
    challenge_limit.hit(client_ip(request))
    try:
        return auth.create_challenge(body.address)
    except auth.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/auth/login")
def auth_login(body: LoginIn, request: Request) -> dict:
    login_limit.hit(client_ip(request))
    try:
        session = auth.login(body.address, body.nonce, body.signature)
    except auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    user = credits.get_user(session["address"])
    return session | {"credits": user.credits}


@app.post("/api/auth/logout")
def auth_logout(authorization: str = Header(default="")) -> dict:
    auth.revoke(_token(authorization))
    return {"ok": True}


def _me(address: str) -> dict:
    user = credits.get_user(address)
    with get_session() as session:
        ledger = session.exec(
            select(CreditEntry).where(CreditEntry.address == address).order_by(desc(CreditEntry.id)).limit(20)
        ).all()
        my_picks = session.exec(select(Pick).where(Pick.address == address).order_by(desc(Pick.id)).limit(50)).all()
    return {
        "address": address, "credits": user.credits, "week": user.week, "cap": credits.CAP,
        "weekly_floor": credits.WEEKLY_FLOOR, "next_slot": picks.next_slot(), "ledger": ledger,
        "picks": [sessions.pick_out(p) for p in my_picks], "memory_namespace": picks.user_namespace(address),
        "session_cost": credits.SESSION_COST, "call_reward": credits.CALL_REWARD, "questions_per_session": sessions.MAX_MESSAGES,
    }


@app.get("/api/me")
def me(address: str = Depends(current_address)) -> dict:
    return _me(address)


@app.get("/api/me/record")
def my_record(asset: str | None = None, address: str = Depends(current_address)) -> dict:
    return sessions.personal_record(address, _asset(asset) if asset else None)


def _session_errors(fn):
    try:
        return fn()
    except credits.InsufficientCredits as exc:
        raise HTTPException(status_code=402, detail=str(exc))
    except (sessions.SessionError, picks.PickError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/sessions")
def open_session(body: SessionIn, address: str = Depends(current_address)) -> dict:
    session_limit.hit(address)
    ps = _session_errors(lambda: sessions.open_session(address, _asset(body.asset), body.mode, body.direction))
    return sessions.view(ps) | {"credits": credits.get_user(address).credits}


@app.get("/api/sessions")
def my_sessions(address: str = Depends(current_address)) -> list[dict]:
    return sessions.list_sessions(address)


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: int, address: str = Depends(current_address)) -> dict:
    return sessions.view(_session_errors(lambda: sessions.get_owned(address, session_id)))


@app.post("/api/sessions/{session_id}/call")
def lock_call(session_id: int, body: CallIn, address: str = Depends(current_address)) -> dict:
    return sessions.view(_session_errors(lambda: sessions.lock_call(address, session_id, body.direction)))


@app.post("/api/sessions/{session_id}/messages")
def ask_in_session(session_id: int, body: QuestionIn, address: str = Depends(current_address)) -> dict:
    question_limit.hit(address)
    return _session_errors(lambda: sessions.ask(address, session_id, body.text))


GUIDE_LIMIT = 20  # per IP per hour
guide_limit = RateLimit(GUIDE_LIMIT, 3600, "Too many questions for now. Sign in to keep going in a session.")


@app.post("/api/guide")
def ask_guide(body: GuideIn, request: Request) -> dict:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="ask a question")
    left = guide_limit.hit(client_ip(request))
    s = stats()
    out = guide.answer(text, [t.model_dump() for t in body.history[-12:]], {
        "memories_on_walrus": s["memories_stored"], "past_hours_studied": s["episodes_learned"],
    })
    return {"text": out["text"], "by": out["by"], "left": left}


@app.get("/api/leaderboard")
def leaderboard(limit: int = Query(20, ge=1, le=100)) -> dict:
    """Users ranked by hit rate (at least 3 resolved calls)."""
    with get_session() as session:
        rows = session.exec(
            select(Pick.address, func.count(), func.sum(Pick.status == "WON"))
            .where(Pick.status.in_(["WON", "LOST"])).group_by(Pick.address)
        ).all()
    board = [
        {"address": a[:6] + "…" + a[-4:], "calls": n, "right": int(w or 0), "hit_rate": (w or 0) / n}
        for a, n, w in rows if n >= 3
    ]
    board.sort(key=lambda r: (r["hit_rate"], r["calls"]), reverse=True)
    return {"users": board[:limit]}
