"""Walk-forward backtest: train only on labels known at t, predict t, let memory grow as outcomes resolve."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.evaluation.metrics import summary
from app.features.build import PRICE_FEATURES, build_frame, load_candles, load_onchain
from app.features.regime import regime_of
from app.models.voices import POLICY_VOICES, PRIMARY_VOICE, make_voices
from app.policy.recall_policy import PolicyConfig, decide
from app.policy.stats import StatsBook

log = logging.getLogger(__name__)

REGIME_DIMS = ("vol", "trend", "chain", "session")


@dataclass(frozen=True)
class BacktestConfig:
    asset: str = "SUI"
    horizon_h: int = 4
    min_train_rows: int = 21 * 24
    retrain_every_h: int = 24
    train_window_h: int = 60 * 24
    with_onchain: bool = True
    include_ablation: bool = True


def voice_predictions(frame: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    """Per-hour predictions of every voice, retrained every `retrain_every_h` on resolved rows only."""
    usable = frame.dropna(subset=PRICE_FEATURES)
    times = usable.index.to_numpy()
    voices = make_voices(cfg.with_onchain, cfg.include_ablation)
    rows, fitted_at = [], None
    for i, t in enumerate(times):
        train = usable[(usable["resolved_at"] <= t) & usable["label"].notna()]
        train = train[train.index > t - cfg.train_window_h * 3_600_000]
        if len(train) < cfg.min_train_rows:
            continue
        if fitted_at is None or t - fitted_at >= cfg.retrain_every_h * 3_600_000:
            for v in voices:
                v.fit(train)
            fitted_at = t
        row = usable.iloc[[i]]
        rows.append({"t": int(t)} | {v.name: float(v.predict(row)[0]) for v in voices})
    return pd.DataFrame(rows).set_index("t")


def simulate_recall(
    frame: pd.DataFrame, preds: pd.DataFrame, policy: PolicyConfig, primary: str = PRIMARY_VOICE
) -> tuple[pd.DataFrame, StatsBook]:
    """Replay hours in order. Memory at t only holds episodes whose outcome resolved by t."""
    meta = frame.loc[preds.index]
    regimes = [regime_of(r) for _, r in meta.iterrows()]
    probs = [{v: float(preds.at[t, v]) for v in POLICY_VOICES} for t in preds.index]
    pending = sorted(
        (meta.at[t, "resolved_at"], i) for i, t in enumerate(preds.index) if not np.isnan(meta.at[t, "label"])
    )
    book, cursor, out = StatsBook(), 0, []
    for i, t in enumerate(preds.index):
        while cursor < len(pending) and pending[cursor][0] <= t:
            j = pending[cursor][1]
            book.add_episode(regimes[j], probs[j], float(meta.iloc[j]["label"]))
            cursor += 1
        d = decide(regimes[i], probs[i], book, primary, policy)
        out.append({"t": t, "recall_p": d.p, "recall_voice": d.voice, "action": d.action, "alpha": d.alpha,
                    "level": d.level, "n_matched": d.n_matched, "reason": "; ".join(d.reasons)} | regimes[i])
    return pd.DataFrame(out).set_index("t"), book


def run_backtest(cfg: BacktestConfig = BacktestConfig(), policy: PolicyConfig = PolicyConfig()) -> dict:
    frame = build_frame(load_candles(cfg.asset), load_onchain() if cfg.with_onchain else None, cfg.horizon_h)
    preds = voice_predictions(frame, cfg)
    recall, book = simulate_recall(frame, preds, policy)
    result = preds.join(recall).join(frame[["close", "close_future", "label"]])
    result = result.dropna(subset=["label"])
    return {"rows": result, "report": report(result), "book": book}


def report(result: pd.DataFrame) -> dict:
    y = result["label"]
    voices = [c for c in result.columns if c.endswith("-v1") or c == "naive-momentum"]
    rep = {"period": {"start": int(result.index.min()), "end": int(result.index.max()), "n": len(result),
                      "base_rate_up": float(y.mean())},
           "voices": {v: summary(result[v], y) for v in voices}}
    rep["voices"]["amnesiac"] = summary(result[PRIMARY_VOICE], y)
    rep["voices"]["recall"] = summary(result["recall_p"], y)
    called = result["action"] != "NO_CALL"
    rep["recall_actions"] = result["action"].value_counts().to_dict()
    rep["recall_when_called"] = summary(result.loc[called, "recall_p"], y[called])
    rep["amnesiac_same_hours"] = summary(result.loc[called, PRIMARY_VOICE], y[called])
    rep["by_vol"] = {
        vol: {"n": int(len(g)), "amnesiac": summary(g[PRIMARY_VOICE], g["label"])["brier"],
              "recall": summary(g["recall_p"], g["label"])["brier"]}
        for vol, g in result.groupby("vol")
    }
    return rep
