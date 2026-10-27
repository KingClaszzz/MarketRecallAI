"""Memory text formats: a consistent human/semantic line, then one JSON line for exact parsing."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.policy.stats import StatsBook

JSON_PREFIX = "DATA "


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def regime_text(regime: dict) -> str:
    return " ".join(f"{k}={regime[k]}" for k in ("vol", "trend", "chain", "session"))


def _with_data(header: str, data: dict) -> str:
    return f"{header}\n{JSON_PREFIX}{json.dumps(data, separators=(',', ':'), default=float)}"


def parse_data(text: str) -> dict | None:
    for line in text.splitlines():
        if line.startswith(JSON_PREFIX):
            return json.loads(line[len(JSON_PREFIX):])
    return None


def episode_text(f) -> str:
    outcome = "UP" if f.label == 1 else "DOWN_OR_FLAT"
    voices = " ".join(f"{v}={p:.2f}" for v, p in f.voices.items())
    header = (
        f"[EPISODE] {f.asset} {f.horizon_h}h @{iso(f.t)} | regime {regime_text(f.regime)}\n"
        f"voices {voices} → outcome={outcome} | amnesiac p={f.amnesiac_p:.2f} brier={f.amnesiac_brier:.3f} | "
        f"recall {f.recall_action} p={f.recall_p:.2f} brier={f.recall_brier:.3f}"
    )
    return _with_data(header, {
        "type": "episode", "forecast_id": f.id, "asset": f.asset, "horizon_h": f.horizon_h, "t": f.t,
        "regime": f.regime, "voices": f.voices, "label": f.label, "close_at_t": f.close_at_t,
        "close_at_resolve": f.close_at_resolve, "recall_p": f.recall_p, "recall_action": f.recall_action,
        "model_version": f.model_version,
    })


def credibility_chunks(asset: str, book: StatsBook, snapshot_id: str, covers_until: int, source: str) -> list[str]:
    """One memory per volatility bucket, each carrying the stats of every regime key under it."""
    groups: dict[str, dict] = {}
    for key, bucket in book.to_dict()["stats"].items():
        vol = key.split("|")[0]
        groups.setdefault(vol, {})[key] = bucket
    texts = []
    for i, (vol, stats) in enumerate(sorted(groups.items()), 1):
        lines = []
        for key, bucket in sorted(stats.items()):
            parts = []
            for voice, s in sorted(bucket.items()):
                n = s["n"]
                bss = 1 - (s["sum_brier"] / n) / 0.25 if n else float("nan")
                parts.append(f"{voice} n={n} bss={bss:+.3f}")
            lines.append(f"{key}: " + ", ".join(parts))
        header = (
            f"[CREDIBILITY] {asset} 4h snapshot {snapshot_id} part {i}/{len(groups)} ({vol}) "
            f"covers until {iso(covers_until)} from {source}\n" + "\n".join(lines)
        )
        texts.append(_with_data(header, {
            "type": "credibility", "asset": asset, "snapshot_id": snapshot_id, "part": i, "parts": len(groups),
            "covers_until": covers_until, "episodes": book.episodes, "source": source, "stats": stats,
        }))
    return texts


def lesson_text(asset: str, rule: str, status: str, statement: str, evidence: dict) -> str:
    return _with_data(f"[LESSON][{status}] {asset} rule={rule} | {statement}", {
        "type": "lesson", "asset": asset, "rule": rule, "status": status, "statement": statement, "evidence": evidence,
    })


def decision_text(asset: str, event: str, detail: str, data: dict) -> str:
    return _with_data(f"[DECISION] {asset} {event} | {detail}", {"type": "decision", "asset": asset, "event": event} | data)
