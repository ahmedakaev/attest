"""
BPE Tokenizer Profiling Module.

Provides ultra-low-cost, instant model family identification by matching
token count signatures (usage.prompt_tokens delta) against canonical BPE vocabularies
(o200k_base for GPT-4o/GPT-5, cl100k_base for GPT-4/GPT-3.5, Llama-3, Qwen-2, DeepSeek).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from attest.models import MethodTier, RawSample, Score, Verdict


@dataclass
class TokenizerSignature:
    family: str
    expected_overhead: int  # Standard chat formatting overhead tokens
    deltas: dict[str, int]  # Diagnostic phrase id -> expected delta token count


# Precomputed ground-truth token deltas for standardized diagnostic probes
CANONICAL_SIGNATURES: dict[str, dict[str, int]] = {
    "o200k": {
        "probe_spaces_unicode": 10,
        "probe_code_signature": 17,
        "probe_emojis": 11,
    },
    "cl100k": {
        "probe_spaces_unicode": 16,
        "probe_code_signature": 19,
        "probe_emojis": 17,
    },
    "llama3": {
        "probe_spaces_unicode": 13,
        "probe_code_signature": 18,
        "probe_emojis": 15,
    },
    "qwen2": {
        "probe_spaces_unicode": 11,
        "probe_code_signature": 17,
        "probe_emojis": 14,
    },
}

# Mapping of model family names to expected tokenizer
EXPECTED_MODEL_TOKENIZERS: dict[str, list[str]] = {
    "gpt-5": ["o200k"],
    "gpt-5.6": ["o200k"],
    "gpt-4o": ["o200k"],
    "gpt-4o-mini": ["o200k"],
    "o1": ["o200k"],
    "o3": ["o200k"],
    "gpt-4": ["cl100k"],
    "gpt-3.5": ["cl100k"],
    "llama-3": ["llama3"],
    "llama-3.1": ["llama3"],
    "llama-3.3": ["llama3"],
    "qwen": ["qwen2"],
    "qwen-2.5": ["qwen2"],
    "deepseek": ["deepseek", "cl100k", "qwen2"],
}


@dataclass
class TokenizerProfile:
    detected_family: str
    confidence: float
    matched_probes: int
    total_probes: int
    observed_deltas: dict[str, int]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected_family": self.detected_family,
            "confidence": round(self.confidence, 2),
            "matched_probes": self.matched_probes,
            "total_probes": self.total_probes,
            "observed_deltas": self.observed_deltas,
            "message": self.message,
        }


def identify_tokenizer_family(observed_deltas: dict[str, int]) -> TokenizerProfile:
    """
    Matches observed token deltas against known BPE tokenizer vocabularies.
    """
    if not observed_deltas:
        return TokenizerProfile(
            detected_family="unknown",
            confidence=0.0,
            matched_probes=0,
            total_probes=0,
            observed_deltas={},
            message="No diagnostic tokenizer probes observed in run",
        )

    best_family = "unknown"
    best_matches = 0
    total = len(observed_deltas)

    for family, sigs in CANONICAL_SIGNATURES.items():
        matches = 0
        for probe_key, delta in observed_deltas.items():
            if sigs.get(probe_key) == delta:
                matches += 1
        if matches > best_matches:
            best_matches = matches
            best_family = family

    confidence = best_matches / max(1, total) if total > 0 else 0.0
    names = {
        "o200k": "OpenAI o200k_base (GPT-4o / GPT-5 series)",
        "cl100k": "OpenAI cl100k_base (GPT-4 / GPT-3.5 legacy)",
        "llama3": "Meta Llama 3/3.1/3.3 (128k BPE)",
        "qwen2": "Qwen 2/2.5 BPE (152k)",
        "unknown": "Unknown / Non-standard vocabulary",
    }
    msg = f"Detected {names.get(best_family, best_family)} ({best_matches}/{total} signatures matched)"

    return TokenizerProfile(
        detected_family=best_family,
        confidence=confidence,
        matched_probes=best_matches,
        total_probes=total,
        observed_deltas=observed_deltas,
        message=msg,
    )


def is_compatible_tokenizer(
    claimed_model: str, detected_family: str
) -> tuple[bool, str]:
    """
    Validates if the detected tokenizer family matches the claimed model architecture.
    """
    if detected_family == "unknown":
        return True, "Tokenizer family could not be uniquely determined"

    clean_model = claimed_model.strip().lower()
    matched_key = None
    for model_key in EXPECTED_MODEL_TOKENIZERS:
        if model_key in clean_model:
            matched_key = model_key
            break

    if not matched_key:
        return True, f"No strict tokenizer rule for model '{claimed_model}'"

    expected_fams = EXPECTED_MODEL_TOKENIZERS[matched_key]
    if detected_family in expected_fams:
        return (
            True,
            f"Tokenizer '{detected_family}' matches claimed model family '{matched_key}'",
        )

    return False, (
        f"Tokenizer mismatch: model '{claimed_model}' requires tokenizer {expected_fams}, "
        f"but backend tokenized with '{detected_family}'"
    )


PROBE_ANCHOR_TEXT = "Hello"
PROBE_PHRASES: dict[str, str] = {
    "probe_spaces_unicode": "Hello   hello_world  🚀 \n\t\n привет мир ",
    "probe_code_signature": "Hello def calculate_total_amount(items: list[dict[str, Any]]) -> float: pass",
    "probe_emojis": "Hello 🧮⚡️🚀🌟✨",
}


def extract_observed_bpe_deltas(
    samples: list[RawSample],
    prompts_map: dict[int, Any] | None = None,
    base_sample: RawSample | None = None,
) -> dict[str, int]:
    """
    Extracts token count deltas from samples that match standardized diagnostic phrases.
    Uses prompts_map to resolve prompt texts or probe_key in params.
    """
    observed: dict[str, int] = {}
    p_map = prompts_map or {}

    # 1. Resolve anchor prompt_id ('Hello')
    anchor_pid = None
    for pid, p in p_map.items():
        text = getattr(p, "text", "")
        params = getattr(p, "params", {}) or {}
        if (
            text.strip() == PROBE_ANCHOR_TEXT
            or params.get("probe_key") == "probe_anchor"
        ):
            anchor_pid = pid
            break

    base_pt = None
    if base_sample and base_sample.usage and "prompt_tokens" in base_sample.usage:
        base_pt = base_sample.usage["prompt_tokens"]
    elif anchor_pid is not None:
        for s in samples:
            if s.prompt_id == anchor_pid and s.usage and "prompt_tokens" in s.usage:
                base_pt = s.usage["prompt_tokens"]
                break

    # 2. Resolve diagnostic probe keys from prompts_map
    probe_pid_to_key: dict[int, str] = {}
    for pid, p in p_map.items():
        text = getattr(p, "text", "").strip()
        params = getattr(p, "params", {}) or {}
        key = params.get("probe_key")
        if not key:
            for k, expected_text in PROBE_PHRASES.items():
                if text == expected_text.strip():
                    key = k
                    break
        if key and key != "probe_anchor":
            probe_pid_to_key[pid] = key

    for s in samples:
        if not s.usage or "prompt_tokens" not in s.usage:
            continue
        pt = s.usage["prompt_tokens"]
        key = probe_pid_to_key.get(s.prompt_id)
        if key:
            observed[key] = (pt - base_pt) if base_pt else pt

    return observed


# Delta tolerance, in tokens, before two tokenizers count as different
BASELINE_DELTA_TOLERANCE = 1


def check_tokenizer_fingerprint(
    claimed_model: str,
    run_samples: list[RawSample],
    prompts_map: dict[int, Any] | None = None,
    run_id: int = 0,
    baseline_samples: list[RawSample] | None = None,
) -> Score:
    """
    Level 0: Evaluates BPE tokenizer spectrum from prompt token usages.

    With baseline samples for the same probes the verdict is relative: the provider
    must tokenize like the reference endpoint. The static family table is kept as
    information only, since it cannot follow every new model (it labelled Qwen 3.8
    on OpenRouter itself as o200k).
    """
    deltas = extract_observed_bpe_deltas(run_samples, prompts_map=prompts_map)
    base_deltas = (
        extract_observed_bpe_deltas(baseline_samples, prompts_map=prompts_map)
        if baseline_samples
        else {}
    )
    common = sorted(set(deltas) & set(base_deltas))
    if deltas and common:
        profile = identify_tokenizer_family(deltas)
        diffs = {k: deltas[k] - base_deltas[k] for k in common}
        same = all(abs(d) <= BASELINE_DELTA_TOLERANCE for d in diffs.values())
        return Score(
            id=None,
            run_id=run_id,
            method=MethodTier.TOKENIZER.value,
            scope="aggregate",
            value=1.0 if same else 0.0,
            threshold=0.8,
            verdict=Verdict.PASS if same else Verdict.FAIL,
            details={
                **profile.to_dict(),
                "claimed_model": claimed_model,
                "mode": "baseline",
                "baseline_deltas": {k: base_deltas[k] for k in common},
                "run_deltas": {k: deltas[k] for k in common},
                "is_compatible": same,
                "reason": (
                    "Tokenizes exactly like the baseline endpoint"
                    if same
                    else "Tokenizes differently from the baseline endpoint: "
                    + ", ".join(f"{k} {d:+d}" for k, d in diffs.items() if d)
                ),
            },
        )
    # No baseline for these probes: fall back to the static family table
    if not deltas:
        return Score(
            id=None,
            run_id=run_id,
            method=MethodTier.TOKENIZER.value
            if hasattr(MethodTier, "TOKENIZER")
            else "tokenizer",
            scope="aggregate",
            value=1.0,
            threshold=1.0,
            verdict=Verdict.SKIP,
            details={
                "message": "No BPE tokenizer diagnostic probes present in this test run"
            },
        )

    profile = identify_tokenizer_family(deltas)
    is_match, reason = is_compatible_tokenizer(claimed_model, profile.detected_family)

    verdict = Verdict.PASS if is_match else Verdict.FAIL
    val = profile.confidence if is_match else 0.0

    return Score(
        id=None,
        run_id=run_id,
        method=MethodTier.TOKENIZER.value
        if hasattr(MethodTier, "TOKENIZER")
        else "tokenizer",
        scope="aggregate",
        value=val,
        threshold=0.8,
        verdict=verdict,
        details={
            **profile.to_dict(),
            "claimed_model": claimed_model,
            "is_compatible": is_match,
            "reason": reason,
        },
    )
