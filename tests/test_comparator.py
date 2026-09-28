import numpy as np

from attest.comparator.distribution import compute_jsd, normalize_token
from attest.comparator.embedding import LocalTextVectorizer
from attest.comparator.mmd import permutation_test
from attest.comparator.pipeline import ComparatorPipeline
from attest.config import ThresholdsConfig
from attest.models import PromptItem, RawSample, Target, Verdict


def test_normalize_token():
    assert normalize_token("  42.  ") == "42"
    assert normalize_token("'Blue'") == "blue"
    assert normalize_token("cat\n") == "cat"
    assert normalize_token('"7"') == "7"


def test_jsd_identical_and_divergent():
    # Identical distributions should have JSD == 0.0
    tokens_base = ["42"] * 30 + ["7"] * 20
    tokens_same = ["42"] * 30 + ["7"] * 20
    jsd_same = compute_jsd(tokens_base, tokens_same)
    assert jsd_same < 0.001

    # Completely different distributions (model substitution)
    tokens_swapped = ["99"] * 30 + ["13"] * 20
    jsd_diff = compute_jsd(tokens_base, tokens_swapped)
    assert jsd_diff > 0.5  # Well above 0.15 failure threshold


def test_local_text_vectorizer():
    vec = LocalTextVectorizer()
    text_a = "def is_palindrome(s: str) -> bool: return s == s[::-1]"
    text_b = "def is_palindrome(s: str) -> bool: return s.lower() == s.lower()[::-1]"
    text_c = "SELECT * FROM users WHERE active = 1 ORDER BY created_at DESC"

    sim_similar = vec.cosine_similarity(text_a, text_b)
    sim_different = vec.cosine_similarity(text_a, text_c)

    assert sim_similar > 0.7
    assert sim_different < 0.3


def test_mmd_and_permutation():
    rng = np.random.default_rng(42)
    # Samples from the same Gaussian distribution
    x = rng.normal(loc=0.0, scale=1.0, size=(20, 3))
    y_same = rng.normal(loc=0.0, scale=1.0, size=(20, 3))

    _mmd_same, p_val_same = permutation_test(x, y_same, n_resamples=100)
    # Cannot reject null hypothesis of sameness (p-value should be high)
    assert p_val_same >= 0.05

    # Samples from a significantly shifted distribution
    y_shifted = rng.normal(loc=5.0, scale=1.0, size=(20, 3))
    _mmd_shifted, p_val_diff = permutation_test(x, y_shifted, n_resamples=100)
    # Reject null hypothesis (p-value close to 0)
    assert p_val_diff <= 0.05


def test_pipeline_execution():
    target = Target(
        id="test-gpt4o", base_url="https://api.openai.com/v1", model="gpt-4o"
    )
    prompts = [
        PromptItem(
            id=1,
            category="one_token",
            text="Pick a number 1-10",
            params={"max_tokens": 5, "temperature": 1.0},
            samples_count=10,
            battery_version="v1",
        ),
        PromptItem(
            id=2,
            category="code",
            text="Write is_palindrome",
            params={"max_tokens": 50, "temperature": 0.0},
            samples_count=1,
            battery_version="v1",
        ),
    ]

    base_samples = [
        RawSample(
            prompt_id=1,
            raw_text=f"{i % 3}",
            latency_ms=100,
            fingerprint="fp_123",
            model_returned="gpt-4o",
            usage={"total_tokens": 15},
            headers={},
        )
        for i in range(10)
    ] + [
        RawSample(
            prompt_id=2,
            raw_text="def is_palindrome(s): return s == s[::-1]",
            latency_ms=200,
            fingerprint="fp_123",
            model_returned="gpt-4o",
            usage={"total_tokens": 40},
            headers={},
        )
    ]

    # Matching run samples
    run_samples_matching = [
        RawSample(
            prompt_id=1,
            raw_text=f"{i % 3}",
            latency_ms=110,
            fingerprint="fp_123",
            model_returned="gpt-4o",
            usage={"total_tokens": 15},
            headers={},
        )
        for i in range(10)
    ] + [
        RawSample(
            prompt_id=2,
            raw_text="def is_palindrome(s): return s == s[::-1]",
            latency_ms=190,
            fingerprint="fp_123",
            model_returned="gpt-4o",
            usage={"total_tokens": 40},
            headers={},
        )
    ]

    pipeline = ComparatorPipeline(thresholds=ThresholdsConfig())
    result = pipeline.execute(
        target=target,
        baseline_samples=base_samples,
        run_samples=run_samples_matching,
        prompts=prompts,
        run_id=1,
        include_level3_mmd=False,
    )

    assert result.overall_verdict == Verdict.PASS


def test_is_compatible_model_name():
    from attest.comparator.quick import check_model_claim, is_compatible_model_name

    # Exact match
    match, _ = is_compatible_model_name("gpt-4o", "gpt-4o")
    assert match is True

    # OpenAI dated snapshots
    match, _ = is_compatible_model_name("gpt-4o", "gpt-4o-2024-08-06")
    assert match is True

    match, _ = is_compatible_model_name("gpt-4o-mini", "gpt-4o-mini-2024-07-18")
    assert match is True

    # Gateway namespace prefixes (e.g. OpenRouter)
    match, _ = is_compatible_model_name("openai/gpt-4o", "gpt-4o-2024-08-06")
    assert match is True

    match, _ = is_compatible_model_name("deepseek-chat", "deepseek/deepseek-chat")
    assert match is True

    # Formatting aliases
    match, _ = is_compatible_model_name(
        "claude-3.5-sonnet", "claude-3-5-sonnet-20241022"
    )
    assert match is True

    # 2026 Frontier Models & router namespaces
    match, _ = is_compatible_model_name("gpt-5.5", "openai/gpt-5.5")
    assert match is True

    match, _ = is_compatible_model_name(
        "claude-fable-5-1", "anthropic/claude-fable-5.1"
    )
    assert match is True

    match, _ = is_compatible_model_name(
        "deepseek-v4.1-flash", "deepseek/deepseek-v4.1-flash"
    )
    assert match is True

    match, _ = is_compatible_model_name("qwen/qwen-3.8-max", "qwen-3.8-max-0902")
    assert match is True

    # Real mismatches (model substitution / spoofing)
    match_spoof, _ = is_compatible_model_name("gpt-5.5", "gpt-4.1")
    assert match_spoof is False

    match_other, _ = is_compatible_model_name("gpt-5", "llama-4-scout")
    assert match_other is False

    # Verify check_model_claim Score
    sample_valid = RawSample(
        prompt_id=1, raw_text="ok", latency_ms=50, model_returned="gpt-4o-2024-08-06"
    )
    score_pass = check_model_claim("gpt-4o", [sample_valid], run_id=1)
    assert score_pass.verdict == Verdict.PASS

    sample_spoof = RawSample(
        prompt_id=1, raw_text="ok", latency_ms=50, model_returned="gpt-4o-mini"
    )
    score_fail = check_model_claim("gpt-4o", [sample_spoof], run_id=1)
    assert score_fail.verdict == Verdict.FAIL


def test_jsd_with_logprobs():
    from attest.comparator.distribution import compare_distributions_jsd

    prompts_map = {
        1: PromptItem(
            id=1,
            category="one_token",
            text="Pick a digit",
            params={"max_tokens": 1, "temperature": 1.0, "logprobs": True},
            samples_count=2,
            battery_version="v1",
        )
    }

    # Baseline with top logprobs
    base_samples = [
        RawSample(
            prompt_id=1,
            raw_text="4",
            latency_ms=100,
            logprobs={"4": -0.22, "7": -1.6, "2": -2.5},
        ),
        RawSample(
            prompt_id=1,
            raw_text="4",
            latency_ms=105,
            logprobs={"4": -0.20, "7": -1.7, "2": -2.4},
        ),
    ]

    # Identical run samples
    run_samples_same = [
        RawSample(
            prompt_id=1,
            raw_text="4",
            latency_ms=95,
            logprobs={"4": -0.21, "7": -1.65, "2": -2.45},
        ),
    ]

    scores_same = compare_distributions_jsd(
        base_samples,
        run_samples_same,
        prompts_map,
        run_id=1,
        thresholds=ThresholdsConfig(),
    )
    assert scores_same[0].verdict == Verdict.PASS
    assert scores_same[0].value < 0.01
    assert "logprobs" in scores_same[0].details["mode"]

    # Divergent run samples (different distribution)
    run_samples_diff = [
        RawSample(
            prompt_id=1,
            raw_text="9",
            latency_ms=95,
            logprobs={"9": -0.15, "8": -1.9, "1": -3.0},
        ),
    ]

    scores_diff = compare_distributions_jsd(
        base_samples,
        run_samples_diff,
        prompts_map,
        run_id=1,
        thresholds=ThresholdsConfig(),
    )
    assert scores_diff[0].verdict == Verdict.FAIL
    assert scores_diff[0].value > 0.4


def test_reasoning_model_jsd_adaptation():
    from attest.comparator.distribution import compare_distributions_jsd

    prompts_map = {
        1: PromptItem(
            id=1,
            category="one_token",
            text="Name random number",
            params={"max_tokens": 1},
            samples_count=1,
            battery_version="v1",
        )
    }
    base_samples = [
        RawSample(
            prompt_id=1,
            raw_text="4",
            latency_ms=100,
            logprobs={"4": -0.2, "7": -1.8, "3": -2.5},
        )
    ]
    # Shifted sample yielding moderate JSD (~0.22)
    run_samples = [
        RawSample(
            prompt_id=1,
            raw_text="7",
            latency_ms=100,
            logprobs={"7": -0.4, "4": -1.2, "8": -2.0},
        )
    ]
    thresholds = ThresholdsConfig(jsd_fail=0.15, reasoning_jsd_fail=0.35)

    # 1. Standard model: JSD ~0.22 > 0.15 fails
    scores_standard = compare_distributions_jsd(
        base_samples,
        run_samples,
        prompts_map,
        run_id=1,
        thresholds=thresholds,
        target_model="gpt-4o",
    )
    assert scores_standard[0].details["is_reasoning_model"] is False
    assert scores_standard[0].verdict in (Verdict.FAIL, Verdict.WARN)

    # 2. Reasoning model: threshold relaxed to 0.35, JSD ~0.22 is WARN, NOT FAIL!
    scores_reasoning = compare_distributions_jsd(
        base_samples,
        run_samples,
        prompts_map,
        run_id=2,
        thresholds=thresholds,
        target_model="gemini-3.7-flash",
    )
    assert scores_reasoning[0].details["is_reasoning_model"] is True
    assert scores_reasoning[0].threshold == 0.35
    assert scores_reasoning[0].verdict != Verdict.FAIL


def test_latency_tps_comparator():
    from attest.comparator.latency import compare_latency_throughput

    thresholds = ThresholdsConfig()

    # --- 1. Normal case: similar latency & TPS → PASS ---
    base_samples = [
        RawSample(
            prompt_id=i,
            raw_text=f"response {i}",
            latency_ms=500,
            usage={"prompt_tokens": 10, "completion_tokens": 50},
        )
        for i in range(10)
    ]
    run_samples_normal = [
        RawSample(
            prompt_id=i,
            raw_text=f"response {i}",
            latency_ms=520,  # ~4% slower — well within threshold
            usage={"prompt_tokens": 10, "completion_tokens": 50},
        )
        for i in range(10)
    ]

    scores = compare_latency_throughput(
        base_samples, run_samples_normal, run_id=1, thresholds=thresholds
    )
    tps_score = next(s for s in scores if s.method == "latency_tps")
    lat_score = next(s for s in scores if s.method == "latency_drift")
    assert tps_score.verdict == Verdict.PASS
    assert lat_score.verdict == Verdict.PASS

    # --- 2. Asymmetric speedup: 3x faster → WARN (high-throughput cluster / fast hardware) ---
    run_samples_fast = [
        RawSample(
            prompt_id=i,
            raw_text=f"response {i}",
            latency_ms=150,  # 3.3x faster
            usage={"prompt_tokens": 10, "completion_tokens": 50},
        )
        for i in range(10)
    ]

    scores_fast = compare_latency_throughput(
        base_samples, run_samples_fast, run_id=2, thresholds=thresholds
    )
    tps_fast = next(s for s in scores_fast if s.method == "latency_tps")
    assert tps_fast.verdict == Verdict.WARN
    assert "faster" in tps_fast.details["direction"]

    # --- 2b. Severe slowdown without TTFT → WARN: end-to-end speed also holds the
    # provider's proxy/network overhead, so it cannot prove a slower model ---
    run_samples_slow = [
        RawSample(
            prompt_id=i,
            raw_text=f"response {i}",
            latency_ms=1200,  # 2.4x slower = ~58% drop
            usage={"prompt_tokens": 10, "completion_tokens": 50},
        )
        for i in range(10)
    ]
    scores_slow = compare_latency_throughput(
        base_samples, run_samples_slow, run_id=22, thresholds=thresholds
    )
    tps_slow = next(s for s in scores_slow if s.method == "latency_tps")
    assert tps_slow.verdict == Verdict.WARN
    assert "slower" in tps_slow.details["direction"]

    # --- 2c. Decode speed itself drops >50% (TTFT on both sides) → FAIL ---
    for smp in base_samples:
        smp.ttft_ms = 100  # 49 tokens in 400 ms
    run_decode_slow = [
        RawSample(
            prompt_id=i,
            raw_text=f"response {i}",
            latency_ms=1100,  # 49 tokens in 1000 ms after the first token
            ttft_ms=100,
            usage={"prompt_tokens": 10, "completion_tokens": 50},
        )
        for i in range(10)
    ]
    scores_decode = compare_latency_throughput(
        base_samples, run_decode_slow, run_id=23, thresholds=thresholds
    )
    tps_decode = next(s for s in scores_decode if s.method == "latency_tps")
    assert tps_decode.details["decode_only"] is True
    assert tps_decode.verdict == Verdict.FAIL

    # --- 3. No usage data → SKIP ---
    bare_samples = [
        RawSample(prompt_id=i, raw_text="x", latency_ms=100) for i in range(5)
    ]
    scores_skip = compare_latency_throughput(
        bare_samples, bare_samples, run_id=3, thresholds=thresholds
    )
    tps_skip = next(s for s in scores_skip if s.method == "latency_tps")
    assert tps_skip.verdict == Verdict.SKIP

    # --- 4. Single-token probe jitter capped at WARN (not FAIL) ---
    base_1tok = [
        RawSample(
            prompt_id=i,
            raw_text="4",
            latency_ms=300,
            usage={"prompt_tokens": 5, "completion_tokens": 1},
        )
        for i in range(6)
    ]
    run_1tok_jitter = [
        RawSample(
            prompt_id=i,
            raw_text="4",
            latency_ms=90,
            usage={"prompt_tokens": 5, "completion_tokens": 1},
        )
        for i in range(6)
    ]
    scores_1tok = compare_latency_throughput(
        base_1tok, run_1tok_jitter, run_id=4, thresholds=thresholds
    )
    tps_1tok = next(s for s in scores_1tok if s.method == "latency_tps")
    # Even though 300ms -> 90ms is >200% speedup, single-token probe must cap at WARN
    assert tps_1tok.verdict == Verdict.WARN
    assert tps_1tok.details["single_token_regime"] is True

    # --- 5. Prompt subset alignment ---
    # Baseline has 5 fast prompts (prompt_id 0..4) and 5 slow prompts (prompt_id 5..9)
    base_mixed = [
        RawSample(
            prompt_id=i,
            raw_text="x",
            latency_ms=100 if i < 5 else 2000,
            usage={"completion_tokens": 10},
        )
        for i in range(10)
    ]
    # Run only executes fast prompts 0..4
    run_subset = [
        RawSample(
            prompt_id=i, raw_text="x", latency_ms=105, usage={"completion_tokens": 10}
        )
        for i in range(5)
    ]
    scores_subset = compare_latency_throughput(
        base_mixed, run_subset, run_id=5, thresholds=thresholds
    )
    tps_subset = next(s for s in scores_subset if s.method == "latency_tps")
    lat_subset = next(s for s in scores_subset if s.method == "latency_drift")
    # Because prompts are aligned, 105ms is compared against 100ms (not against the 2000ms mixed median)
    assert tps_subset.verdict == Verdict.PASS
    assert lat_subset.verdict == Verdict.PASS
    assert lat_subset.details["matched_prompts"] == 5


def test_quick_system_fingerprint():
    from attest.comparator.quick import check_system_fingerprint

    # 1. Matching fingerprints -> PASS
    b_samples = [
        RawSample(prompt_id=1, raw_text="a", latency_ms=100, fingerprint="fp_abc123")
    ]
    r_samples = [
        RawSample(prompt_id=1, raw_text="a", latency_ms=100, fingerprint="fp_abc123")
    ]
    score = check_system_fingerprint(b_samples, r_samples, run_id=1)
    assert score.verdict == Verdict.PASS

    # 2. Changed fingerprint -> WARN
    r_samples_changed = [
        RawSample(prompt_id=1, raw_text="a", latency_ms=100, fingerprint="fp_xyz789")
    ]
    score_warn = check_system_fingerprint(b_samples, r_samples_changed, run_id=2)
    assert score_warn.verdict == Verdict.WARN

    # 3. No fingerprint provided -> SKIP
    b_bare = [RawSample(prompt_id=1, raw_text="a", latency_ms=100, fingerprint=None)]
    r_bare = [RawSample(prompt_id=1, raw_text="a", latency_ms=100, fingerprint=None)]
    score_skip = check_system_fingerprint(b_bare, r_bare, run_id=3)
    assert score_skip.verdict == Verdict.SKIP


def test_quick_seed_determinism():
    from attest.comparator.quick import check_seed_determinism

    prompts_map = {
        1: PromptItem(
            id=1,
            category="factual",
            text="2+2",
            params={"temperature": 0.0},
            samples_count=1,
            battery_version="v1",
        ),
        2: PromptItem(
            id=2,
            category="code",
            text="seed test",
            params={"seed": 42},
            samples_count=1,
            battery_version="v1",
        ),
    }

    # 1. Deterministic match -> PASS
    b_samples = [
        RawSample(prompt_id=1, raw_text="4", latency_ms=100),
        RawSample(prompt_id=2, raw_text="def test(): pass", latency_ms=100),
    ]
    r_samples_match = [
        RawSample(prompt_id=1, raw_text="4", latency_ms=100),
        RawSample(prompt_id=2, raw_text="def test(): pass", latency_ms=100),
    ]
    score_pass = check_seed_determinism(
        b_samples, r_samples_match, prompts_map, run_id=1
    )
    assert score_pass.verdict == Verdict.PASS
    assert score_pass.value == 1.0

    # 2. Divergence -> WARN only: endpoints serving the same model are not
    # byte-identical at temperature 0, so this alone cannot prove a swap
    r_samples_diff = [
        RawSample(prompt_id=1, raw_text="different answer", latency_ms=100),
        RawSample(prompt_id=2, raw_text="completely different code", latency_ms=100),
    ]
    score_fail = check_seed_determinism(
        b_samples, r_samples_diff, prompts_map, run_id=2
    )
    assert score_fail.verdict == Verdict.WARN
    assert score_fail.value == 0.0

    # 3. Reasoning models ignore temperature: their prompts are not compared
    r_reasoning = [
        RawSample(prompt_id=1, raw_text="x", reasoning_content="thinking..."),
        RawSample(prompt_id=2, raw_text="y", reasoning_tokens=30),
    ]
    score_skip = check_seed_determinism(b_samples, r_reasoning, prompts_map, run_id=3)
    assert score_skip.verdict == Verdict.SKIP


def test_reasoning_model_detection_and_false_positives():
    from attest.comparator.distribution import is_reasoning_model
    from attest.utils import is_reasoning_model_name

    positives = [
        "o1",
        "o1-preview",
        "o1-mini",
        "openai/o1-mini",
        "o3",
        "o3-mini",
        "gpt-6",
        "gpt-6-astra",
        "gemini-3.7-flash",
        "gemini-3.8-pro",
        "deepseek-r1",
        "deepseek/deepseek-r1",
        "deepseek-reasoner",
        "claude-3-7-sonnet-thinking",
        "r1",
        "deepseek/r1",
        "test-cot-model",
    ]
    for m in positives:
        assert is_reasoning_model_name(m) is True, f"Failed positive for {m}"
        assert is_reasoning_model(model_name=m) is True, (
            f"Failed distribution is_reasoning_model for {m}"
        )

    negatives = [
        "gpt-4o",
        "gpt-4o-mini",
        "claude-3-5-sonnet",
        "mistral-7b-instruct",
        "polo1-7b",
        "proto12-v2",
        "driver1",
        "mascot",
    ]
    for m in negatives:
        assert is_reasoning_model_name(m) is False, f"False positive detected for {m}"
        assert is_reasoning_model(model_name=m) is False, (
            f"False positive in distribution for {m}"
        )


def test_comparator_and_reporting_package_exports():
    from attest import comparator, reporting

    assert hasattr(comparator, "compare_runs")
    assert hasattr(comparator, "ComparisonResult")
    assert "compare_runs" in comparator.__all__
    assert "ComparisonResult" in comparator.__all__

    assert hasattr(reporting, "print_comparison_report")
    assert "print_comparison_report" in reporting.__all__


def test_rejects_custom_temperature():
    from attest.utils import rejects_custom_temperature

    assert rejects_custom_temperature("o1-preview") is True
    assert rejects_custom_temperature("openai/o1-preview") is True
    assert rejects_custom_temperature("o1-mini") is True
    assert rejects_custom_temperature("o1-mini-2024-09-12") is True
    assert rejects_custom_temperature("gpt-4o") is False
    assert rejects_custom_temperature("o1") is False
    assert rejects_custom_temperature("o3-mini") is False
    assert rejects_custom_temperature(None) is False


def test_ttft_drift_and_decode_tps():
    from attest.comparator.latency import _compute_tps, compare_latency_throughput
    from attest.config import ThresholdsConfig
    from attest.models import RawSample, Verdict

    def s(ttft, latency, tokens=50):
        return RawSample(
            prompt_id=1,
            raw_text="x" * 200,
            latency_ms=latency,
            ttft_ms=ttft,
            usage={"completion_tokens": tokens},
        )

    # Same decode speed (50 tok / 1 s), provider queues 2 s longer before the first token
    base = [s(500, 1500) for _ in range(5)]
    run = [s(2500, 3500) for _ in range(5)]
    scores = {
        sc.method: sc
        for sc in compare_latency_throughput(base, run, 1, ThresholdsConfig())
    }
    assert scores["latency_ttft"].verdict == Verdict.WARN
    assert scores["latency_ttft"].details["direction"] == "slower"
    # Decode-only TPS is unchanged, so the queueing is not reported as a slowdown
    assert scores["latency_tps"].details["decode_only"] is True
    assert scores["latency_tps"].verdict == Verdict.PASS

    # Hidden reasoning tokens were produced before TTFT and are not decode tokens
    thinking = RawSample(
        prompt_id=1,
        raw_text="3",
        latency_ms=3000,
        ttft_ms=2000,
        usage={"completion_tokens": 520},
        reasoning_tokens=500,
    )
    assert _compute_tps(thinking, decode_only=True) == 19.0

    # Old baseline without TTFT -> TTFT check skipped, TPS uses the old formula
    old_base = [s(None, 1500) for _ in range(5)]
    scores = {
        sc.method: sc
        for sc in compare_latency_throughput(old_base, run, 1, ThresholdsConfig())
    }
    assert scores["latency_ttft"].verdict == Verdict.SKIP
    assert scores["latency_tps"].details["decode_only"] is False
