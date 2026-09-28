"""
Per-target history: how speed, TTFT and billing of one provider moved across runs.

Built only from data already stored for every run (samples and scores), so it costs
no API requests. Each run is compared with its baseline on its own; the history is
what shows the day a provider changed something, or a slow drift that stays inside
the per-run tolerances.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from attest.comparator.latency import _compute_tps
from attest.db import Database
from attest.models import MethodTier, RawSample, Verdict


def _median(values: list[float]) -> float | None:
    return round(float(np.median(values)), 1) if values else None


def _run_metrics(samples: list[RawSample]) -> dict[str, Any]:
    ttfts = [float(s.ttft_ms) for s in samples if s.ttft_ms is not None]
    # Decode speed when the run was streamed, end-to-end speed otherwise
    decode_only = bool(ttfts)
    tps = [t for s in samples if (t := _compute_tps(s, decode_only)) is not None]
    latencies = [float(s.latency_ms) for s in samples if (s.latency_ms or 0) > 0]
    return {
        "samples": len(samples),
        "ttft_ms": _median(ttfts),
        "tps": _median(tps),
        "tps_decode_only": decode_only,
        "latency_ms": _median(latencies),
    }


def build_target_history(
    db: Database, target_id: str, limit: int = 30
) -> list[dict[str, Any]]:
    """Runs of a target, oldest first, with their speed and billing figures."""
    history = []
    for run in reversed(db.list_runs(target_id=target_id, limit=limit)):
        if run.id is None:
            continue
        scores = db.get_scores(run.id)
        by_method = {s.method: s for s in scores}
        billing = by_method.get(MethodTier.BILLING.value)
        iris = by_method.get(MethodTier.IRIS.value)
        history.append(
            {
                "run_id": run.id,
                "started_at": run.started_at,
                "baseline_id": run.baseline_id,
                "battery_version": run.battery_version,
                "verdict": Verdict.aggregate(scores).value,
                **_run_metrics(db.get_run_samples(run.id)),
                # Worst relative overcharge vs the baseline (0.12 = +12%)
                "overcharge": (
                    billing.value
                    if billing and billing.verdict != Verdict.SKIP
                    else None
                ),
                # Lower bound on the share of requests served by another model
                "iris_dilution": (
                    iris.details.get("dilution_lower_bound")
                    if iris and iris.verdict != Verdict.SKIP
                    else None
                ),
            }
        )
    return history
