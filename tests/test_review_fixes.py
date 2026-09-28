"""
Regression tests for detection false positives/negatives and adapter stealth.
"""

import random
from pathlib import Path

import httpx
import pytest
import respx

from attest.battery.loader import load_battery
from attest.comparator.assertion import evaluate_sample_assertions
from attest.comparator.distribution import compare_distributions_jsd
from attest.comparator.mmd import compute_mmd_permutation
from attest.config import ThresholdsConfig
from attest.models import PromptAssertion, PromptItem, RawSample, Verdict
from attest.sampling.openai_compat import OpenAICompatAdapter

PROMPTS = {
    1: PromptItem(
        id=1,
        category="one_token",
        text="Name a random number between 1 and 100.",
        params={"max_tokens": 1},
        samples_count=50,
        battery_version="v1",
    )
}


def _sample(text: str, logprobs: dict | None = None) -> RawSample:
    return RawSample(prompt_id=1, raw_text=text, latency_ms=100, logprobs=logprobs)


def _jsd(base: list[RawSample], run: list[RawSample]):
    return compare_distributions_jsd(base, run, PROMPTS, 1, ThresholdsConfig())[0]


def _draw(rng: random.Random, weights: list[float], k: int = 50) -> list[RawSample]:
    values = [str(i) for i in range(1, len(weights) + 1)]
    return [_sample(v) for v in rng.choices(values, weights=weights, k=k)]


def test_empirical_jsd_same_model_wide_answer_space_passes():
    # Uncorrected plug-in JSD for this distribution is ~0.22 (FAIL in ~94% of runs)
    rng = random.Random(7)
    weights = [1 / (i**1.5) for i in range(1, 101)]
    verdicts = [
        _jsd(_draw(rng, weights), _draw(rng, weights)).verdict for _ in range(20)
    ]
    assert Verdict.FAIL not in verdicts


def test_empirical_jsd_different_model_still_fails():
    rng = random.Random(7)
    weights = [1 / (i**1.5) for i in range(1, 101)]
    score = _jsd(_draw(rng, weights), _draw(rng, list(reversed(weights))))
    assert score.verdict == Verdict.FAIL
    cell = score.details["cells"][0]
    assert cell["raw_jsd"] > cell["jsd"] > 0.15
    assert cell["p_value"] < 0.01


def test_jsd_mixed_logprob_modes_fall_back_to_empirical():
    # Reference returns first-token logprobs ('Par'), reseller does not ('Paris')
    base = [_sample("Paris", {"Par": -0.1, "Lon": -2.5}) for _ in range(20)]
    run = [_sample("Paris") for _ in range(20)]
    score = _jsd(base, run)
    assert score.verdict == Verdict.PASS
    assert score.value == 0.0
    assert score.details["cells"][0]["used_logprobs"] is False


def test_jsd_empty_answers_skip_instead_of_pass():
    # Reasoning models burn max_tokens=1 on hidden thinking and return no content
    score = _jsd([_sample("") for _ in range(20)], [_sample("") for _ in range(20)])
    assert score.verdict == Verdict.SKIP
    assert score.details["skipped_cells"][0]["reason"] == "empty_output"


def test_mmd_ignores_latency_and_unmatched_prompts():
    def mk(pid: int, text: str, latency: int) -> RawSample:
        return RawSample(
            prompt_id=pid,
            raw_text=text,
            latency_ms=latency,
            usage={"completion_tokens": None},
        )

    texts = [f"answer number {i} " * (1 + i % 4) for i in range(20)]
    base = [mk(1, t, 200) for t in texts] + [mk(2, "x" * 3000, 200) for _ in range(20)]
    # Same responses from a provider 10x farther away; prompt 2 not in this battery
    run = [mk(1, t, 2000) for t in texts]

    score = compute_mmd_permutation(
        base, run, run_id=1, thresholds=ThresholdsConfig(), n_resamples=100
    )[0]
    assert score.verdict == Verdict.PASS
    assert score.details["baseline_count"] == 20


def _ok_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": "hi"}}]}
    )


@pytest.mark.asyncio
async def test_adapter_does_not_identify_itself():
    adapter = OpenAICompatAdapter(
        base_url="https://reseller.example/v1", model="gpt-4o", api_key="test-token"
    )
    with respx.mock(base_url="https://reseller.example/v1") as mock:
        route = mock.post("/chat/completions").mock(side_effect=_ok_response)
        await adapter.sample(1, "hello", {})
        headers = route.calls[0].request.headers
    await adapter.close()

    assert "attest" not in headers.get("user-agent", "").lower()
    assert not any("openrouter" in k.lower() for k in headers)


@pytest.mark.asyncio
async def test_adapter_retry_max_counts_retries():
    adapter = OpenAICompatAdapter(
        base_url="https://mock.api/v1",
        model="gpt-4o",
        api_key="test-token",
        retry_max=1,
        retry_backoff=0.1,
    )
    with respx.mock(base_url="https://mock.api/v1") as mock:
        route = mock.post("/chat/completions").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
            ]
        )
        sample = await adapter.sample(1, "hello", {})
        assert route.call_count == 2
    await adapter.close()
    assert sample.raw_text == "ok"


@pytest.mark.parametrize(
    "assertion",
    [
        "{type: contain, value: x}",
        "{type: latency_ms_max, value: fast}",
        "{type: regex, value: '(unclosed'}",
    ],
)
def test_battery_rejects_malformed_assertions(tmp_path: Path, assertion: str):
    battery = tmp_path / "bad.yaml"
    battery.write_text(
        f"version: t\nprompts:\n  - text: hi\n    assert:\n      - {assertion}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="index 0"):
        load_battery(battery)


def test_unknown_assertion_type_is_not_green():
    passed, results = evaluate_sample_assertions(
        _sample("anything"), [PromptAssertion(type="contain", value="x")]
    )
    assert passed is False
    assert results[0]["passed"] is False
