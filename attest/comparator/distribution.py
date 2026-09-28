"""
Level 1: One-Token Behavioral Fingerprinting via Jensen-Shannon Divergence.
Compares single-token answer distributions between a baseline and an audit run.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import numpy as np
from scipy.spatial.distance import jensenshannon

from attest.config import ThresholdsConfig
from attest.models import MethodTier, PromptItem, RawSample, Score, Verdict
from attest.utils import is_reasoning_model_name


def normalize_token(text: str) -> str:
    """Extract and normalize the core single-token answer."""
    # Strip thinking / reasoning tags first (e.g. DeepSeek-R1 / QwQ <think>...</think>)
    clean = (
        re.sub(
            r"<(?:think|thought|reasoning)>.*?</(?:think|thought|reasoning)>",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        .strip()
        .lower()
    )
    # Strip whitespace, quotes, markdown formatting, trailing punctuation
    clean = re.sub(r"^[`'\"]+|[`'\"]+$", "", clean)
    clean = clean.strip(" .,!?:;\n\r\t")
    # If the response is e.g. "42." -> "42"
    match = re.match(r"^([^\s,.:;!]+)", clean)
    if match:
        return match.group(1)
    return clean or "<empty>"


def extract_sample_distribution(
    sample: RawSample, use_logprobs: bool = True
) -> dict[str, float]:
    """
    Extract token probability distribution from a single sample.
    Uses true logprobs if available and allowed (p = exp(logprob)), else 1.0 on normalized text.
    """
    if use_logprobs and sample.logprobs and isinstance(sample.logprobs, dict):
        dist: dict[str, float] = {}
        for tok, lp in sample.logprobs.items():
            norm_tok = normalize_token(tok)
            try:
                prob = float(np.exp(float(lp)))
                dist[norm_tok] = dist.get(norm_tok, 0.0) + prob
            except (OverflowError, ValueError):
                pass
        total = sum(dist.values())
        if total > 0:
            return {t: p / total for t, p in dist.items()}

    # Fallback to normalized sampled text
    norm = normalize_token(sample.raw_text)
    return {norm: 1.0}


def build_aggregated_distribution(
    samples: list[RawSample], vocabulary: set[str], use_logprobs: bool = True
) -> np.ndarray:
    """Build probability distribution array over a shared vocabulary by averaging sample distributions."""
    if not samples or not vocabulary:
        return np.ones(max(len(vocabulary), 1)) / max(len(vocabulary), 1)

    vocab_sorted = sorted(vocabulary)
    acc: dict[str, float] = {t: 0.0 for t in vocab_sorted}

    for s in samples:
        s_dist = extract_sample_distribution(s, use_logprobs)
        for t, prob in s_dist.items():
            if t in acc:
                acc[t] += prob

    total = sum(acc.values())
    if total <= 0:
        return np.ones(len(vocab_sorted)) / len(vocab_sorted)

    return np.array([acc[t] / total for t in vocab_sorted], dtype=np.float64)


def build_distribution(tokens: list[str], vocabulary: set[str]) -> np.ndarray:
    """Build empirical probability distribution array over a shared vocabulary from token list."""
    if not tokens:
        return np.ones(len(vocabulary)) / max(len(vocabulary), 1)

    counts = Counter(tokens)
    total = sum(counts.values())
    vocab_sorted = sorted(vocabulary)
    return np.array(
        [counts.get(token, 0) / total for token in vocab_sorted], dtype=np.float64
    )


def compute_jsd(tokens_a: list[str], tokens_b: list[str]) -> float:
    """
    Computes exact Jensen-Shannon Divergence between two sets of token answers.
    Bounded in [0, 1] using base 2.
    """
    if not tokens_a or not tokens_b:
        return 1.0

    vocab = set(tokens_a) | set(tokens_b)
    if len(vocab) == 1:
        return 0.0

    p = build_distribution(tokens_a, vocab)
    q = build_distribution(tokens_b, vocab)

    js_dist = jensenshannon(p, q, base=2)
    jsd_val = float(js_dist**2)
    return max(0.0, min(1.0, jsd_val))


EMPTY_TOKEN = "<empty>"
# A probe cell is unusable when most responses carry no answer token, e.g. a reasoning
# model spending its whole max_tokens=1 budget on hidden thinking. Empty-vs-empty would
# otherwise score JSD=0 and PASS regardless of which model is behind the endpoint.
MAX_EMPTY_RATIO = 0.5
JSD_NULL_PERMUTATIONS = 200


def samples_have_logprobs(samples_a: list[RawSample], samples_b: list[RawSample]) -> bool:
    """
    Logprob mode is only valid when every sample on both sides has logprobs.
    Mixing modes compares first-token logprobs ('par') against full sampled words
    ('paris'), producing disjoint vocabularies and a spurious JSD of 1.0.
    """
    return all(bool(s.logprobs) for s in samples_a) and all(
        bool(s.logprobs) for s in samples_b
    )


def empty_ratio(samples: list[RawSample]) -> float:
    if not samples:
        return 0.0
    empty = sum(
        1
        for s in samples
        if not s.logprobs and normalize_token(s.raw_text) == EMPTY_TOKEN
    )
    return empty / len(samples)


def _jsd_from_counts(p_counts: np.ndarray, q_counts: np.ndarray) -> float:
    p = p_counts / p_counts.sum()
    q = q_counts / q_counts.sum()
    return max(0.0, min(1.0, float(jensenshannon(p, q, base=2) ** 2)))


def empirical_jsd_null(
    tokens_a: list[str],
    tokens_b: list[str],
    n_permutations: int = JSD_NULL_PERMUTATIONS,
    rng_seed: int = 0,
) -> tuple[float, float, float]:
    """
    Permutation null for empirical (frequency-based) JSD.

    With finite samples the plug-in JSD is biased upward: two samples of 50 answers from
    the *same* model over a wide answer space ("random number 1-100") routinely score
    0.2-0.5. Shuffling the pooled answers between the two sides estimates that
    same-model baseline level.

    Returns (observed_jsd, null_mean_jsd, p_value).
    """
    vocab = sorted(set(tokens_a) | set(tokens_b))
    if len(vocab) <= 1:
        return 0.0, 0.0, 1.0
    index = {t: i for i, t in enumerate(vocab)}
    pooled = np.array([index[t] for t in tokens_a + tokens_b])
    m = len(tokens_a)
    k = len(vocab)

    observed = _jsd_from_counts(
        np.bincount(pooled[:m], minlength=k), np.bincount(pooled[m:], minlength=k)
    )
    rng = np.random.default_rng(rng_seed)
    null = np.empty(n_permutations)
    for i in range(n_permutations):
        perm = rng.permutation(pooled)
        null[i] = _jsd_from_counts(
            np.bincount(perm[:m], minlength=k), np.bincount(perm[m:], minlength=k)
        )
    p_value = float((np.sum(null >= observed - 1e-12) + 1) / (n_permutations + 1))
    return observed, float(null.mean()), p_value


def compute_samples_jsd(
    samples_a: list[RawSample],
    samples_b: list[RawSample],
) -> tuple[float, bool, list[tuple[str, float]], list[tuple[str, float]]]:
    """
    Computes Jensen-Shannon Divergence between two sample sets.
    Uses logprobs only when both sides fully provide them, else empirical frequencies.
    Returns (raw_jsd_val, used_logprobs, top_a_tokens, top_b_tokens).
    """
    if not samples_a or not samples_b:
        return 1.0, False, [], []

    used_logprobs = samples_have_logprobs(samples_a, samples_b)

    vocab: set[str] = set()
    for s in samples_a:
        vocab.update(extract_sample_distribution(s, used_logprobs).keys())
    for s in samples_b:
        vocab.update(extract_sample_distribution(s, used_logprobs).keys())

    vocab_sorted = sorted(vocab)
    p = build_aggregated_distribution(samples_a, vocab, used_logprobs)
    q = build_aggregated_distribution(samples_b, vocab, used_logprobs)

    # Extract top tokens with probabilities
    top_a = sorted(
        zip(vocab_sorted, [round(float(v), 4) for v in p]),
        key=lambda x: x[1],
        reverse=True,
    )[:3]
    top_b = sorted(
        zip(vocab_sorted, [round(float(v), 4) for v in q]),
        key=lambda x: x[1],
        reverse=True,
    )[:3]

    if len(vocab) <= 1:
        return 0.0, used_logprobs, top_a, top_b

    js_dist = jensenshannon(p, q, base=2)
    jsd_val = float(js_dist**2)
    return max(0.0, min(1.0, jsd_val)), used_logprobs, top_a, top_b


def is_reasoning_model(
    model_name: str | None = None,
    samples: list[RawSample] | None = None,
) -> bool:
    """Detect if the target model generates internal chain-of-thought tokens."""
    if model_name and is_reasoning_model_name(model_name):
        return True
    if samples:
        for s in samples:
            if s.reasoning_tokens and s.reasoning_tokens > 0:
                return True
            if s.reasoning_content:
                return True
            if s.model_returned and is_reasoning_model_name(s.model_returned):
                return True
    return False


def compare_distributions_jsd(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    prompts_map: dict[int, PromptItem],
    run_id: int,
    thresholds: ThresholdsConfig,
    target_model: str | None = None,
) -> list[Score]:
    """
    Audits all one_token prompt responses across baseline and run using JSD.
    Automatically leverages true logprobs when available, with empirical fallback.
    Adapts JSD thresholds for reasoning/thinking models where internal CoT introduces entropy.
    """
    # Group raw samples by prompt_id
    base_by_prompt: dict[int, list[RawSample]] = {}
    for s in baseline_samples:
        base_by_prompt.setdefault(s.prompt_id, []).append(s)

    run_by_prompt: dict[int, list[RawSample]] = {}
    for s in run_samples:
        run_by_prompt.setdefault(s.prompt_id, []).append(s)

    # Find one_token and bpe_fingerprint prompts
    one_token_prompts = [
        p
        for p in prompts_map.values()
        if p.category in ("one_token", "bpe_fingerprint") and p.id is not None
    ]

    if not one_token_prompts:
        return [
            Score(
                id=None,
                run_id=run_id,
                method=MethodTier.JSD.value,
                scope="aggregate",
                value=0.0,
                threshold=thresholds.jsd_fail,
                verdict=Verdict.SKIP,
                details={
                    "message": "No one_token or bpe_fingerprint prompts found in battery"
                },
            )
        ]

    prompt_jsds: list[dict[str, Any]] = []
    skipped_cells: list[dict[str, Any]] = []
    jsd_values: list[float] = []
    cell_modes: set[str] = set()

    for p in one_token_prompts:
        if p.id is None:
            continue
        b_samples = base_by_prompt.get(p.id, [])
        r_samples = run_by_prompt.get(p.id, [])

        if not b_samples or not r_samples:
            continue

        b_empty, r_empty = empty_ratio(b_samples), empty_ratio(r_samples)
        if b_empty > MAX_EMPTY_RATIO or r_empty > MAX_EMPTY_RATIO:
            skipped_cells.append(
                {
                    "prompt_id": p.id,
                    "reason": "empty_output",
                    "baseline_empty_ratio": round(b_empty, 2),
                    "run_empty_ratio": round(r_empty, 2),
                }
            )
            continue

        raw_jsd, used_lp, top_baseline, top_run = compute_samples_jsd(
            b_samples, r_samples
        )
        cell: dict[str, Any] = {
            "prompt_id": p.id,
            "text": p.text[:40] + ("..." if len(p.text) > 40 else ""),
            "baseline_samples": len(b_samples),
            "run_samples": len(r_samples),
            "used_logprobs": used_lp,
            "top_baseline_tokens": top_baseline,
            "top_run_tokens": top_run,
        }
        if used_lp:
            cell_jsd = raw_jsd
            cell_modes.add("logprobs")
        else:
            # Subtract the same-model sampling-noise level so thresholds mean the same
            # thing regardless of sample count and answer-space width.
            _obs, null_mean, p_value = empirical_jsd_null(
                [normalize_token(s.raw_text) for s in b_samples],
                [normalize_token(s.raw_text) for s in r_samples],
            )
            cell_jsd = max(0.0, raw_jsd - null_mean)
            cell["raw_jsd"] = round(raw_jsd, 4)
            cell["null_jsd"] = round(null_mean, 4)
            cell["p_value"] = round(p_value, 4)
            cell_modes.add("empirical")

        cell["jsd"] = round(cell_jsd, 4)
        jsd_values.append(cell_jsd)
        prompt_jsds.append(cell)

    if not jsd_values:
        message = (
            "One-token probes returned empty answers (reasoning model budget exhausted?); "
            "JSD fingerprinting is not applicable"
            if skipped_cells
            else "No samples collected for one_token or bpe_fingerprint prompts"
        )
        return [
            Score(
                id=None,
                run_id=run_id,
                method=MethodTier.JSD.value,
                scope="aggregate",
                value=0.0,
                threshold=thresholds.jsd_fail,
                verdict=Verdict.SKIP,
                details={"message": message, "skipped_cells": skipped_cells},
            )
        ]

    # Overall Mean JSD
    avg_jsd = float(np.mean(jsd_values))
    max_jsd = float(np.max(jsd_values))

    # Check if target or baseline is a reasoning model
    is_reasoning = is_reasoning_model(target_model, run_samples) or is_reasoning_model(
        None, baseline_samples
    )
    effective_jsd_fail = (
        thresholds.reasoning_jsd_fail if is_reasoning else thresholds.jsd_fail
    )
    effective_jsd_warn = (
        min(thresholds.jsd_warn * 1.5, effective_jsd_fail * 0.7)
        if is_reasoning
        else thresholds.jsd_warn
    )

    # Strict verdict evaluation
    if avg_jsd > effective_jsd_fail:
        verdict = Verdict.FAIL
    elif avg_jsd > effective_jsd_warn:
        verdict = Verdict.WARN
    else:
        verdict = Verdict.PASS

    aggregate_score = Score(
        id=None,
        run_id=run_id,
        method=MethodTier.JSD.value,
        scope="aggregate",
        value=round(avg_jsd, 4),
        threshold=effective_jsd_fail,
        verdict=verdict,
        details={
            "mean_jsd": round(avg_jsd, 4),
            "max_jsd": round(max_jsd, 4),
            "mode": (
                "logprobs (token probability distributions)"
                if cell_modes == {"logprobs"}
                else "empirical (frequency-based, permutation bias-corrected)"
                if cell_modes == {"empirical"}
                else "mixed (logprobs + bias-corrected empirical)"
            ),
            "num_probe_cells": len(jsd_values),
            "cells": prompt_jsds,
            "threshold_warn": effective_jsd_warn,
            "threshold_fail": effective_jsd_fail,
            "is_reasoning_model": is_reasoning,
            "skipped_cells": skipped_cells,
        },
    )

    return [aggregate_score]
