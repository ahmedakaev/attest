"""
Provider Battle & Run Comparison Engine.
Compares two audit runs or targets side-by-side across:
  - Infrastructure & Gateways
  - Throughput (TPS) & Generation Speed
  - Latency (Median & P95 TTFT)
  - Deterministic Logic & Assertions Match Rate
  - Distribution Divergence (JSD to Baseline)
  - Semantic Similarity (Embedding Cosine)
  - Cost & Final Recommended Verdict
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from attest.db import Database
from attest.detection.infrastructure import (
    InfrastructureFingerprint,
    detect_infrastructure,
)
from attest.models import RawSample, Run, Score, Target, Verdict


@dataclass
class TargetRunSummary:
    run_id: int
    target_id: str
    base_url: str
    claimed_model: str
    wire_model: str | None
    model_returned: str | None
    overall_verdict: Verdict
    infrastructure: InfrastructureFingerprint
    median_latency_ms: float
    p95_latency_ms: float
    median_tps: float
    assertion_total: int
    assertion_passed: int
    assertion_pass_rate: float
    jsd_score: float | None
    embedding_score: float | None
    total_samples: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "target_id": self.target_id,
            "base_url": self.base_url,
            "claimed_model": self.claimed_model,
            "wire_model": self.wire_model,
            "model_returned": self.model_returned,
            "overall_verdict": self.overall_verdict.value,
            "infrastructure": self.infrastructure.to_dict(),
            "median_latency_ms": round(self.median_latency_ms, 1),
            "p95_latency_ms": round(self.p95_latency_ms, 1),
            "median_tps": round(self.median_tps, 1),
            "assertion_total": self.assertion_total,
            "assertion_passed": self.assertion_passed,
            "assertion_pass_rate": round(self.assertion_pass_rate, 1),
            "jsd_score": round(self.jsd_score, 4)
            if self.jsd_score is not None
            else None,
            "embedding_score": round(self.embedding_score, 4)
            if self.embedding_score is not None
            else None,
            "total_samples": self.total_samples,
        }


@dataclass
class ComparisonResult:
    run_a: TargetRunSummary
    run_b: TargetRunSummary
    winner: str | None  # "a", "b", "tie", or None
    recommendation_ru: str
    recommendation_en: str
    deltas: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_a": self.run_a.to_dict(),
            "run_b": self.run_b.to_dict(),
            "winner": self.winner,
            "recommendation_ru": self.recommendation_ru,
            "recommendation_en": self.recommendation_en,
            "deltas": self.deltas,
        }


def _extract_run_summary(
    run: Run,
    target: Target,
    scores: list[Score],
    samples: list[RawSample],
) -> TargetRunSummary:
    # 1. Infrastructure
    infra_score = next((s for s in scores if s.method == "infrastructure"), None)
    if infra_score and infra_score.details:
        infra = InfrastructureFingerprint(
            proxy_gateway=infra_score.details.get("proxy_gateway"),
            upstream_cloud=infra_score.details.get("upstream_cloud"),
            deployment_id=infra_score.details.get("deployment_id"),
            server_software=infra_score.details.get("server_software"),
            region=infra_score.details.get("region"),
            confidence=infra_score.details.get("confidence", 1.0),
            raw_signatures=infra_score.details.get("raw_signatures", {}),
        )
    else:
        infra = detect_infrastructure(raw_samples=samples)

    # 2. Latencies
    latencies = [
        float(s.latency_ms) for s in samples if s.latency_ms and s.latency_ms > 0
    ]
    med_lat = float(np.median(latencies)) if latencies else 0.0
    p95_lat = float(np.percentile(latencies, 95)) if latencies else 0.0

    # 3. TPS
    tps_score = next((s for s in scores if s.method == "latency_tps"), None)
    med_tps = 0.0
    if tps_score and tps_score.details:
        r_tps = tps_score.details.get("run_tps", {})
        if isinstance(r_tps, dict):
            med_tps = float(r_tps.get("median", 0.0))
        elif isinstance(r_tps, (int, float)):
            med_tps = float(r_tps)
    if med_tps == 0.0 and samples:
        tps_list = []
        for s in samples:
            if s.usage and isinstance(s.usage, dict):
                ct = s.usage.get("completion_tokens")
                if ct and (s.latency_ms or 0) > 0:
                    tps_list.append(ct / (s.latency_ms / 1000.0))
        if tps_list:
            med_tps = float(np.median(tps_list))

    # 4. Assertions
    assert_score = next((s for s in scores if s.method == "assertions"), None)
    total_a = 0
    passed_a = 0
    if assert_score and assert_score.details:
        total_a = int(assert_score.details.get("total_assertions", 0))
        passed_a = int(assert_score.details.get("passed_assertions", 0))
    pass_rate = (passed_a / total_a * 100.0) if total_a > 0 else 100.0

    # 5. JSD & Embedding
    jsd_score_obj = next((s for s in scores if s.method == "jsd"), None)
    jsd_val = float(jsd_score_obj.value) if jsd_score_obj else None

    emb_score_obj = next((s for s in scores if s.method == "embedding_cosine"), None)
    emb_val = float(emb_score_obj.value) if emb_score_obj else None

    # Overall verdict via domain aggregate
    overall = Verdict.aggregate(scores)

    model_ret = next((s.model_returned for s in samples if s.model_returned), None)

    return TargetRunSummary(
        run_id=run.id or 0,
        target_id=target.id,
        base_url=target.base_url,
        claimed_model=target.model,
        wire_model=target.wire_model,
        model_returned=model_ret,
        overall_verdict=overall,
        infrastructure=infra,
        median_latency_ms=med_lat,
        p95_latency_ms=p95_lat,
        median_tps=med_tps,
        assertion_total=total_a,
        assertion_passed=passed_a,
        assertion_pass_rate=pass_rate,
        jsd_score=jsd_val,
        embedding_score=emb_val,
        total_samples=len(samples),
    )


def compare_runs_data(
    target_a: Target,
    run_a: Run,
    scores_a: list[Score],
    samples_a: list[RawSample],
    target_b: Target,
    run_b: Run,
    scores_b: list[Score],
    samples_b: list[RawSample],
) -> ComparisonResult:
    """
    Pure domain comparative analysis between two evaluation runs without database dependencies.
    """
    summary_a = _extract_run_summary(run_a, target_a, scores_a, samples_a)
    summary_b = _extract_run_summary(run_b, target_b, scores_b, samples_b)

    # Compute deltas
    # Speed comparison
    tps_multiplier = (
        round(summary_b.median_tps / summary_a.median_tps, 2)
        if (summary_a.median_tps > 0 and summary_b.median_tps > 0)
        else 1.0
    )
    lat_diff_ms = round(summary_b.median_latency_ms - summary_a.median_latency_ms, 1)

    deltas = {
        "tps_multiplier_b_vs_a": tps_multiplier,
        "latency_diff_ms_b_minus_a": lat_diff_ms,
        "assertion_pass_rate_diff": round(
            summary_b.assertion_pass_rate - summary_a.assertion_pass_rate, 1
        ),
    }

    # Decide winner & recommendation
    winner: str | None = None
    if (
        summary_a.overall_verdict == Verdict.FAIL
        and summary_b.overall_verdict != Verdict.FAIL
    ):
        winner = "b"
        rec_ru = f"Провайдер B ({target_b.id}) побеждает: провайдер A ({target_a.id}) дисквалифицирован (FAIL)."
        rec_en = f"Provider B ({target_b.id}) wins: Provider A ({target_a.id}) failed verification."
    elif (
        summary_b.overall_verdict == Verdict.FAIL
        and summary_a.overall_verdict != Verdict.FAIL
    ):
        winner = "a"
        rec_ru = f"Провайдер A ({target_a.id}) побеждает: провайдер B ({target_b.id}) дисквалифицирован (FAIL)."
        rec_en = f"Provider A ({target_a.id}) wins: Provider B ({target_b.id}) failed verification."
    else:
        # Both passed or both warned
        if (
            summary_b.median_tps > 0
            and summary_b.median_tps >= summary_a.median_tps * 1.2
            and summary_b.assertion_pass_rate >= summary_a.assertion_pass_rate
        ):
            winner = "b"
            rec_ru = (
                f"Провайдер B ({target_b.id}) предпочтительнее: генерирует в {tps_multiplier}x быстрее "
                f"({summary_b.median_tps:.1f} vs {summary_a.median_tps:.1f} ток/с) при идентичной точности logic-ассертов ({summary_b.assertion_pass_rate:.0f}%)."
            )
            rec_en = (
                f"Provider B ({target_b.id}) preferred: {tps_multiplier}x higher throughput "
                f"({summary_b.median_tps:.1f} vs {summary_a.median_tps:.1f} tok/s) with {summary_b.assertion_pass_rate:.0f}% assertion match."
            )
        elif (
            summary_a.median_tps > 0
            and summary_a.median_tps >= summary_b.median_tps * 1.2
            and summary_a.assertion_pass_rate >= summary_b.assertion_pass_rate
        ):
            winner = "a"
            inv_mult = (
                round(summary_a.median_tps / summary_b.median_tps, 2)
                if summary_b.median_tps > 0
                else 1.0
            )
            rec_ru = (
                f"Провайдер A ({target_a.id}) предпочтительнее: генерирует в {inv_mult}x быстрее "
                f"({summary_a.median_tps:.1f} vs {summary_b.median_tps:.1f} ток/с) при точности ассертов {summary_a.assertion_pass_rate:.0f}%."
            )
            rec_en = (
                f"Provider A ({target_a.id}) preferred: {inv_mult}x higher throughput "
                f"({summary_a.median_tps:.1f} vs {summary_b.median_tps:.1f} tok/s) with {summary_a.assertion_pass_rate:.0f}% assertion match."
            )
        else:
            winner = "tie"
            rec_ru = "Оба провайдера демонстрируют сопоставимую производительность и прошли проверки подлинности."
            rec_en = "Both providers demonstrate comparable performance and passed authenticity checks."

    return ComparisonResult(
        run_a=summary_a,
        run_b=summary_b,
        winner=winner,
        recommendation_ru=rec_ru,
        recommendation_en=rec_en,
        deltas=deltas,
    )


def compare_runs(
    db: Database,
    run_id_a: int,
    run_id_b: int,
) -> ComparisonResult:
    """
    Compares two runs from the database and produces a side-by-side comparative analysis.
    """
    run_a = db.get_run(run_id_a)
    if not run_a:
        raise ValueError(f"Run #{run_id_a} not found in database")
    run_b = db.get_run(run_id_b)
    if not run_b:
        raise ValueError(f"Run #{run_id_b} not found in database")

    target_a = db.get_target(run_a.target_id)
    if not target_a:
        raise ValueError(f"Target '{run_a.target_id}' for run #{run_id_a} not found")
    target_b = db.get_target(run_b.target_id)
    if not target_b:
        raise ValueError(f"Target '{run_b.target_id}' for run #{run_id_b} not found")

    scores_a = db.get_scores(run_id_a)
    samples_a = db.get_run_samples(run_id_a)

    scores_b = db.get_scores(run_id_b)
    samples_b = db.get_run_samples(run_id_b)

    return compare_runs_data(
        target_a=target_a,
        run_a=run_a,
        scores_a=scores_a,
        samples_a=samples_a,
        target_b=target_b,
        run_b=run_b,
        scores_b=scores_b,
        samples_b=samples_b,
    )
