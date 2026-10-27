import numpy as np
import pandas as pd

from app.backtest.walkforward import simulate_recall
from app.data.validation import HOUR_MS
from app.policy.recall_policy import PolicyConfig, decide, fit_alpha
from app.policy.stats import RegimeStats, StatsBook

REGIME = {"vol": "high", "trend": "down", "chain": "busy", "session": "us-weekday"}
VOICES = ("lr-v1", "rf-v1", "naive-momentum")


def book_with(p: dict[str, float], labels: list[float], regime=REGIME) -> StatsBook:
    book = StatsBook()
    for y in labels:
        book.add_episode(regime, p, y)
    return book


def test_empty_memory_keeps_baseline():
    d = decide(REGIME, {"lr-v1": 0.7}, StatsBook(), "lr-v1")
    assert d.action == "BASELINE" and d.p == 0.7


def test_overconfident_voice_is_shrunk_toward_half():
    # lr says 0.7 every time but it is UP only half the time -> no skill -> shrink.
    book = book_with({"lr-v1": 0.7}, [1, 0] * 20)
    d = decide(REGIME, {"lr-v1": 0.7}, book, "lr-v1", PolicyConfig(enable_abstain=False))
    assert d.action == "ADJUSTED"
    assert 0.5 <= d.p < 0.6


def test_skilled_voice_is_left_alone():
    book = StatsBook()
    for i in range(40):
        y = float(i % 2)
        book.add_episode(REGIME, {"lr-v1": 0.65 if y else 0.35}, y)
    d = decide(REGIME, {"lr-v1": 0.65}, book, "lr-v1")
    assert d.action in {"BASELINE", "ADJUSTED"} and d.p >= 0.65


def test_abstains_when_every_voice_is_bad_here():
    # Confidently wrong: says 0.8 but it always goes down.
    book = book_with({"lr-v1": 0.8}, [0.0] * 20)
    d = decide(REGIME, {"lr-v1": 0.8}, book, "lr-v1")
    assert d.action == "NO_CALL" and d.p == 0.5


def test_falls_back_to_coarser_regime_level():
    other = REGIME | {"chain": "quiet"}
    book = book_with({"lr-v1": 0.6}, [1, 0] * 10, regime=other)  # same vol+trend, different chain
    d = decide(REGIME, {"lr-v1": 0.6}, book, "lr-v1", PolicyConfig(enable_abstain=False))
    assert d.level == "vol=high|trend=down"


def test_alpha_shrinks_toward_one_with_few_episodes():
    s = RegimeStats()
    s.add(0.9, 0.0)  # one confidently wrong episode
    assert fit_alpha(s, PolicyConfig(shrink_prior=5)) > 0.5


def test_backtest_memory_never_contains_unresolved_outcomes():
    """At hour t the policy may only learn from episodes resolved by t (horizon 4h)."""
    n = 60
    t0 = 1_800_000_000_000 - (1_800_000_000_000 % HOUR_MS)
    idx = [t0 + i * HOUR_MS for i in range(n)]
    frame = pd.DataFrame(
        {
            "vol_pct_30d": 0.9, "ema24_dist": -0.01, "ema72_dist": -0.01, "ema24_above_72": False,
            "tx_z_7d": 2.0, "hour_utc": 15, "is_weekend": 0.0,
            "label": [float(i % 2) for i in range(n)],
            "resolved_at": [t + 4 * HOUR_MS for t in idx],
        },
        index=idx,
    )
    preds = pd.DataFrame({v: 0.6 for v in VOICES}, index=idx)
    out, _ = simulate_recall(frame, preds, PolicyConfig(n_min=1))
    resolved_by_t = np.array([(frame["resolved_at"] <= t).sum() for t in idx])
    # n_matched counts episodes the policy saw for the primary voice at each hour.
    assert (out["n_matched"].to_numpy() <= resolved_by_t).all()
    assert out["n_matched"].iloc[3] == 0  # nothing has resolved in the first 4 hours
