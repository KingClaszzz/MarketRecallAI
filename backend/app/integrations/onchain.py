"""Sui network metrics via Tatum gRPC: checkpoint lookup by timestamp and epoch info."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from app.config import get_settings
from app.integrations.sui_grpc import LEDGER, SuiGrpcClient
from app.integrations.tracking import tracked

SUMMARY_MASK = [
    "sequence_number",
    "summary.timestamp",
    "summary.epoch",
    "summary.total_network_transactions",
    "summary.epoch_rolling_gas_cost_summary",
]


@dataclass(frozen=True)
class Checkpoint:
    seq: int
    ts: int  # ms
    total_tx: int
    epoch: int
    computation_cost: int
    storage_cost: int
    storage_rebate: int


@lru_cache
def get_client() -> SuiGrpcClient:
    s = get_settings()
    return SuiGrpcClient(s.tatum_sui_grpc_host, s.tatum_api_key)


def _parse_ts(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _to_checkpoint(raw: dict) -> Checkpoint:
    summary = raw["checkpoint"]["summary"]
    gas = summary.get("epoch_rolling_gas_cost_summary", {})
    return Checkpoint(
        seq=int(raw["checkpoint"]["sequence_number"]),
        ts=_parse_ts(summary["timestamp"]),
        total_tx=int(summary["total_network_transactions"]),
        epoch=int(summary.get("epoch", 0)),
        computation_cost=int(gas.get("computation_cost", 0)),
        storage_cost=int(gas.get("storage_cost", 0)),
        storage_rebate=int(gas.get("storage_rebate", 0)),
    )


def get_checkpoint(seq: int | None = None) -> Checkpoint:
    request = {"sequence_number": str(seq)} if seq is not None else {}
    with tracked("tatum_grpc", "LedgerService.GetCheckpoint"):
        return _to_checkpoint(get_client().call(LEDGER, "GetCheckpoint", request, read_mask=SUMMARY_MASK))


def get_reference_gas_price() -> int:
    with tracked("tatum_grpc", "LedgerService.GetEpoch"):
        raw = get_client().call(LEDGER, "GetEpoch", read_mask=["epoch", "reference_gas_price"])
    return int(raw["epoch"]["reference_gas_price"])


def checkpoint_at(target_ms: int, tolerance_ms: int = 5_000, max_steps: int = 8) -> Checkpoint:
    """Latest checkpoint whose timestamp is <= target_ms (within tolerance), via interpolation search."""
    hi = get_checkpoint()
    if hi.ts <= target_ms:
        return hi
    lo: Checkpoint | None = None
    rate = 4.0 / 1000  # ~4 checkpoints/s on mainnet
    guess = hi.seq - int((hi.ts - target_ms) * rate)
    for _ in range(max_steps):
        probe = get_checkpoint(max(guess, 0))
        if probe.ts <= target_ms:
            lo = probe
            if target_ms - probe.ts <= tolerance_ms:
                return probe
        else:
            hi = probe
        if lo is not None:
            rate = (hi.seq - lo.seq) / max(hi.ts - lo.ts, 1)
            guess = lo.seq + int((target_ms - lo.ts) * rate)
            if guess >= hi.seq:
                guess = hi.seq - 1
        else:
            guess = hi.seq - int((hi.ts - target_ms) * rate) - int(tolerance_ms * rate)
    if lo is None:
        raise RuntimeError(f"checkpoint search did not bracket target {target_ms}")
    return lo
