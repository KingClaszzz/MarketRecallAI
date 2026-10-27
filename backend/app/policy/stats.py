"""Sufficient statistics of past episodes per (regime level, voice): the state the Recall policy reads."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.features.regime import LEVELS


@dataclass
class RegimeStats:
    n: int = 0
    sum_p: float = 0.0
    sum_y: float = 0.0
    sum_brier: float = 0.0
    sum_dp2: float = 0.0  # sum (p - 0.5)^2
    sum_dpy: float = 0.0  # sum (p - 0.5)(y - 0.5)

    def add(self, p: float, y: float) -> None:
        self.n += 1
        self.sum_p += p
        self.sum_y += y
        self.sum_brier += (p - y) ** 2
        self.sum_dp2 += (p - 0.5) ** 2
        self.sum_dpy += (p - 0.5) * (y - 0.5)

    @property
    def brier(self) -> float:
        return self.sum_brier / self.n if self.n else float("nan")

    @property
    def bss(self) -> float:
        # A constant 0.5 forecast always scores 0.25.
        return 1 - self.brier / 0.25 if self.n else float("nan")

    @property
    def avg_p(self) -> float:
        return self.sum_p / self.n if self.n else float("nan")

    @property
    def freq_up(self) -> float:
        return self.sum_y / self.n if self.n else float("nan")

    def summary(self) -> dict:
        return {"n": self.n, "bss": self.bss, "brier": self.brier, "avg_p": self.avg_p, "freq_up": self.freq_up}


def level_key(regime: dict[str, str], dims: tuple[str, ...]) -> str:
    return "|".join(f"{d}={regime[d]}" for d in dims)


class StatsBook:
    def __init__(self) -> None:
        self.stats: dict[str, dict[str, RegimeStats]] = {}  # level_key -> voice -> stats
        self.episodes = 0

    def add_episode(self, regime: dict[str, str], voice_probs: dict[str, float], label: float) -> None:
        for dims in LEVELS:
            bucket = self.stats.setdefault(level_key(regime, dims), {})
            for voice, p in voice_probs.items():
                bucket.setdefault(voice, RegimeStats()).add(p, label)
        self.episodes += 1

    def get(self, key: str, voice: str) -> RegimeStats | None:
        return self.stats.get(key, {}).get(voice)

    def to_dict(self) -> dict:
        return {"episodes": self.episodes, "stats": {k: {v: asdict(s) for v, s in b.items()} for k, b in self.stats.items()}}

    @classmethod
    def from_dict(cls, data: dict) -> "StatsBook":
        book = cls()
        book.episodes = data.get("episodes", 0)
        book.stats = {k: {v: RegimeStats(**s) for v, s in b.items()} for k, b in data["stats"].items()}
        return book

    def merge(self, other: "StatsBook") -> None:
        for key, bucket in other.stats.items():
            mine = self.stats.setdefault(key, {})
            for voice, s in bucket.items():
                m = mine.setdefault(voice, RegimeStats())
                for f in ("n", "sum_p", "sum_y", "sum_brier", "sum_dp2", "sum_dpy"):
                    setattr(m, f, getattr(m, f) + getattr(s, f))
        self.episodes += other.episodes
