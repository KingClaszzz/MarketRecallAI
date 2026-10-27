"""Deterministic forecast metrics. The LLM never computes these."""
from __future__ import annotations

import numpy as np

EPS = 1e-6


def brier(p, y) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((p - y) ** 2)) if len(p) else float("nan")


def log_loss(p, y) -> float:
    p, y = np.clip(np.asarray(p, float), EPS, 1 - EPS), np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))) if len(p) else float("nan")


def accuracy(p, y) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((p > 0.5) == (y == 1))) if len(p) else float("nan")


def brier_skill(p, y, reference: float = 0.5) -> float:
    """1 - Brier / Brier(constant reference). > 0 means better than a coin flip."""
    ref = brier(np.full(len(p), reference), y)
    return 1 - brier(p, y) / ref if len(p) and ref > 0 else float("nan")


def reliability(p, y, bins: int = 10) -> list[dict]:
    p, y = np.asarray(p, float), np.asarray(y, float)
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if mask.any():
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(mask.sum()), "avg_p": float(p[mask].mean()), "freq_up": float(y[mask].mean())})
    return out


def summary(p, y) -> dict:
    return {
        "n": int(len(p)),
        "brier": brier(p, y),
        "log_loss": log_loss(p, y),
        "accuracy": accuracy(p, y),
        "bss": brier_skill(p, y),
    }
