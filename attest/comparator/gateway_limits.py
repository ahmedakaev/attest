"""
Gateway max_tokens mismatch guard.

Gateways treat tiny output caps differently: some pass `max_tokens: 1` through and
return one token ("Cer"), others enforce a minimum and return the whole word
("Cerulean"). Some also spend a small cap on hidden reasoning and return
an empty answer. The model is the same, but seed, distribution, speed, similarity
and MMD checks would read the difference as a swap. Prompts where one side is cut to
a single token and the other is not are therefore left out of those checks.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from attest.models import MethodTier, RawSample, Score, Verdict

TRUNCATED_MAX_TOKENS = 1
# The other side must be clearly longer, not one token of jitter
FULL_MIN_TOKENS = 3


def _median_completion_tokens(samples: list[RawSample]) -> dict[int, float]:
    grouped: dict[int, list[int]] = {}
    for s in samples:
        if not isinstance(s.usage, dict):
            continue
        ct = s.usage.get("completion_tokens")
        if isinstance(ct, (int, float)) and not isinstance(ct, bool):
            # Hidden reasoning counts: the cap applies to it too, and a gateway that
            # spends its minimum on reasoning returns an empty answer
            grouped.setdefault(s.prompt_id, []).append(int(ct))
    return {pid: float(np.median(v)) for pid, v in grouped.items() if v}


EMPTY_SHARE = 0.5
ANSWERED_SHARE = 0.9


def _empty_share(samples: list[RawSample]) -> dict[int, float]:
    grouped: dict[int, list[bool]] = {}
    for s in samples:
        grouped.setdefault(s.prompt_id, []).append(not s.raw_text.strip())
    return {pid: sum(v) / len(v) for pid, v in grouped.items()}


def find_max_tokens_mismatch(
    baseline_samples: list[RawSample], run_samples: list[RawSample]
) -> dict[int, dict[str, Any]]:
    """Prompt ids where one side was truncated to one token and the other was not,
    or where one side came back empty (the cap went to hidden reasoning) and the
    other answered."""
    base = _median_completion_tokens(baseline_samples)
    run = _median_completion_tokens(run_samples)
    mismatched: dict[int, dict[str, Any]] = {}
    base_empty, run_empty = _empty_share(baseline_samples), _empty_share(run_samples)
    for pid in set(base_empty) & set(run_empty):
        for side, empty, other in (
            ("baseline", base_empty[pid], run_empty[pid]),
            ("run", run_empty[pid], base_empty[pid]),
        ):
            if empty >= EMPTY_SHARE and other <= 1 - ANSWERED_SHARE:
                mismatched[pid] = {
                    "baseline_completion_tokens": base.get(pid),
                    "run_completion_tokens": run.get(pid),
                    "truncated_side": side,
                    "reason": "empty_answers",
                }
    for pid in (set(base) & set(run)) - set(mismatched):
        lo, hi = sorted((base[pid], run[pid]))
        if lo <= TRUNCATED_MAX_TOKENS and hi >= FULL_MIN_TOKENS:
            mismatched[pid] = {
                "baseline_completion_tokens": base[pid],
                "run_completion_tokens": run[pid],
                "truncated_side": "run" if run[pid] < base[pid] else "baseline",
                "reason": "single_token",
            }
    return mismatched


def gateway_limits_score(mismatched: dict[int, dict[str, Any]], run_id: int) -> Score:
    """Informational score (SKIP, never counted in the verdict) explaining the exclusion."""
    sides = {m["truncated_side"] for m in mismatched.values()}
    empty = [m for m in mismatched.values() if m.get("reason") == "empty_answers"]
    empty_baseline = sum(1 for m in empty if m["truncated_side"] == "baseline")
    return Score(
        id=None,
        run_id=run_id,
        method=MethodTier.GATEWAY_LIMITS.value,
        scope="aggregate",
        value=float(len(mismatched)),
        threshold=None,
        verdict=Verdict.SKIP,
        details={
            "excluded_prompts": len(mismatched),
            "truncated_side": sides.pop() if len(sides) == 1 else "mixed",
            "prompts": {str(pid): info for pid, info in sorted(mismatched.items())},
            "message": (
                f"{len(mismatched)} probes left out of seed, distribution, speed, "
                "similarity and MMD checks: one side's answers were cut to one token "
                "or came back empty while the other side answered. This is a gateway "
                "or output-cap difference, not a model difference."
                + (
                    f" {empty_baseline} of them have empty baseline answers: the "
                    "model spent the whole cap on hidden reasoning. Recapture the "
                    "baseline (thinking models now get a larger cap)."
                    if empty_baseline
                    else ""
                )
            ),
            "empty_baseline_prompts": empty_baseline,
        },
    )
