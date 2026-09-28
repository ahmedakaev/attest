"""
Tests for the gateway max_tokens mismatch guard.
"""

from attest.comparator.gateway_limits import find_max_tokens_mismatch
from attest.comparator.pipeline import ComparatorPipeline
from attest.config import ThresholdsConfig
from attest.models import PromptItem, RawSample, Target, Verdict

COLORS = ["Cerulean", "Cerulean", "Teal", "Turquoise", "Cerulean"] * 2
PIECES = {"Cerulean": "Cer", "Teal": "Te", "Turquoise": "Te"}


def _sample(pid: int, text: str, tokens: int, latency: int) -> RawSample:
    return RawSample(
        prompt_id=pid,
        raw_text=text,
        latency_ms=latency,
        usage={"prompt_tokens": 14, "completion_tokens": tokens},
    )


def _prompts() -> list[PromptItem]:
    return [
        PromptItem(
            id=1,
            category="one_token",
            text="Name a random color. Reply with one word.",
            params={"max_tokens": 1, "temperature": 1.0},
            samples_count=10,
            battery_version="t",
        )
    ]


def test_detects_truncated_side():
    base = [_sample(1, c, 7, 1000) for c in COLORS]
    run = [_sample(1, PIECES[c], 1, 2000) for c in COLORS]
    found = find_max_tokens_mismatch(base, run)
    assert found[1]["truncated_side"] == "run"

    # Same truncation on both sides, or both whole words: nothing to exclude
    assert find_max_tokens_mismatch(run, run) == {}
    assert find_max_tokens_mismatch(base, base) == {}


def test_truncation_does_not_fail_the_run():
    """gpt-5.6-luna via OpenRouter (whole words) vs a proxy honouring max_tokens=1."""
    base = [_sample(1, c, 7, 1000) for c in COLORS]
    run = [_sample(1, PIECES[c], 1, 2000) for c in COLORS]
    target = Target(id="t", base_url="https://x/v1", model="gpt-5.6-luna")
    result = ComparatorPipeline(ThresholdsConfig()).execute(
        target, base, run, _prompts(), run_id=1, include_level3_mmd=True
    )
    by_method = {s.method: s for s in result.scores}

    assert by_method["gateway_limits"].verdict == Verdict.SKIP
    assert by_method["gateway_limits"].details["excluded_prompts"] == 1
    for method in ("jsd", "latency_tps", "mmd_permutation"):
        assert by_method[method].verdict != Verdict.FAIL, method
    assert result.overall_verdict != Verdict.FAIL


def test_hidden_reasoning_that_ate_the_cap_counts():
    # OpenRouter spent a 16-token minimum on hidden reasoning and returned nothing;
    # the proxy returned one visible token. Both are gateway artefacts.
    base = [
        RawSample(
            prompt_id=7,
            raw_text="",
            usage={"completion_tokens": 16},
            reasoning_tokens=16,
        )
        for _ in range(3)
    ]
    run = [_sample(7, "Hello", 1, 900) for _ in range(3)]
    assert 7 in find_max_tokens_mismatch(base, run)


def test_empty_baseline_answers_are_excluded_and_explained():
    from attest.comparator.gateway_limits import gateway_limits_score

    base = [
        RawSample(prompt_id=9, raw_text="", usage={"completion_tokens": 20})
        for _ in range(8)
    ]
    run = [_sample(9, "73928416", 90, 2000) for _ in range(8)]
    found = find_max_tokens_mismatch(base, run)
    assert found[9]["reason"] == "empty_answers"
    assert found[9]["truncated_side"] == "baseline"
    score = gateway_limits_score(found, run_id=1)
    assert score.details["empty_baseline_prompts"] == 1
    assert "Recapture the baseline" in score.details["message"]
