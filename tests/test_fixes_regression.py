"""Regression and edge-case unit tests for verified bug fixes."""

import httpx
import pytest
import respx

from attest.comparator.assertion import evaluate_sample_assertions
from attest.comparator.compare import compare_runs
from attest.comparator.distribution import (
    compare_distributions_jsd,
    normalize_token,
)
from attest.comparator.embedding import compare_semantic_embeddings
from attest.comparator.latency import _compute_tps, compare_latency_throughput
from attest.comparator.mmd import compute_mmd_permutation
from attest.comparator.pipeline import ComparatorPipeline
from attest.config import ThresholdsConfig
from attest.db import Database
from attest.models import (
    MethodTier,
    PromptAssertion,
    PromptItem,
    RawSample,
    RunStatus,
    Score,
    Target,
    Verdict,
)
from attest.sampling.openai_compat import OpenAICompatAdapter


# =============================================================================
# Issue 1: Empty or skipped pipeline audits must NOT return Verdict.PASS
# =============================================================================
def test_empty_or_skipped_pipeline_returns_skip():
    """If no behavioral tests run (all SKIP or only infrastructure present), overall_verdict is SKIP."""
    pipeline = ComparatorPipeline(ThresholdsConfig())
    # 1. Empty scores
    assert pipeline.aggregate_overall_verdict([]) == Verdict.SKIP

    # 2. Only SKIP scores
    skip_scores = [
        Score(
            id=None,
            run_id=1,
            method=MethodTier.ASSERTIONS.value,
            scope="aggregate",
            value=1.0,
            threshold=1.0,
            verdict=Verdict.SKIP,
        ),
        Score(
            id=None,
            run_id=1,
            method=MethodTier.JSD.value,
            scope="aggregate",
            value=0.0,
            threshold=0.15,
            verdict=Verdict.SKIP,
        ),
    ]
    assert pipeline.aggregate_overall_verdict(skip_scores) == Verdict.SKIP

    # 3. Only INFRASTRUCTURE score present with PASS (gateway detection should not declare audit PASS)
    infra_only = [
        Score(
            id=None,
            run_id=1,
            method=MethodTier.INFRASTRUCTURE.value,
            scope="aggregate",
            value=0.9,
            threshold=None,
            verdict=Verdict.PASS,
        )
    ]
    assert pipeline.aggregate_overall_verdict(infra_only) == Verdict.SKIP

    # 4. Behavioral test PASS with INFRASTRUCTURE PASS -> overall PASS
    mixed_pass = [
        Score(
            id=None,
            run_id=1,
            method=MethodTier.ASSERTIONS.value,
            scope="aggregate",
            value=1.0,
            threshold=1.0,
            verdict=Verdict.PASS,
        ),
        Score(
            id=None,
            run_id=1,
            method=MethodTier.INFRASTRUCTURE.value,
            scope="aggregate",
            value=0.9,
            threshold=None,
            verdict=Verdict.PASS,
        ),
    ]
    assert pipeline.aggregate_overall_verdict(mixed_pass) == Verdict.PASS


# =============================================================================
# Issue 2: Provider Battle winner with 0 TPS must not declare B winner
# =============================================================================
def test_compare_runs_0_tps_is_tie(tmp_path):
    """When both runs have equal quality and 0 TPS, compare_runs should declare 'tie'."""
    db_file = tmp_path / "test_0tps_compare.db"
    db = Database(str(db_file))

    db.save_target(Target(id="p-a", base_url="https://api.a.com/v1", model="m1"))
    db.save_target(Target(id="p-b", base_url="https://api.b.com/v1", model="m1"))
    prompts = db.sync_prompts(
        [
            PromptItem(
                id=None,
                category="one_token",
                text="Hello",
                params={},
                samples_count=1,
                battery_version="v1",
            )
        ],
        "v1",
    )
    pid = prompts[0].id
    assert pid is not None

    base_id = db.create_baseline(target_id="p-a", battery_version="v1")

    run_a_id = db.create_run(
        target_id="p-a",
        baseline_id=base_id,
        battery_version="v1",
        status=RunStatus.COMPLETED,
    )
    db.finish_run(run_a_id, status=RunStatus.COMPLETED)
    # Samples with no latency / 0 latency
    db.save_run_samples(
        run_a_id,
        [RawSample(prompt_id=pid, raw_text="ok", latency_ms=0, usage={})],
    )
    db.save_scores(
        [
            Score(
                id=None,
                run_id=run_a_id,
                method="assertions",
                scope="aggregate",
                value=1.0,
                threshold=1.0,
                verdict=Verdict.PASS,
                details={"total_assertions": 1, "passed_assertions": 1},
            )
        ]
    )

    run_b_id = db.create_run(
        target_id="p-b",
        baseline_id=base_id,
        battery_version="v1",
        status=RunStatus.COMPLETED,
    )
    db.finish_run(run_b_id, status=RunStatus.COMPLETED)
    db.save_run_samples(
        run_b_id,
        [RawSample(prompt_id=pid, raw_text="ok", latency_ms=0, usage={})],
    )
    db.save_scores(
        [
            Score(
                id=None,
                run_id=run_b_id,
                method="assertions",
                scope="aggregate",
                value=1.0,
                threshold=1.0,
                verdict=Verdict.PASS,
                details={"total_assertions": 1, "passed_assertions": 1},
            )
        ]
    )

    result = compare_runs(db, run_a_id, run_b_id)
    assert result.winner == "tie"


# =============================================================================
# Issue 3: RawSample.latency_ms nullability & None tolerance
# =============================================================================
def test_latency_ms_none_tolerance():
    """All latency calculations and comparator modules tolerate latency_ms=None without TypeError."""
    # 1. RawSample default
    s_default = RawSample(prompt_id=1, raw_text="text")
    assert s_default.latency_ms == 0

    # 2. Explicit None
    s_none = RawSample(prompt_id=1, raw_text="text", latency_ms=None)
    assert _compute_tps(s_none) is None

    # 3. compare_latency_throughput with latency_ms=None in baseline or run
    s1 = RawSample(
        prompt_id=1, raw_text="text 1", latency_ms=None, usage={"completion_tokens": 10}
    )
    s2 = RawSample(
        prompt_id=1, raw_text="text 2", latency_ms=None, usage={"completion_tokens": 10}
    )
    scores = compare_latency_throughput(
        [s1], [s2], run_id=1, thresholds=ThresholdsConfig()
    )
    assert len(scores) >= 1

    # 4. compute_mmd_permutation with latency_ms=None
    base_samples = [
        RawSample(prompt_id=1, raw_text=f"resp {i}", latency_ms=None) for i in range(5)
    ]
    run_samples = [
        RawSample(prompt_id=1, raw_text=f"resp {i}", latency_ms=None) for i in range(5)
    ]
    mmd_scores = compute_mmd_permutation(
        base_samples, run_samples, run_id=1, thresholds=ThresholdsConfig()
    )
    assert len(mmd_scores) == 1
    assert mmd_scores[0].method == MethodTier.MMD_PERMUTATION.value

    # 5. Assertion latency_ms_max with latency_ms=None
    passed, results = evaluate_sample_assertions(
        s_none, [PromptAssertion(type="latency_ms_max", value=500)]
    )
    assert passed is False
    assert results[0]["passed"] is False


# =============================================================================
# Issue 4: bpe_fingerprint probe category support in JSD & Embedding
# =============================================================================
def test_bpe_fingerprint_category_alignment():
    """bpe_fingerprint category is included in JSD comparator and excluded from Embedding Cosine."""
    prompts_map = {
        1: PromptItem(
            id=1,
            category="bpe_fingerprint",
            text="Pick digit",
            params={"max_tokens": 1},
            samples_count=2,
            battery_version="v1",
        ),
        2: PromptItem(
            id=2,
            category="reasoning",
            text="Explain quantum physics",
            params={},
            samples_count=1,
            battery_version="v1",
        ),
    }

    base_samples = [
        RawSample(prompt_id=1, raw_text="42", latency_ms=100),
        RawSample(prompt_id=1, raw_text="42", latency_ms=100),
        RawSample(prompt_id=2, raw_text="Physics is great", latency_ms=200),
    ]
    run_samples = [
        RawSample(prompt_id=1, raw_text="42", latency_ms=100),
        RawSample(prompt_id=1, raw_text="42", latency_ms=100),
        RawSample(prompt_id=2, raw_text="Physics is awesome", latency_ms=200),
    ]

    # JSD should process prompt 1 (bpe_fingerprint)
    jsd_scores = compare_distributions_jsd(
        base_samples, run_samples, prompts_map, run_id=1, thresholds=ThresholdsConfig()
    )
    assert len(jsd_scores) == 1
    assert jsd_scores[0].verdict != Verdict.SKIP
    assert jsd_scores[0].value == 0.0

    # Embedding should ignore prompt 1 (bpe_fingerprint) and only process prompt 2
    emb_scores = compare_semantic_embeddings(
        base_samples, run_samples, prompts_map, run_id=1, thresholds=ThresholdsConfig()
    )
    assert len(emb_scores) == 1
    assert emb_scores[0].verdict != Verdict.SKIP
    by_cat = emb_scores[0].details.get("by_category", {})
    assert "bpe_fingerprint" not in by_cat
    assert "reasoning" in by_cat


# =============================================================================
# Issue 5: Reasoning model <think> tag stripping
# =============================================================================
def test_reasoning_models_strip_think_tags():
    """normalize_token and is_json assertion strip <think> / <thought> / <reasoning> blocks."""
    # 1. normalize_token with DeepSeek-R1 style output
    text_r1 = (
        "<think>\nThe user wants a random digit.\nI should answer 42.\n</think>\n42."
    )
    assert normalize_token(text_r1) == "42"

    text_thought = "<thought>\nInternal chain of thought\n</thought>\nYes"
    assert normalize_token(text_thought) == "yes"

    text_reasoning = "<reasoning>\nStep 1: compute\n</reasoning>\n7"
    assert normalize_token(text_reasoning) == "7"

    # 2. is_json assertion with reasoning prefix
    json_cot_text = """<think>
Here is my chain of thought. Let's return JSON as requested.
</think>
{"status": "ok", "code": 200}"""
    sample = RawSample(prompt_id=1, raw_text=json_cot_text, latency_ms=150)
    passed, results = evaluate_sample_assertions(
        sample, [PromptAssertion(type="is_json", value=["status", "code"])]
    )
    assert passed is True
    assert results[0]["passed"] is True


# =============================================================================
# Issue 6: OpenAI-compat adapter fallback on 422 Unprocessable Entity
# =============================================================================
@pytest.mark.asyncio
async def test_openai_compat_adapter_fallback_422():
    """OpenAICompatAdapter adapts payload when provider returns 422 (e.g. FastAPI / LiteLLM validation)."""
    adapter = OpenAICompatAdapter(
        base_url="https://mock-proxy.test/v1",
        api_key="test-key",
        model="gpt-4o",
        retry_max=1,
    )

    call_count = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        # First call: reject logprobs with 422
        if "logprobs" in request.read().decode("utf-8"):
            return httpx.Response(
                422,
                json={
                    "detail": [
                        {
                            "loc": ["body", "logprobs"],
                            "msg": "Extra inputs are not permitted",
                            "type": "extra_forbidden",
                        }
                    ]
                },
            )
        # Second call (after stripping logprobs): succeed
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "42"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    with respx.mock(base_url="https://mock-proxy.test/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(side_effect=handle_request)

        sample = await adapter.sample(
            prompt_id=1,
            prompt_text="Hello",
            params={"max_tokens": 1, "logprobs": True, "top_logprobs": 5},
        )

        assert sample.raw_text == "42"
        assert call_count == 2
        assert adapter._rejects_logprobs is True

    await adapter.close()
