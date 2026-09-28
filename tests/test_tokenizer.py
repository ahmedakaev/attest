"""Unit tests for BPE tokenizer profiling and model family verification."""

from attest.detection.tokenizer import (
    check_tokenizer_fingerprint,
    extract_observed_bpe_deltas,
    identify_tokenizer_family,
    is_compatible_tokenizer,
)
from attest.models import PromptItem, RawSample, Verdict


def test_identify_tokenizer_family_o200k():
    # Canonical o200k deltas: 10, 17, 11
    observed = {
        "probe_spaces_unicode": 10,
        "probe_code_signature": 17,
        "probe_emojis": 11,
    }
    profile = identify_tokenizer_family(observed)
    assert profile.detected_family == "o200k"
    assert profile.confidence == 1.0
    assert "OpenAI o200k_base" in profile.message


def test_identify_tokenizer_family_cl100k():
    # Canonical cl100k deltas: 16, 19, 17
    observed = {
        "probe_spaces_unicode": 16,
        "probe_code_signature": 19,
        "probe_emojis": 17,
    }
    profile = identify_tokenizer_family(observed)
    assert profile.detected_family == "cl100k"
    assert profile.confidence == 1.0
    assert "OpenAI cl100k_base" in profile.message


def test_identify_tokenizer_family_llama3():
    # Canonical llama3 deltas: 13, 18, 15
    observed = {
        "probe_spaces_unicode": 13,
        "probe_code_signature": 18,
        "probe_emojis": 15,
    }
    profile = identify_tokenizer_family(observed)
    assert profile.detected_family == "llama3"
    assert profile.confidence == 1.0


def test_is_compatible_tokenizer():
    # GPT-5 / GPT-4o with o200k -> Compatible
    is_match, reason = is_compatible_tokenizer("gpt-5.6-sol", "o200k")
    assert is_match is True
    assert "matches claimed model" in reason

    # GPT-4o with Llama-3 -> Incompatible (Spoofing!)
    is_match, reason = is_compatible_tokenizer("gpt-4o", "llama3")
    assert is_match is False
    assert "Tokenizer mismatch" in reason


def test_extract_observed_bpe_deltas_with_prompts():
    prompts_map = {
        10: PromptItem(
            id=10,
            category="tokenizer_probe",
            text="Hello",
            params={"probe_key": "probe_anchor"},
            samples_count=1,
            battery_version="v1",
        ),
        11: PromptItem(
            id=11,
            category="tokenizer_probe",
            text="Hello   hello_world  🚀 \n\t\n привет мир ",
            params={"probe_key": "probe_spaces_unicode"},
            samples_count=1,
            battery_version="v1",
        ),
        12: PromptItem(
            id=12,
            category="tokenizer_probe",
            text="Hello def calculate_total_amount(items: list[dict[str, Any]]) -> float: pass",
            params={"probe_key": "probe_code_signature"},
            samples_count=1,
            battery_version="v1",
        ),
        13: PromptItem(
            id=13,
            category="tokenizer_probe",
            text="Hello 🧮⚡️🚀🌟✨",
            params={"probe_key": "probe_emojis"},
            samples_count=1,
            battery_version="v1",
        ),
    }

    # Emulate o200k token counts (base=7)
    samples = [
        RawSample(prompt_id=10, raw_text=".", usage={"prompt_tokens": 7}),
        RawSample(
            prompt_id=11, raw_text=".", usage={"prompt_tokens": 17}
        ),  # delta = 10
        RawSample(
            prompt_id=12, raw_text=".", usage={"prompt_tokens": 24}
        ),  # delta = 17
        RawSample(
            prompt_id=13, raw_text=".", usage={"prompt_tokens": 18}
        ),  # delta = 11
    ]

    deltas = extract_observed_bpe_deltas(samples, prompts_map=prompts_map)
    assert deltas["probe_spaces_unicode"] == 10
    assert deltas["probe_code_signature"] == 17
    assert deltas["probe_emojis"] == 11

    # Check score for claimed gpt-5.6-sol
    score_pass = check_tokenizer_fingerprint(
        "gpt-5.6-sol", samples, prompts_map=prompts_map
    )
    assert score_pass.verdict == Verdict.PASS
    assert score_pass.value == 1.0
    assert score_pass.details["detected_family"] == "o200k"

    # Check score if claimed gpt-4 (cl100k) but tokenized with o200k -> FAIL
    score_fail = check_tokenizer_fingerprint("gpt-4", samples, prompts_map=prompts_map)
    assert score_fail.verdict == Verdict.FAIL
    assert score_fail.value == 0.0


def test_check_tokenizer_skip_when_no_probes():
    samples = [RawSample(prompt_id=1, raw_text="test", usage={"prompt_tokens": 5})]
    score = check_tokenizer_fingerprint("gpt-5.6", samples, prompts_map={})
    assert score.verdict == Verdict.SKIP


def test_tokenizer_verdict_is_relative_to_the_baseline():
    """Real case: Qwen 3.8 via OpenRouter and via a reseller tokenized identically
    (62/72/79/76) but the static table calls that o200k; the baseline decides."""
    from attest.battery.loader import load_battery
    from attest.detection.tokenizer import check_tokenizer_fingerprint
    from attest.models import RawSample, Verdict

    _v, prompts = load_battery("batteries/tokenizer.yaml")
    prompts_map = {i + 1: p for i, p in enumerate(prompts)}
    for pid, p in prompts_map.items():
        p.id = pid

    def samples(counts):
        return [
            RawSample(prompt_id=pid, raw_text="", usage={"prompt_tokens": n})
            for pid, n in zip(prompts_map, counts, strict=True)
        ]

    same = check_tokenizer_fingerprint(
        "qwen3.8-flash",
        samples([62, 72, 79, 76]),
        prompts_map,
        1,
        baseline_samples=samples([62, 72, 79, 76]),
    )
    assert same.verdict == Verdict.PASS and same.details["mode"] == "baseline"

    swapped = check_tokenizer_fingerprint(
        "qwen3.8-flash",
        samples([62, 78, 90, 84]),
        prompts_map,
        1,
        baseline_samples=samples([62, 72, 79, 76]),
    )
    assert swapped.verdict == Verdict.FAIL
