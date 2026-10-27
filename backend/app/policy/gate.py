"""Promotion gate: a memory rule is only switched on if it improves Brier on two disjoint periods."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from app.evaluation.metrics import brier
from app.policy.recall_policy import PolicyConfig

RULES = {
    "shrink": "enable_shrink",
    "abstain": "enable_abstain",
    "switch": "enable_switch",
}
STATEMENTS = {
    "shrink": "Scale a voice's confidence by how well-calibrated it has been in similar regimes",
    "abstain": "Return NO_CALL when every voice has had negative skill in similar regimes",
    "switch": "Switch to the voice with the best track record in similar regimes",
}
MIN_DELTA = 0.0002  # Brier improvement required on each period


def evaluate_rules(frame: pd.DataFrame, preds: pd.DataFrame, simulate) -> list[dict]:
    """Ablate each rule against the all-candidate-rules-on config, on the first and second half."""
    labels = frame.loc[preds.index, "label"]
    mid = preds.index[len(preds) // 2]
    full = PolicyConfig(enable_shrink=True, enable_abstain=True, enable_switch=False)

    def halves(cfg: PolicyConfig) -> tuple[float, float]:
        rows, _ = simulate(frame, preds, cfg)
        r = rows.join(labels).dropna(subset=["label"])
        a, b = r[r.index < mid], r[r.index >= mid]
        return brier(a["recall_p"], a["label"]), brier(b["recall_p"], b["label"])

    results = []
    for rule, flag in RULES.items():
        with_rule = replace(full, **{flag: True})
        without_rule = replace(full, **{flag: False})
        on, off = halves(with_rule), halves(without_rule)
        deltas = (off[0] - on[0], off[1] - on[1])  # positive = rule helps
        passed = all(d >= MIN_DELTA for d in deltas)
        results.append({
            "rule": rule,
            "status": "validated" if passed else "rejected",
            "statement": STATEMENTS[rule],
            "evidence": {
                "periods": ["first half", "second half"],
                "split_t": int(mid),
                "brier_with": [round(x, 5) for x in on],
                "brier_without": [round(x, 5) for x in off],
                "delta": [round(x, 5) for x in deltas],
                "min_delta": MIN_DELTA,
                "n": int(len(preds)),
            },
        })
    return results


def config_from_lessons(latest_status: dict[str, str]) -> PolicyConfig:
    """Only validated rules are active. No lessons yet means memory changes nothing."""
    return PolicyConfig(**{flag: latest_status.get(rule) == "validated" for rule, flag in RULES.items()})
