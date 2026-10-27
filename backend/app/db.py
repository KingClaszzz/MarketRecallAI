from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, BigInteger, Column, Engine, Index, UniqueConstraint
from sqlmodel import Field, Session, SQLModel, create_engine

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Candle(SQLModel, table=True):
    """Closed 1h candle. open_time is the hour start in ms (UTC)."""

    source: str = Field(primary_key=True)  # tatum | binance
    symbol: str = Field(primary_key=True)
    open_time: int = Field(primary_key=True, sa_type=BigInteger)
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trades: int
    taker_buy_base: float
    ingested_at: datetime = Field(default_factory=utcnow)


class OnchainSnapshot(SQLModel, table=True):
    """Sui network state at the checkpoint closest to (not after) an hour boundary."""

    hour_ts: int = Field(primary_key=True, sa_type=BigInteger)  # hour boundary in ms (UTC)
    checkpoint_seq: int = Field(sa_type=BigInteger)
    checkpoint_ts: int = Field(sa_type=BigInteger)
    total_tx: int = Field(sa_type=BigInteger)
    epoch: int
    computation_cost: int = Field(sa_type=BigInteger)
    storage_cost: int = Field(sa_type=BigInteger)
    storage_rebate: int = Field(sa_type=BigInteger)
    reference_gas_price: int | None = Field(default=None, sa_type=BigInteger)
    ingested_at: datetime = Field(default_factory=utcnow)


class MarketSnapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    price_usd: float
    market_cap_usd: float | None = None
    volume_24h_usd: float | None = None
    change_24h_pct: float | None = None


class Forecast(SQLModel, table=True):
    """One decision hour. Append-only: outcome fields are filled once, at resolution."""

    id: int | None = Field(default=None, primary_key=True)
    asset: str = Field(index=True)
    t: int = Field(index=True, sa_type=BigInteger)  # decision time = close of the last 1h candle (ms)
    source: str = Field(default="live", index=True)  # live | backtest
    horizon_h: int
    close_at_t: float
    voices: dict = Field(default_factory=dict, sa_column=Column(JSON))  # voice -> p_up
    model_version: str
    regime: dict = Field(default_factory=dict, sa_column=Column(JSON))
    amnesiac_p: float
    recall_p: float
    recall_action: str  # BASELINE | ADJUSTED | NO_CALL
    trace: dict = Field(default_factory=dict, sa_column=Column(JSON))
    data_flags: list = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="PENDING", index=True)  # PENDING | RESOLVED | UNRESOLVABLE
    created_at: datetime = Field(default_factory=utcnow)
    close_at_resolve: float | None = None
    label: float | None = None
    amnesiac_brier: float | None = None
    recall_brier: float | None = None
    resolved_at: datetime | None = None
    episode_memory_id: int | None = None

    __table_args__ = (UniqueConstraint("asset", "t", "source"),)


class MemoryRef(SQLModel, table=True):
    """Local index of memories written to Walrus."""

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    namespace: str = Field(index=True)
    kind: str = Field(index=True)  # EPISODE | CREDIBILITY | LESSON | DECISION | INIT
    text: str
    memwal_id: str | None = None
    blob_id: str | None = None
    status: str = "PENDING"  # PENDING | STORED | FAILED | SKIPPED_BUDGET
    error: str | None = None
    ref: dict = Field(default_factory=dict, sa_column=Column(JSON))


class PolicyState(SQLModel, table=True):
    """Snapshots of the learned StatsBook; the latest row is active."""

    id: int | None = Field(default=None, primary_key=True)
    asset: str = Field(index=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    source: str  # bootstrap | live | restore
    covers_until: int = Field(sa_type=BigInteger)  # latest decision time t whose outcome is included (ms)
    book: dict = Field(default_factory=dict, sa_column=Column(JSON))
    snapshot_id: str | None = None


class Lesson(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    asset: str = Field(index=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    rule: str = Field(index=True)  # shrink | abstain | switch
    status: str  # observation | hypothesis | validated | rejected | retired
    statement: str
    evidence: dict = Field(default_factory=dict, sa_column=Column(JSON))
    supersedes: int | None = None
    memory_id: int | None = None


class User(SQLModel, table=True):
    address: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)
    credits: int = 0
    week: str = ""  # ISO week of the last refill


class CreditEntry(SQLModel, table=True):

    id: int | None = Field(default=None, primary_key=True)
    address: str = Field(index=True)
    ts: datetime = Field(default_factory=utcnow)
    delta: int
    balance: int
    reason: str  # signup | weekly_refill | session | session_refund | call_right | call_refund
    ref: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Pick(SQLModel, table=True):
    __table_args__ = (Index("ux_pick_window", "address", "asset", "slot_t", unique=True),)

    id: int | None = Field(default=None, primary_key=True)
    address: str = Field(index=True)
    asset: str = Field(index=True)
    slot_t: int = Field(index=True, sa_type=BigInteger)  # start of the 4h window
    direction: str  # UP | DOWN (= DOWN_OR_FLAT)
    status: str = Field(default="PENDING", index=True)  # PENDING | WON | LOST | REFUNDED
    created_at: datetime = Field(default_factory=utcnow)
    session_id: int | None = Field(default=None, index=True)
    mode: str = "own"  # own | model
    model_p: float | None = None  # Recall P(up) when the call was locked
    model_action: str | None = None
    close_at_t: float | None = None
    close_at_resolve: float | None = None
    resolved_at: datetime | None = None
    memory_id: int | None = None

    __table_args__ = (UniqueConstraint("address", "asset", "slot_t"),)

    @property
    def agrees_with_model(self) -> bool | None:
        if self.model_p is None or self.model_action == "NO_CALL" or abs(self.model_p - 0.5) < 0.005:
            return None
        return (self.direction == "UP") == (self.model_p > 0.5)


class PredictSession(SQLModel, table=True):

    id: int | None = Field(default=None, primary_key=True)
    address: str = Field(index=True)
    asset: str
    mode: str  # own | model
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    slot_t: int = Field(sa_type=BigInteger)
    forecast_id: int
    pick_id: int | None = None
    messages_used: int = 0
    max_messages: int
    history: dict = Field(default_factory=dict, sa_column=Column(JSON))
    context: dict = Field(default_factory=dict, sa_column=Column(JSON))


class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)
    ts: datetime = Field(default_factory=utcnow)
    role: str  # user | assistant
    text: str
    by: str | None = None  # llm | template
    problems: list = Field(default_factory=list, sa_column=Column(JSON))


class AuthChallenge(SQLModel, table=True):
    nonce: str = Field(primary_key=True)
    address: str
    message: str
    expires_at: datetime
    used: bool = False


class AuthSession(SQLModel, table=True):
    token_hash: str = Field(primary_key=True)
    address: str = Field(index=True)
    expires_at: datetime


class AskLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    address: str = Field(index=True)
    asset: str
    ts: datetime = Field(default_factory=utcnow)
    forecast_id: int | None = None
    response: dict = Field(default_factory=dict, sa_column=Column(JSON))


class IntegrationLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    service: str = Field(index=True)  # tatum_ohlcv | tatum_grpc | binance | coingecko | walrus | llm
    op: str
    ok: bool
    latency_ms: int
    error: str | None = None


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = normalize_url(get_settings().database_url)
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            # small pool for a single process; pre_ping survives a serverless database suspending idle connections
            _engine = create_engine(url, pool_size=3, max_overflow=2, pool_pre_ping=True, pool_recycle=300,
                                    connect_args={"options": "-c timezone=GMT"})
    return _engine


def normalize_url(url: str) -> str:
    """Hosted Postgres hands out postgres:// or postgresql:// URLs; use the psycopg 3 driver for both."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())
    _add_missing_columns()
    with get_engine().begin() as conn:  # create_all skips indexes on existing tables
        conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ux_pick_window ON pick (address, asset, slot_t)")
        if conn.dialect.name == "postgresql":
            # no policies: hosted data APIs (e.g. Supabase) see nothing, while the owning backend role is unaffected
            for table in SQLModel.metadata.sorted_tables:
                conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')


def _add_missing_columns() -> None:
    """create_all never alters existing tables, so add new columns by hand (SQLite only)."""
    engine = get_engine()
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info('{table.name}')")}
            for column in table.columns:
                if column.name in existing:
                    continue
                default = column.default.arg if column.default is not None and not callable(column.default.arg) else None
                suffix = "" if default is None else f" DEFAULT '{default}'" if isinstance(default, str) else f" DEFAULT {default}"
                conn.exec_driver_sql(
                    f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(engine.dialect)}{suffix}"
                )


def get_session() -> Session:
    return Session(get_engine())
