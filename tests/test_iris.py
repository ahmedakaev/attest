"""
Tests for the IRIS random-string fingerprint check.
"""

import random

from attest.battery.loader import load_battery
from attest.comparator.iris import compare_iris, normalize_answer
from attest.comparator.pipeline import ComparatorPipeline
from attest.config import ThresholdsConfig
from attest.i18n import format_failure_diagnostics
from attest.models import PromptItem, RawSample, Target, Verdict

PROMPTS = {
    pid: PromptItem(
        id=pid,
        category="iris",
        text=f"probe {pid}",
        params={},
        samples_count=8,
        battery_version="t",
    )
    for pid in range(1, 6)
}


def _real_model(rng: random.Random) -> str:
    # Habit: strongly prefers 7 and 3, never starts with 0
    first = rng.choice("123456789")
    rest = "".join(rng.choice("7777733339") for _ in range(7))
    return first + rest


def _substitute(rng: random.Random) -> str:
    # Different habit: prefers low digits and starts with 0
    return "0" + "".join(rng.choice("0012") for _ in range(7))


def _samples(
    per_prompt: int, seed: int, substitute_share: float = 0.0
) -> list[RawSample]:
    rng = random.Random(seed)
    out = []
    for pid in PROMPTS:
        for _ in range(per_prompt):
            gen = _substitute if rng.random() < substitute_share else _real_model
            out.append(RawSample(prompt_id=pid, raw_text=gen(rng)))
    return out


def _score(run: list[RawSample]):
    base = _samples(per_prompt=8, seed=1)
    scores = compare_iris(base, run, PROMPTS, run_id=1, thresholds=ThresholdsConfig())
    assert len(scores) == 1
    return scores[0]


def test_normalize_answer():
    assert normalize_answer(" 4 7-1, 9. ") == "4719"
    assert normalize_answer("`hTh`") == "HTH"
    assert normalize_answer("") == ""


def test_same_model_passes():
    score = _score(_samples(per_prompt=8, seed=2))
    assert score.verdict == Verdict.PASS
    assert score.details["dilution_lower_bound"] < 0.2


def test_full_substitution_fails():
    score = _score(_samples(per_prompt=8, seed=3, substitute_share=1.0))
    assert score.verdict == Verdict.FAIL
    assert score.details["dilution_lower_bound"] > 0.8


def test_partial_routing_detected_and_estimated():
    score = _score(_samples(per_prompt=8, seed=4, substitute_share=0.4))
    assert score.verdict == Verdict.FAIL
    assert 0.2 <= score.details["dilution_lower_bound"] <= 0.6


def test_unseen_answer_length_is_a_tell():
    run = [RawSample(prompt_id=pid, raw_text="12") for pid in PROMPTS for _ in range(8)]
    assert _score(run).details["tells"] == 40


def test_empty_answers_and_small_baseline_skip():
    run = [RawSample(prompt_id=pid, raw_text="") for pid in PROMPTS for _ in range(8)]
    assert _score(run).verdict == Verdict.SKIP

    small_base = _samples(per_prompt=3, seed=1)
    scores = compare_iris(
        small_base, _samples(8, 2), PROMPTS, run_id=1, thresholds=ThresholdsConfig()
    )
    assert scores[0].verdict == Verdict.SKIP


def test_no_iris_prompts_is_silent():
    prompts = {
        1: PromptItem(
            id=1,
            category="factual",
            text="q",
            params={},
            samples_count=1,
            battery_version="t",
        )
    }
    assert compare_iris([], [], prompts, run_id=1, thresholds=ThresholdsConfig()) == []


def test_iris_in_pipeline_and_diagnostics():
    base = _samples(per_prompt=8, seed=1)
    run = _samples(per_prompt=8, seed=5, substitute_share=1.0)
    target = Target(id="t", base_url="https://x/v1", model="m")
    result = ComparatorPipeline(ThresholdsConfig()).execute(
        target, base, run, list(PROMPTS.values()), run_id=1
    )
    iris = [s for s in result.scores if s.method == "iris"]
    assert iris and iris[0].verdict == Verdict.FAIL
    # iris prompts must not leak into the semantic-similarity check
    for s in result.scores:
        if s.method == "embedding_cosine":
            assert s.verdict in (Verdict.SKIP, Verdict.PASS)

    diags = format_failure_diagnostics(result.scores, locale="ru")
    assert any("случайных строк" in d["message"] for d in diags)


def test_iris_battery_loads():
    version, prompts = load_battery("batteries/iris.yaml")
    assert version == "iris-2026"
    assert all(p.category == "iris" for p in prompts)
    assert sum(p.samples_count for p in prompts) == 40
