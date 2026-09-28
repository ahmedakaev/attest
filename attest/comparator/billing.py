"""
Billing Integrity: detects token over-billing from the `usage` block the provider
already returns with every response. Costs zero extra requests.

Checks, all relative to the trusted baseline for the same prompts:
  - Input tokens: robust fit run = scale * baseline + overhead across prompts.
    scale > 1 means every input token is multiplied; overhead > 0 means a fixed number
    of tokens is added to each request (hidden system prompt or flat padding).
  - Output tokens: tokens billed per character of visible answer text.
  - Phantom reasoning: reasoning tokens billed although the baseline model never reasons.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import theilslopes

from attest.config import ThresholdsConfig
from attest.models import MethodTier, RawSample, Score, Verdict

# Below this many characters the chars-per-token ratio is dominated by rounding
MIN_COMPLETION_CHARS = 40
MIN_COMPLETION_SAMPLES = 3
# A slope/intercept fit needs prompts of visibly different lengths to separate the two
MIN_FIT_PROMPTS = 3
MIN_FIT_SPREAD_TOKENS = 20


def _usage_int(sample: RawSample, *keys: str) -> int | None:
    if not isinstance(sample.usage, dict):
        return None
    for key in keys:
        val = sample.usage.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return int(val)
    return None


def _prompt_tokens(sample: RawSample) -> int | None:
    return _usage_int(sample, "prompt_tokens", "input_tokens")


def _visible_completion(sample: RawSample) -> tuple[int, int] | None:
    """(visible answer tokens, answer chars), excluding billed reasoning tokens."""
    completion = _usage_int(sample, "completion_tokens", "output_tokens")
    if completion is None:
        return None
    visible = completion - (sample.reasoning_tokens or 0)
    chars = len(sample.raw_text)
    if visible <= 0 or chars < MIN_COMPLETION_CHARS:
        return None
    return visible, chars


def _median_by_prompt(samples: list[RawSample]) -> dict[int, float]:
    grouped: dict[int, list[int]] = {}
    for s in samples:
        pt = _prompt_tokens(s)
        if pt is not None and pt > 0:
            grouped.setdefault(s.prompt_id, []).append(pt)
    return {pid: float(np.median(v)) for pid, v in grouped.items()}


def _grade(value: float, warn: float, fail: float) -> Verdict:
    if value >= fail:
        return Verdict.FAIL
    if value >= warn:
        return Verdict.WARN
    return Verdict.PASS


def _check_prompt_tokens(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    thresholds: ThresholdsConfig,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[Verdict]]:
    base = _median_by_prompt(baseline_samples)
    run = _median_by_prompt(run_samples)
    common = sorted(set(base) & set(run))
    if not common:
        return None, [], []

    x = np.array([base[p] for p in common])
    y = np.array([run[p] for p in common])
    total_inflation = float(y.sum() / x.sum() - 1.0)

    fitted = (
        len(common) >= MIN_FIT_PROMPTS and (x.max() - x.min()) >= MIN_FIT_SPREAD_TOKENS
    )
    if fitted:
        slope, intercept, _lo, _hi = theilslopes(y, x)
        scale, overhead = float(slope), float(intercept)
    else:
        # Too few / too similar prompts to separate scale from overhead:
        # attribute the whole difference to a per-request overhead.
        scale, overhead = 1.0, float(np.median(y - x))

    issues: list[dict[str, Any]] = []
    verdicts: list[Verdict] = []

    scale_v = _grade(
        scale - 1.0,
        thresholds.billing_prompt_scale_warn,
        thresholds.billing_prompt_scale_fail,
    )
    if scale_v != Verdict.PASS:
        issues.append(
            {"kind": "prompt_scale", "scale": round(scale, 3), "verdict": scale_v.value}
        )
    verdicts.append(scale_v)

    overhead_v = _grade(
        overhead,
        thresholds.billing_prompt_overhead_warn,
        thresholds.billing_prompt_overhead_fail,
    )
    if overhead_v != Verdict.PASS:
        issues.append(
            {
                "kind": "prompt_overhead",
                "tokens": round(overhead, 1),
                "verdict": overhead_v.value,
            }
        )
    verdicts.append(overhead_v)

    info = {
        "matched_prompts": len(common),
        "fit": "theil-sen" if fitted else "median-difference",
        "scale": round(scale, 4),
        "overhead_tokens": round(overhead, 1),
        "baseline_total": int(x.sum()),
        "run_total": int(y.sum()),
        "total_inflation": round(total_inflation, 4),
    }
    return info, issues, verdicts


def _reasoning_unseparable(
    baseline_samples: list[RawSample], run_samples: list[RawSample]
) -> set[int]:
    """Prompts where the model reasoned but one side does not report how much.

    A gateway that bills reasoning inside completion_tokens without a
    reasoning_tokens breakdown would otherwise look like it bills the visible text
    at a higher rate.
    """

    def by_prompt(samples: list[RawSample]) -> dict[int, list[RawSample]]:
        out: dict[int, list[RawSample]] = {}
        for s in samples:
            out.setdefault(s.prompt_id, []).append(s)
        return out

    base, run = by_prompt(baseline_samples), by_prompt(run_samples)
    unseparable = set()
    for pid in set(base) & set(run):
        both = base[pid] + run[pid]
        reasoned = any(
            (s.reasoning_tokens or 0) > 0 or s.reasoning_content for s in both
        )
        reported = all(s.reasoning_tokens is not None for s in both)
        if reasoned and not reported:
            unseparable.add(pid)
    return unseparable


def _check_completion_tokens(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    thresholds: ThresholdsConfig,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[Verdict]]:
    skipped = _reasoning_unseparable(baseline_samples, run_samples)
    run_prompt_ids = {s.prompt_id for s in run_samples} - skipped
    base = [
        v
        for s in baseline_samples
        if s.prompt_id in run_prompt_ids and (v := _visible_completion(s))
    ]
    base_prompt_ids = {s.prompt_id for s in baseline_samples} - skipped
    run = [
        v
        for s in run_samples
        if s.prompt_id in base_prompt_ids and (v := _visible_completion(s))
    ]
    if len(base) < MIN_COMPLETION_SAMPLES or len(run) < MIN_COMPLETION_SAMPLES:
        return None, [], []

    base_tokens_per_char = sum(t for t, _ in base) / sum(c for _, c in base)
    run_tokens_per_char = sum(t for t, _ in run) / sum(c for _, c in run)
    inflation = run_tokens_per_char / base_tokens_per_char - 1.0

    verdict = _grade(
        inflation,
        thresholds.billing_completion_warn,
        thresholds.billing_completion_fail,
    )
    issues = (
        [
            {
                "kind": "completion",
                "pct": round(inflation * 100, 1),
                "verdict": verdict.value,
            }
        ]
        if verdict != Verdict.PASS
        else []
    )
    info = {
        "baseline_samples": len(base),
        "run_samples": len(run),
        "baseline_chars_per_token": round(1 / base_tokens_per_char, 3),
        "run_chars_per_token": round(1 / run_tokens_per_char, 3),
        "inflation": round(inflation, 4),
        "skipped_unreported_reasoning_prompts": len(skipped),
    }
    return info, issues, [verdict]


def _check_phantom_reasoning(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[Verdict]]:
    base_known = [s for s in baseline_samples if s.usage]
    if not base_known or any(
        (s.reasoning_tokens or 0) > 0 or s.reasoning_content for s in base_known
    ):
        return None, [], []
    billed = sum(s.reasoning_tokens or 0 for s in run_samples)
    if billed <= 0:
        return {"run_reasoning_tokens": 0}, [], [Verdict.PASS]
    samples = sum(1 for s in run_samples if (s.reasoning_tokens or 0) > 0)
    return (
        {"run_reasoning_tokens": billed, "samples": samples},
        [
            {
                "kind": "phantom_reasoning",
                "tokens": billed,
                "samples": samples,
                "verdict": "WARN",
            }
        ],
        [Verdict.WARN],
    )


# A cap is ignored when a reply bills clearly more than was allowed
CAP_TOLERANCE = 1.05
CAP_SLACK_TOKENS = 2
CAP_IGNORED_RUN_SHARE = 0.3
CAP_IGNORED_BASELINE_SHARE = 0.1


def _cap_exceed(samples: list[RawSample]) -> tuple[int, int, int, int]:
    """(samples with a known cap, samples billed over it, largest bill, its cap)."""
    known = over = worst = worst_cap = 0
    for s in samples:
        billed = _usage_int(s, "completion_tokens", "output_tokens")
        if s.max_tokens_sent is None or billed is None:
            continue
        known += 1
        if billed > s.max_tokens_sent * CAP_TOLERANCE + CAP_SLACK_TOKENS:
            over += 1
            if billed > worst:
                worst, worst_cap = billed, s.max_tokens_sent
    return known, over, worst, worst_cap


def _check_cap_ignored(
    baseline_samples: list[RawSample], run_samples: list[RawSample]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[Verdict]]:
    """Provider bills past the max_tokens it was sent, while the baseline respects it:
    the caller cannot bound their spend on this provider."""
    r_known, r_over, worst, worst_cap = _cap_exceed(run_samples)
    if not r_known:
        return None, [], []
    b_known, b_over, _, _ = _cap_exceed(baseline_samples)
    run_share = r_over / r_known
    base_share = b_over / b_known if b_known else 0.0
    info = {
        "run_over_cap": r_over,
        "run_with_cap": r_known,
        "baseline_over_cap": b_over,
        "baseline_with_cap": b_known,
    }
    if run_share >= CAP_IGNORED_RUN_SHARE and base_share <= CAP_IGNORED_BASELINE_SHARE:
        return (
            info,
            [
                {
                    "kind": "cap_ignored",
                    "over": r_over,
                    "total": r_known,
                    "max_billed": worst,
                    "cap": worst_cap,
                    "verdict": Verdict.WARN.value,
                }
            ],
            [Verdict.WARN],
        )
    return info, [], [Verdict.PASS]


def compare_billing(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    run_id: int,
    thresholds: ThresholdsConfig,
    tokenizer_differs: bool = False,
) -> list[Score]:
    """Compare billed token counts against the baseline for the same prompts.

    tokenizer_differs: the provider tokenizes differently from the baseline (another
    model). Token counts of different tokenizers and chat templates are not
    comparable, so input and per-character output checks are skipped; the swap
    itself is reported by the tokenizer check.
    """
    if tokenizer_differs:
        prompt_info, prompt_issues, prompt_v = None, [], []
        comp_info, comp_issues, comp_v = None, [], []
    else:
        prompt_info, prompt_issues, prompt_v = _check_prompt_tokens(
            baseline_samples, run_samples, thresholds
        )
        comp_info, comp_issues, comp_v = _check_completion_tokens(
            baseline_samples, run_samples, thresholds
        )
    reas_info, reas_issues, reas_v = _check_phantom_reasoning(
        baseline_samples, run_samples
    )
    cap_info, cap_issues, cap_v = _check_cap_ignored(baseline_samples, run_samples)

    verdicts = prompt_v + comp_v + reas_v + cap_v
    if not verdicts:
        return [
            Score(
                id=None,
                run_id=run_id,
                method=MethodTier.BILLING.value,
                scope="aggregate",
                value=0.0,
                threshold=None,
                verdict=Verdict.SKIP,
                details={
                    "message": "Provider did not return usage data for matching prompts"
                },
            )
        ]

    verdict = next(
        (v for v in (Verdict.FAIL, Verdict.WARN) if v in verdicts), Verdict.PASS
    )
    # Headline value: worst relative overcharge observed
    overcharge = max(
        [
            prompt_info["total_inflation"] if prompt_info else 0.0,
            comp_info["inflation"] if comp_info else 0.0,
            0.0,
        ]
    )
    return [
        Score(
            id=None,
            run_id=run_id,
            method=MethodTier.BILLING.value,
            scope="aggregate",
            value=round(overcharge, 4),
            threshold=thresholds.billing_prompt_scale_fail,
            verdict=verdict,
            details={
                "prompt_tokens": prompt_info,
                "completion_tokens": comp_info,
                "reasoning_tokens": reas_info,
                "output_cap": cap_info,
                "skipped_token_comparison_other_tokenizer": tokenizer_differs,
                "issues": prompt_issues + comp_issues + reas_issues + cap_issues,
            },
        )
    ]
