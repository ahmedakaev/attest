"""
IRIS random-string fingerprint (arXiv 2607.20860): detects model substitution and
partial routing to a cheaper model ("dilution") from short "random" strings.

Models are poor random generators, and each has its own habits (favourite digits,
first characters, run lengths). For every `iris` prompt the baseline answers define a
per-position character model; a run answer that is atypical for it is a "tell".

  - score(y) = mean over positions of -log P_ref(char), with add-0.5 smoothing.
    An answer whose length never occurs in the reference is always a tell.
  - The tell threshold is the j-th largest of the n leave-one-out baseline scores (95th
    percentile). Under "same model" the m run answers are exchangeable with them, so the
    tell count follows the exact exceedance law
        P(X = x) = C(x + j - 1, x) * C(n - j + m - x, m - x) / C(n + m, m),
    which already accounts for the randomness of a small baseline (a binomial at the
    mean rate does not, and gives several times more false FAILs at n = 8).
  - Verdict: prompts are independent, so their laws are convolved and the p-value is
    P(total tells >= observed). No logprobs are needed.
  - Dilution estimate: (tell_rate - alpha) / (1 - alpha). A substitute does not make
    every answer a tell, so this is a lower bound on the rerouted share of traffic.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import numpy as np
from scipy.special import comb

from attest.config import ThresholdsConfig
from attest.models import MethodTier, PromptItem, RawSample, Score, Verdict

IRIS_CATEGORY = "iris"
TELL_QUANTILE = 0.95
SMOOTHING = 0.5
# Leave-one-out needs enough reference answers per prompt to set a threshold
MIN_BASELINE_PER_PROMPT = 5
MIN_RUN_TOTAL = 10

_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)


def normalize_answer(text: str) -> str:
    """Keep only letters and digits, uppercased: '4 7 1, 9' -> '4719', 'h t H' -> 'HTH'."""
    return _NON_ALNUM.sub("", text or "").upper()


class _PositionModel:
    """Per-position character frequencies of reference answers for one prompt."""

    def __init__(self, answers: list[str]):
        self.lengths = Counter(len(a) for a in answers)
        self.alphabet = {c for a in answers for c in a}
        self.positions: list[Counter[str]] = []
        for a in answers:
            for i, c in enumerate(a):
                if i == len(self.positions):
                    self.positions.append(Counter())
                self.positions[i][c] += 1

    def score(self, answer: str) -> float:
        if not answer or not self.lengths.get(len(answer)):
            return math.inf
        # +1 slot so characters the reference never produced still get a probability
        k = len(self.alphabet) + 1
        total = 0.0
        for i, c in enumerate(answer):
            counts = self.positions[i]
            n = sum(counts.values())
            total -= math.log((counts.get(c, 0) + SMOOTHING) / (n + SMOOTHING * k))
        return total / len(answer)


def _loo_scores(answers: list[str]) -> list[float]:
    return [
        _PositionModel(answers[:i] + answers[i + 1 :]).score(a)
        for i, a in enumerate(answers)
    ]


def _exceedance_pmf(n: int, j: int, m: int) -> np.ndarray:
    """Law of how many of m new exchangeable draws exceed the j-th largest of n."""
    x = np.arange(m + 1)
    return comb(x + j - 1, x) * comb(n - j + m - x, m - x) / comb(n + m, m)


def _skip(run_id: int, message: str) -> list[Score]:
    return [
        Score(
            id=None,
            run_id=run_id,
            method=MethodTier.IRIS.value,
            scope="aggregate",
            value=1.0,
            threshold=None,
            verdict=Verdict.SKIP,
            details={"message": message},
        )
    ]


def compare_iris(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    prompts_map: dict[int, PromptItem],
    run_id: int,
    thresholds: ThresholdsConfig,
) -> list[Score]:
    iris_ids = {pid for pid, p in prompts_map.items() if p.category == IRIS_CATEGORY}
    if not iris_ids:
        return []

    def answers_by_prompt(samples: list[RawSample]) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        for s in samples:
            answer = normalize_answer(s.raw_text) if s.prompt_id in iris_ids else ""
            # Empty answers are transport/truncation failures, not model behaviour
            if answer:
                out.setdefault(s.prompt_id, []).append(answer)
        return out

    base = answers_by_prompt(baseline_samples)
    run = answers_by_prompt(run_samples)

    expected = 0.0
    run_tells = run_total = 0
    null_pmf = np.ones(1)
    per_prompt: list[dict[str, Any]] = []
    for pid in sorted(set(base) & set(run)):
        ref_answers = base[pid]
        if len(ref_answers) < MIN_BASELINE_PER_PROMPT:
            continue
        loo = _loo_scores(ref_answers)
        finite = [s for s in loo if math.isfinite(s)]
        if not finite:
            continue
        tau = float(np.quantile(finite, TELL_QUANTILE, method="higher"))
        model = _PositionModel(ref_answers)
        n, m = len(loo), len(run[pid])
        j = sum(1 for s in loo if s >= tau)
        p_tells = sum(1 for a in run[pid] if model.score(a) > tau)
        p_alpha = j / (n + 1)

        null_pmf = np.convolve(null_pmf, _exceedance_pmf(n, j, m))
        expected += p_alpha * m
        run_tells += p_tells
        run_total += m
        per_prompt.append(
            {
                "prompt_id": pid,
                "tells": p_tells,
                "total": len(run[pid]),
                "reference_tell_rate": round(p_alpha, 4),
                "baseline_top": [a for a, _ in Counter(ref_answers).most_common(3)],
                "run_top": [a for a, _ in Counter(run[pid]).most_common(3)],
            }
        )

    if run_total < MIN_RUN_TOTAL:
        return _skip(
            run_id,
            f"Need >= {MIN_RUN_TOTAL} iris answers with >= "
            f"{MIN_BASELINE_PER_PROMPT} baseline answers per prompt",
        )

    alpha = expected / run_total
    tell_rate = run_tells / run_total
    p_value = float(min(1.0, null_pmf[run_tells:].sum()))
    dilution = min(1.0, max(0.0, (tell_rate - alpha) / (1.0 - alpha)))

    if p_value < thresholds.iris_pvalue_fail:
        verdict = Verdict.FAIL
    elif p_value < thresholds.iris_pvalue_warn:
        verdict = Verdict.WARN
    else:
        verdict = Verdict.PASS

    return [
        Score(
            id=None,
            run_id=run_id,
            method=MethodTier.IRIS.value,
            scope="aggregate",
            value=round(p_value, 4),
            threshold=thresholds.iris_pvalue_fail,
            verdict=verdict,
            details={
                "tells": run_tells,
                "total": run_total,
                "tell_rate": round(tell_rate, 4),
                "reference_tell_rate": round(alpha, 4),
                "expected_tells": round(alpha * run_total, 1),
                "p_value": round(p_value, 4),
                "dilution_lower_bound": round(dilution, 3),
                "by_prompt": per_prompt,
            },
        )
    ]
