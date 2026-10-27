"""Forecasting voices. Every voice outputs P(close at t+h > close at t)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.features.build import ONCHAIN_FEATURES, PRICE_FEATURES

P_MIN, P_MAX = 0.02, 0.98


class SklearnVoice:
    def __init__(self, name: str, features: list[str], make_model) -> None:
        self.name = name
        self.features = features
        self._make_model = make_model
        self._model = None
        self._medians: pd.Series | None = None

    def fit(self, frame: pd.DataFrame) -> "SklearnVoice":
        X = frame[self.features]
        self._medians = X.median()
        self._model = self._make_model().fit(X.fillna(self._medians).fillna(0), frame["label"].astype(int))
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        X = frame[self.features].fillna(self._medians).fillna(0)
        return np.clip(self._model.predict_proba(X)[:, 1], P_MIN, P_MAX)

    def contributions(self, row: pd.DataFrame) -> dict[str, float] | None:
        """Per-feature log-odds contribution (coef × standardised value)."""
        steps = getattr(self._model, "named_steps", {})
        scaler, lr = steps.get("standardscaler"), steps.get("logisticregression")
        if scaler is None or lr is None:
            return None
        z = scaler.transform(row[self.features].fillna(self._medians).fillna(0))[0]
        return {f: float(c * v) for f, c, v in zip(self.features, lr.coef_[0], z)}


class MomentumVoice:
    """Naive reference voice: leans with the last 4h move."""

    name = "naive-momentum"

    def fit(self, frame: pd.DataFrame) -> "MomentumVoice":
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.where(frame["ret_4h"].fillna(0) > 0, 0.55, 0.45)


def _lr():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000))


def _rf():
    return RandomForestClassifier(n_estimators=200, max_depth=5, min_samples_leaf=40, n_jobs=-1, random_state=7)


def make_voices(with_onchain: bool = True, include_ablation: bool = False) -> list:
    full = PRICE_FEATURES + (ONCHAIN_FEATURES if with_onchain else [])
    voices = [
        SklearnVoice("lr-v1", full, _lr),
        SklearnVoice("rf-v1", full, _rf),
        MomentumVoice(),
    ]
    if include_ablation and with_onchain:
        voices += [SklearnVoice("lr-price-v1", PRICE_FEATURES, _lr), SklearnVoice("rf-price-v1", PRICE_FEATURES, _rf)]
    return voices


POLICY_VOICES = ("lr-v1", "rf-v1", "naive-momentum")
PRIMARY_VOICE = "lr-v1"
