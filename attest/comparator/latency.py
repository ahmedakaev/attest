"""
Level 1.5: Latency & Throughput Drift Comparator.
Detects performance-based model substitution signals:
  - TPS (tokens per second) drift: a sudden speedup may indicate a smaller/quantized model
  - Latency distribution shift: median, P95, P99 drift between baseline and audit
  - TTFT (time to first token, from streaming): queueing, cold starts and thinking time.
    With TTFT on both sides, TPS is decode speed after the first token, so provider
    queueing no longer shows up as a throughput change.
"""

from __future__ import annotations

import numpy as np

from attest.config import ThresholdsConfig
from attest.models import MethodTier, RawSample, Score, Verdict

# Below this decode window the TPS figure is dominated by timer and network jitter
MIN_DECODE_MS = 50


def _compute_tps(sample: RawSample, decode_only: bool = False) -> float | None:
    """Tokens per second for one sample.

    decode_only: count only the time after the first token. Hidden reasoning (billed
    but not streamed) was generated before TTFT, so it is left out of the tokens.
    """
    if not sample.usage or not isinstance(sample.usage, dict):
        return None
    completion_tokens = sample.usage.get("completion_tokens")
    if not completion_tokens or not isinstance(completion_tokens, (int, float)):
        return None
    if not sample.latency_ms or sample.latency_ms <= 0:
        return None
    if not decode_only:
        return float(completion_tokens) / (sample.latency_ms / 1000.0)
    if sample.ttft_ms is None:
        return None
    decode_ms = sample.latency_ms - sample.ttft_ms
    hidden = 0 if sample.reasoning_content else (sample.reasoning_tokens or 0)
    # The first token arrived at TTFT; the decode window holds the rest
    tokens = float(completion_tokens) - hidden - 1
    if decode_ms < MIN_DECODE_MS or tokens < 2:
        return None
    return tokens / (decode_ms / 1000.0)


def _percentile(values: list[float], pct: float) -> float:
    """Compute percentile of a list of floats."""
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def _compute_stats(values: list[float]) -> dict[str, float]:
    """Compute summary statistics for a list of values."""
    if not values:
        return {
            "count": 0,
            "mean": 0.0,
            "median": 0.0,
            "p5": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "std": 0.0,
        }
    return {
        "count": len(values),
        "mean": round(float(np.mean(values)), 2),
        "median": round(float(np.median(values)), 2),
        "p5": round(_percentile(values, 5), 2),
        "p95": round(_percentile(values, 95), 2),
        "p99": round(_percentile(values, 99), 2),
        "std": round(float(np.std(values)), 2),
    }


def compare_latency_throughput(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    run_id: int,
    thresholds: ThresholdsConfig,
) -> list[Score]:
    """
    Compare latency and throughput (TPS) distributions between baseline and audit run.

    Detection logic:
    - Matches samples across common prompt IDs so differences reflect genuine model
      performance rather than comparing short probes against long generation probes.
    - TPS drop >= tps_drop_fail on multi-token probes → FAIL (throttling, CPU offload, degradation);
      single-token probes (completion_tokens < 3) reflect network RTT + TTFT rather than true
      throughput, so there the drop is capped at WARN.
    - TPS increase >= tps_speedup_warn → WARN only: faster hardware is a legitimate cause, so a
      smaller-model swap must be confirmed by the behavioral checks (JSD / embeddings / assertions).
    - Latency median drift → WARN only (network path and region dominate latency).
    """
    scores: list[Score] = []

    # Align baseline samples with prompts present in the run
    run_prompt_ids = {s.prompt_id for s in run_samples}
    base_matched = [s for s in baseline_samples if s.prompt_id in run_prompt_ids]
    effective_base = base_matched if base_matched else baseline_samples
    overlap_count = len(
        run_prompt_ids.intersection({s.prompt_id for s in baseline_samples})
    )

    # Detect if sampling was predominantly single-token probes
    is_single_token_regime = all(
        (s.usage.get("completion_tokens", 1) if s.usage else 1) < 3 for s in run_samples
    )

    # --- 1. TPS Comparison ---
    # Decode-only TPS needs TTFT on both sides; mixing formulas would fake a drift
    decode_only = any(s.ttft_ms is not None for s in effective_base) and any(
        s.ttft_ms is not None for s in run_samples
    )
    base_tps = [
        t for s in effective_base if (t := _compute_tps(s, decode_only)) is not None
    ]
    run_tps = [
        t for s in run_samples if (t := _compute_tps(s, decode_only)) is not None
    ]

    if base_tps and run_tps and len(base_tps) >= 3 and len(run_tps) >= 3:
        base_stats = _compute_stats(base_tps)
        run_stats = _compute_stats(run_tps)

        base_median = base_stats["median"]
        run_median = run_stats["median"]

        # Relative change: positive = faster, negative = slower
        if base_median > 0:
            relative_change = (run_median - base_median) / base_median
        else:
            relative_change = 0.0

        tps_drop_warn = getattr(thresholds, "tps_drop_warn", thresholds.tps_drift_warn)
        tps_drop_fail = getattr(thresholds, "tps_drop_fail", thresholds.tps_drift_fail)
        tps_speedup_warn = getattr(thresholds, "tps_speedup_warn", 1.00)

        abs_change = abs(relative_change)

        if relative_change < 0:
            # Slowdown: drop in throughput indicates throttling, CPU emulation, or degradation
            direction = "slower"
            drop_ratio = abs_change
            # Without TTFT the speed includes the provider's network and proxy
            # overhead, so a drop alone cannot tell a slower model from a slower path
            if drop_ratio >= tps_drop_fail:
                verdict = (
                    Verdict.WARN
                    if is_single_token_regime or not decode_only
                    else Verdict.FAIL
                )
            elif drop_ratio >= tps_drop_warn:
                verdict = Verdict.WARN
            else:
                verdict = Verdict.PASS
            active_threshold = tps_drop_fail
            note = ""
            if drop_ratio >= tps_drop_fail and is_single_token_regime:
                note = " (single-token jitter: capped at WARN)"
            elif drop_ratio >= tps_drop_fail and not decode_only:
                note = " (end-to-end speed without TTFT includes proxy overhead: capped at WARN)"
        else:
            # Speedup: high-throughput cluster (e.g. Azure H100 vs standard).
            # Should NOT be a hard FAIL when assertions and semantics are authentic.
            direction = "faster"
            speedup_ratio = relative_change
            if speedup_ratio >= tps_speedup_warn:
                verdict = Verdict.WARN
                note = " (high-throughput cluster or fast hardware; verify assertion match)"
            else:
                verdict = Verdict.PASS
                note = ""
            active_threshold = tps_speedup_warn

        scores.append(
            Score(
                id=None,
                run_id=run_id,
                method=MethodTier.LATENCY_TPS.value,
                scope="aggregate",
                value=round(abs_change, 4),
                threshold=active_threshold,
                verdict=verdict,
                details={
                    "baseline_tps": base_stats,
                    "run_tps": run_stats,
                    "relative_change": round(relative_change, 4),
                    "direction": direction,
                    "matched_prompts": overlap_count,
                    "single_token_regime": is_single_token_regime,
                    "decode_only": decode_only,
                    "threshold_drop_fail": tps_drop_fail,
                    "threshold_speedup_warn": tps_speedup_warn,
                    "message": (
                        f"TPS {direction} by {abs_change:.1%}: "
                        f"baseline median {base_median:.1f} tok/s → run median {run_median:.1f} tok/s{note}"
                    ),
                },
            )
        )
    else:
        scores.append(
            Score(
                id=None,
                run_id=run_id,
                method=MethodTier.LATENCY_TPS.value,
                scope="aggregate",
                value=0.0,
                threshold=thresholds.tps_drift_fail,
                verdict=Verdict.SKIP,
                details={
                    "message": "Insufficient usage data to compute TPS comparison",
                    "baseline_samples_with_tps": len(base_tps),
                    "run_samples_with_tps": len(run_tps),
                },
            )
        )

    # --- 1.5. Time to first token ---
    scores.append(_compare_ttft(effective_base, run_samples, run_id, thresholds))

    # --- 2. Latency Distribution Comparison ---
    base_latencies = [
        float(s.latency_ms) for s in effective_base if (s.latency_ms or 0) > 0
    ]
    run_latencies = [
        float(s.latency_ms) for s in run_samples if (s.latency_ms or 0) > 0
    ]

    if (
        base_latencies
        and run_latencies
        and len(base_latencies) >= 3
        and len(run_latencies) >= 3
    ):
        base_lat_stats = _compute_stats(base_latencies)
        run_lat_stats = _compute_stats(run_latencies)

        base_med = base_lat_stats["median"]
        run_med = run_lat_stats["median"]

        if base_med > 0:
            lat_relative = (run_med - base_med) / base_med
        else:
            lat_relative = 0.0

        lat_warn = thresholds.latency_drift_warn
        lat_fail = thresholds.latency_drift_fail

        abs_lat_change = abs(lat_relative)
        if abs_lat_change >= lat_fail:
            lat_verdict = Verdict.WARN  # latency alone is WARN-level, not FAIL
        elif abs_lat_change >= lat_warn:
            lat_verdict = Verdict.WARN
        else:
            lat_verdict = Verdict.PASS

        lat_direction = "slower" if lat_relative > 0 else "faster"

        scores.append(
            Score(
                id=None,
                run_id=run_id,
                method=MethodTier.LATENCY_DRIFT.value,
                scope="aggregate",
                value=round(abs_lat_change, 4),
                threshold=lat_fail,
                verdict=lat_verdict,
                details={
                    "baseline_latency_ms": base_lat_stats,
                    "run_latency_ms": run_lat_stats,
                    "relative_change": round(lat_relative, 4),
                    "direction": lat_direction,
                    "matched_prompts": overlap_count,
                    "message": (
                        f"Latency {lat_direction} by {abs_lat_change:.1%}: "
                        f"baseline median {base_med:.0f}ms → run median {run_med:.0f}ms"
                    ),
                },
            )
        )
    else:
        scores.append(
            Score(
                id=None,
                run_id=run_id,
                method=MethodTier.LATENCY_DRIFT.value,
                scope="aggregate",
                value=0.0,
                threshold=thresholds.latency_drift_fail,
                verdict=Verdict.SKIP,
                details={"message": "Insufficient latency data for comparison"},
            )
        )

    return scores


def _compare_ttft(
    base_samples: list[RawSample],
    run_samples: list[RawSample],
    run_id: int,
    thresholds: ThresholdsConfig,
) -> Score:
    """Median TTFT drift. WARN-only: queueing and region move it as much as the model.

    A much faster first token on a thinking model is the notable case: the provider's
    model may not be thinking at all (a cheaper non-reasoning substitute).
    """
    base = [float(s.ttft_ms) for s in base_samples if s.ttft_ms is not None]
    run = [float(s.ttft_ms) for s in run_samples if s.ttft_ms is not None]
    if len(base) < 3 or len(run) < 3:
        return Score(
            id=None,
            run_id=run_id,
            method=MethodTier.LATENCY_TTFT.value,
            scope="aggregate",
            value=0.0,
            threshold=thresholds.ttft_drift_warn,
            verdict=Verdict.SKIP,
            details={
                "message": "No streamed TTFT on one side (baseline captured before TTFT, "
                "or the provider does not stream)",
                "baseline_samples_with_ttft": len(base),
                "run_samples_with_ttft": len(run),
            },
        )

    base_stats = _compute_stats(base)
    run_stats = _compute_stats(run)
    base_med, run_med = base_stats["median"], run_stats["median"]
    relative = (run_med - base_med) / base_med if base_med > 0 else 0.0
    verdict = (
        Verdict.WARN if abs(relative) >= thresholds.ttft_drift_warn else Verdict.PASS
    )
    direction = "slower" if relative > 0 else "faster"
    return Score(
        id=None,
        run_id=run_id,
        method=MethodTier.LATENCY_TTFT.value,
        scope="aggregate",
        value=round(abs(relative), 4),
        threshold=thresholds.ttft_drift_warn,
        verdict=verdict,
        details={
            "baseline_ttft_ms": base_stats,
            "run_ttft_ms": run_stats,
            "relative_change": round(relative, 4),
            "direction": direction,
            "message": (
                f"TTFT {direction} by {abs(relative):.1%}: "
                f"baseline median {base_med:.0f}ms → run median {run_med:.0f}ms"
            ),
        },
    )
