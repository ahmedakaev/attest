"""
Multi-tier Comparator Pipeline.
Executes Level 0 -> Level 1 -> Level 2 -> Level 3 in structured succession.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from attest.comparator.assertion import evaluate_batch_assertions
from attest.comparator.billing import compare_billing
from attest.comparator.distribution import compare_distributions_jsd
from attest.comparator.embedding import compare_semantic_embeddings
from attest.comparator.gateway_limits import (
    find_max_tokens_mismatch,
    gateway_limits_score,
)
from attest.comparator.iris import compare_iris
from attest.comparator.latency import compare_latency_throughput
from attest.comparator.mmd import compute_mmd_permutation
from attest.comparator.quick import run_quick_checks
from attest.config import ThresholdsConfig
from attest.detection.infrastructure import detect_infrastructure
from attest.i18n import build_pipeline_summary_message, format_failure_diagnostics
from attest.models import MethodTier, PromptItem, RawSample, Score, Target, Verdict


@dataclass
class PipelineResult:
    scores: list[Score]
    overall_verdict: Verdict
    summary_message: str
    failure_diagnostics: list[dict[str, Any]] = field(default_factory=list)


class ComparatorPipeline:
    def __init__(self, thresholds: ThresholdsConfig):
        self.thresholds = thresholds

    @staticmethod
    def aggregate_overall_verdict(scores: list[Score]) -> Verdict:
        """Compute aggregate overall verdict from scores, ignoring SKIP and non-behavioral methods."""
        return Verdict.aggregate(scores)

    def execute(
        self,
        target: Target,
        baseline_samples: list[RawSample],
        run_samples: list[RawSample],
        prompts: list[PromptItem],
        run_id: int,
        include_level3_mmd: bool = False,
        locale: str = "ru",
    ) -> PipelineResult:
        prompts_map = {p.id: p for p in prompts if p.id is not None}
        scores: list[Score] = []

        # 0. Gateway max_tokens guard: probes one gateway cut to a single token while
        # the other returned whole words would read as a swap in the checks below
        mismatched = find_max_tokens_mismatch(baseline_samples, run_samples)
        if mismatched:
            scores.append(gateway_limits_score(mismatched, run_id))
        cmp_base = [s for s in baseline_samples if s.prompt_id not in mismatched]
        cmp_run = [s for s in run_samples if s.prompt_id not in mismatched]

        # 1. Level 0: Quick Checks (model, fingerprint, seed determinism)
        quick_scores = run_quick_checks(
            target_model=target.model,
            baseline_samples=cmp_base,
            run_samples=cmp_run,
            prompts_map=prompts_map,
            run_id=run_id,
            all_run_samples=run_samples,
            all_baseline_samples=baseline_samples,
        )
        scores.extend(quick_scores)

        # 1.2 Infrastructure Fingerprinting (Proxy & Cloud Backend)
        infra_fp = detect_infrastructure(raw_samples=run_samples)
        infra_score = Score(
            id=None,
            run_id=run_id,
            method=MethodTier.INFRASTRUCTURE.value,
            scope="aggregate",
            value=infra_fp.confidence,
            threshold=None,
            verdict=Verdict.PASS,
            details=infra_fp.to_dict(),
        )
        scores.append(infra_score)

        # 1.5 Deterministic Assertions (Prompt Rules)
        run_samples_by_prompt: dict[int, list[RawSample]] = {}
        for s in run_samples:
            run_samples_by_prompt.setdefault(s.prompt_id, []).append(s)

        baseline_samples_by_prompt: dict[int, list[RawSample]] = {}
        for s in baseline_samples:
            baseline_samples_by_prompt.setdefault(s.prompt_id, []).append(s)

        assertions_by_prompt = {
            p_id: p.assertions
            for p_id, p in prompts_map.items()
            if getattr(p, "assertions", None)
        }
        if assertions_by_prompt:
            assert_score = evaluate_batch_assertions(
                samples_by_prompt=run_samples_by_prompt,
                assertions_by_prompt=assertions_by_prompt,
                run_id=run_id,
                baseline_samples_by_prompt=baseline_samples_by_prompt,
            )
            if assert_score:
                scores.append(assert_score)

        # 2. Level 1: One-Token JSD Fingerprinting (Core)
        jsd_scores = compare_distributions_jsd(
            baseline_samples=cmp_base,
            run_samples=cmp_run,
            prompts_map=prompts_map,
            run_id=run_id,
            thresholds=self.thresholds,
            target_model=target.model,
        )
        scores.extend(jsd_scores)

        # 2.1. IRIS: random-string fingerprint (substitution & partial routing)
        scores.extend(
            compare_iris(
                baseline_samples=cmp_base,
                run_samples=cmp_run,
                prompts_map=prompts_map,
                run_id=run_id,
                thresholds=self.thresholds,
            )
        )

        # 2.5. Level 1.5: Latency & Throughput (TPS) Drift
        latency_scores = compare_latency_throughput(
            baseline_samples=cmp_base,
            run_samples=cmp_run,
            run_id=run_id,
            thresholds=self.thresholds,
        )
        scores.extend(latency_scores)

        # 2.6. Billing integrity: token over-billing from returned usage (no extra calls)
        scores.extend(
            compare_billing(
                baseline_samples=baseline_samples,
                run_samples=run_samples,
                run_id=run_id,
                thresholds=self.thresholds,
                tokenizer_differs=any(
                    s.method == MethodTier.TOKENIZER.value
                    and s.verdict == Verdict.FAIL
                    and s.details.get("mode") == "baseline"
                    for s in scores
                ),
            )
        )

        # 3. Level 2: 100% Local Text Similarity for capability probes
        embed_scores = compare_semantic_embeddings(
            baseline_samples=cmp_base,
            run_samples=cmp_run,
            prompts_map=prompts_map,
            run_id=run_id,
            thresholds=self.thresholds,
        )
        scores.extend(embed_scores)

        # 4. Level 3: MMD with Permutation Test
        # Trigger if explicitly requested, or if prior checks indicated WARN
        has_warn = any(s.verdict == Verdict.WARN for s in scores)
        if include_level3_mmd or has_warn:
            mmd_scores = compute_mmd_permutation(
                baseline_samples=cmp_base,
                run_samples=cmp_run,
                run_id=run_id,
                thresholds=self.thresholds,
            )
            scores.extend(mmd_scores)

        # 5. Compute Aggregate Overall Verdict (excluding purely informational scores)
        overall = self.aggregate_overall_verdict(scores)

        diagnostics = format_failure_diagnostics(
            scores, prompts_map=prompts_map, locale=locale
        )
        summary = build_pipeline_summary_message(overall, diagnostics, locale=locale)

        return PipelineResult(
            scores=scores,
            overall_verdict=overall,
            summary_message=summary,
            failure_diagnostics=diagnostics,
        )
