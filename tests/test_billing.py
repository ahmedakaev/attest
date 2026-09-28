"""
Tests for the token billing integrity check.
"""

from attest.comparator.billing import compare_billing
from attest.comparator.pipeline import ComparatorPipeline
from attest.config import ThresholdsConfig
from attest.i18n import format_failure_diagnostics
from attest.models import PromptItem, RawSample, Target, Verdict

PROMPT_TOKENS = {1: 20, 2: 60, 3: 150, 4: 400}
ANSWER = "The capital of France is Paris, a city on the Seine river. " * 3


def _samples(
    prompt_fn=lambda pt: pt,
    completion: int = 40,
    reasoning: int | None = None,
    per_prompt: int = 3,
) -> list[RawSample]:
    out = []
    for pid, pt in PROMPT_TOKENS.items():
        for _ in range(per_prompt):
            out.append(
                RawSample(
                    prompt_id=pid,
                    raw_text=ANSWER,
                    latency_ms=500,
                    usage={
                        "prompt_tokens": int(prompt_fn(pt)),
                        "completion_tokens": completion + (reasoning or 0),
                    },
                    reasoning_tokens=reasoning,
                )
            )
    return out


def _score(run: list[RawSample], base: list[RawSample] | None = None):
    base = base if base is not None else _samples()
    return compare_billing(base, run, run_id=1, thresholds=ThresholdsConfig())[0]


def _kinds(score) -> set[str]:
    return {i["kind"] for i in score.details["issues"]}


def test_honest_provider_passes():
    score = _score(_samples())
    assert score.verdict == Verdict.PASS
    assert score.details["issues"] == []
    assert score.details["prompt_tokens"]["scale"] == 1.0
    assert score.details["prompt_tokens"]["overhead_tokens"] == 0.0


def test_small_template_difference_passes():
    # Different gateways wrap the chat template slightly differently
    score = _score(_samples(prompt_fn=lambda pt: pt + 7))
    assert score.verdict == Verdict.PASS


def test_hidden_system_prompt_fails():
    score = _score(_samples(prompt_fn=lambda pt: pt + 300))
    assert score.verdict == Verdict.FAIL
    assert _kinds(score) == {"prompt_overhead"}
    assert abs(score.details["prompt_tokens"]["overhead_tokens"] - 300) < 1


def test_multiplied_input_tokens_fail():
    score = _score(_samples(prompt_fn=lambda pt: pt * 1.25))
    assert score.verdict == Verdict.FAIL
    assert "prompt_scale" in _kinds(score)
    assert abs(score.details["prompt_tokens"]["scale"] - 1.25) < 0.01


def test_slight_input_inflation_warns():
    score = _score(_samples(prompt_fn=lambda pt: pt * 1.08))
    assert score.verdict == Verdict.WARN


def test_inflated_output_tokens_fail():
    score = _score(_samples(completion=52))  # same text, +30% tokens
    assert score.verdict == Verdict.FAIL
    assert _kinds(score) == {"completion"}


def test_reasoning_tokens_are_not_counted_as_output_inflation():
    base = _samples(reasoning=500)
    run = _samples(reasoning=900)  # more thinking, same visible answer billing
    score = _score(run, base)
    assert score.verdict == Verdict.PASS


def test_phantom_reasoning_warns():
    score = _score(_samples(reasoning=250))
    assert score.verdict == Verdict.WARN
    assert _kinds(score) == {"phantom_reasoning"}


def test_no_usage_skips():
    run = [RawSample(prompt_id=1, raw_text=ANSWER, latency_ms=1) for _ in range(5)]
    score = _score(run, [RawSample(prompt_id=1, raw_text=ANSWER, latency_ms=1)])
    assert score.verdict == Verdict.SKIP


def test_single_prompt_attributes_difference_to_overhead():
    base = [s for s in _samples() if s.prompt_id == 2]
    run = [s for s in _samples(prompt_fn=lambda pt: pt + 200) if s.prompt_id == 2]
    score = _score(run, base)
    assert score.details["prompt_tokens"]["fit"] == "median-difference"
    assert "prompt_overhead" in _kinds(score)


def test_billing_in_pipeline_and_diagnostics():
    prompts = [
        PromptItem(
            id=pid,
            category="factual",
            text=f"prompt {pid}",
            params={},
            samples_count=3,
            battery_version="v1",
        )
        for pid in PROMPT_TOKENS
    ]
    result = ComparatorPipeline(ThresholdsConfig()).execute(
        target=Target(id="t", base_url="https://reseller.example/v1", model="gpt-4o"),
        baseline_samples=_samples(),
        run_samples=_samples(prompt_fn=lambda pt: pt + 300),
        prompts=prompts,
        run_id=1,
        locale="ru",
    )
    billing = next(s for s in result.scores if s.method == "billing")
    assert billing.verdict == Verdict.FAIL
    assert result.overall_verdict == Verdict.FAIL

    messages = [
        d["message"]
        for d in format_failure_diagnostics(result.scores, locale="ru")
        if d["method"] == "billing"
    ]
    assert messages and "300" in messages[0]


def test_unreported_reasoning_is_not_read_as_overbilling():
    """OpenRouter reports 20 reasoning tokens; the proxy bills the same 45 in total
    but gives no breakdown. The visible text is billed alike."""
    answer = "x" * 60
    base = [
        RawSample(
            prompt_id=1,
            raw_text=answer,
            usage={"prompt_tokens": 20, "completion_tokens": 45},
            reasoning_tokens=20,
            reasoning_content="thinking",
        )
        for _ in range(4)
    ]
    run = [
        RawSample(
            prompt_id=1,
            raw_text=answer,
            usage={"prompt_tokens": 20, "completion_tokens": 46},
        )
        for _ in range(4)
    ]
    score = compare_billing(base, run, run_id=1, thresholds=ThresholdsConfig())[0]
    assert not [i for i in score.details["issues"] if i["kind"] == "completion"]


def test_provider_ignoring_max_tokens_is_flagged():
    """Real case: cap 1 sent, the reseller billed 4219 tokens; the baseline kept to it."""
    base = [
        RawSample(
            prompt_id=pid,
            raw_text="x",
            usage={"prompt_tokens": 20, "completion_tokens": 1},
            max_tokens_sent=1,
        )
        for pid in range(1, 5)
    ]
    run = [
        RawSample(
            prompt_id=pid,
            raw_text="Hello! " * 20,
            usage={"prompt_tokens": 20, "completion_tokens": billed},
            max_tokens_sent=1,
        )
        for pid, billed in zip(range(1, 5), (44, 73, 4219, 58), strict=True)
    ]
    score = compare_billing(base, run, run_id=1, thresholds=ThresholdsConfig())[0]
    cap = [i for i in score.details["issues"] if i["kind"] == "cap_ignored"]
    assert cap and cap[0]["max_billed"] == 4219 and cap[0]["over"] == 4
    assert score.verdict == Verdict.WARN

    diags = format_failure_diagnostics([score], locale="ru")
    assert any("игнорирует max_tokens" in d["message"] for d in diags)

    # Both sides over the cap: a gateway convention, not this provider's doing
    both = compare_billing(run, run, run_id=1, thresholds=ThresholdsConfig())[0]
    assert not [i for i in both.details["issues"] if i["kind"] == "cap_ignored"]


def test_other_tokenizer_skips_token_comparisons():
    """Real case: Qwen served as GPT-5.6-luna counts 710 input tokens where the GPT
    baseline counted 210. That is another chat template, not a hidden prompt."""
    base = _samples()
    run = _samples(prompt_fn=lambda pt: pt + 55)
    flagged = compare_billing(base, run, run_id=1, thresholds=ThresholdsConfig())[0]
    assert any(i["kind"] == "prompt_overhead" for i in flagged.details["issues"])

    skipped = compare_billing(
        base, run, run_id=1, thresholds=ThresholdsConfig(), tokenizer_differs=True
    )[0]
    assert not skipped.details["issues"]
    assert skipped.details["skipped_token_comparison_other_tokenizer"] is True
