"""Recall policy: using stats from similar regimes, shrink toward 0.5, abstain, or switch voice.

Switching is off unless it passes the promotion gate (it hurt in walk-forward tests).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.features.regime import LEVELS
from app.models.voices import P_MAX, P_MIN
from app.policy.stats import RegimeStats, StatsBook, level_key


@dataclass(frozen=True)
class PolicyConfig:
    n_min: int = 8
    switch_margin: float = 0.02  # BSS lead needed to switch voice
    abstain_bss: float = -0.03  # NO_CALL below this
    shrink_prior: float = 5.0  # pseudo-episodes pulling alpha toward 1
    alpha_bounds: tuple[float, float] = (0.0, 1.2)
    enable_switch: bool = False
    enable_shrink: bool = True
    enable_abstain: bool = True


@dataclass
class Decision:
    action: str  # BASELINE | ADJUSTED | NO_CALL
    voice: str
    p_raw: float
    p: float
    alpha: float = 1.0
    level: str | None = None
    n_matched: int = 0
    credibility: dict[str, dict] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def fit_alpha(s: RegimeStats, cfg: PolicyConfig) -> float:
    """Least-squares scale for p' = 0.5 + a (p - 0.5), shrunk toward a = 1 by a pseudo-count prior."""
    if s.sum_dp2 < 1e-9:
        return 1.0
    a_star = s.sum_dpy / s.sum_dp2
    a = (s.n * a_star + cfg.shrink_prior) / (s.n + cfg.shrink_prior)
    return float(np.clip(a, *cfg.alpha_bounds))


def decide(
    regime: dict[str, str],
    voice_probs: dict[str, float],
    book: StatsBook,
    primary: str,
    cfg: PolicyConfig = PolicyConfig(),
) -> Decision:
    p_raw = voice_probs[primary]
    decision = Decision(action="BASELINE", voice=primary, p_raw=p_raw, p=p_raw)
    if book.episodes == 0:
        decision.reasons.append("no resolved episodes in memory yet")
        return decision

    key = None
    for dims in LEVELS:
        candidate = level_key(regime, dims)
        s = book.get(candidate, primary)
        if s is not None and s.n >= cfg.n_min:
            key = candidate
            break
    if key is None:
        decision.reasons.append(f"fewer than {cfg.n_min} similar episodes, even at the coarsest regime level")
        return decision

    decision.level = key
    stats = {v: book.get(key, v) for v in voice_probs}
    credibility = {v: s.summary() for v, s in stats.items() if s is not None and s.n >= cfg.n_min}
    decision.credibility = credibility
    decision.n_matched = credibility[primary]["n"]

    best = max(credibility, key=lambda v: credibility[v]["bss"])
    if cfg.enable_abstain and credibility[best]["bss"] < cfg.abstain_bss:
        decision.action, decision.p = "NO_CALL", 0.5
        decision.reasons.append(
            f"best voice here ({best}) has BSS {credibility[best]['bss']:+.3f} over {credibility[best]['n']} episodes; abstaining"
        )
        return decision

    chosen = primary
    if cfg.enable_switch and best != primary and credibility[best]["bss"] - credibility[primary]["bss"] > cfg.switch_margin:
        chosen = best
        decision.reasons.append(
            f"switched {primary} → {best}: BSS {credibility[primary]['bss']:+.3f} vs {credibility[best]['bss']:+.3f} in {key}"
        )

    p = voice_probs[chosen]
    alpha = 1.0
    if cfg.enable_shrink:
        alpha = fit_alpha(stats[chosen], cfg)
        if abs(alpha - 1) >= 0.05:
            c = credibility[chosen]
            decision.reasons.append(
                f"{chosen} in {key}: avg p {c['avg_p']:.2f} vs {c['freq_up']:.0%} UP over {c['n']} episodes → alpha {alpha:.2f}"
            )
        p = 0.5 + alpha * (p - 0.5)

    decision.voice, decision.alpha = chosen, alpha
    decision.p = float(np.clip(p, P_MIN, P_MAX))
    if decision.reasons:
        decision.action = "ADJUSTED"
    else:
        decision.reasons.append(f"memory agrees with {primary} in {key}; no change")
    return decision
