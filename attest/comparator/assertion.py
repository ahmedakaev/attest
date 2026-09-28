"""
Declarative prompt assertion and censorship discrepancy evaluator.

Inspired by Promptfoo's assertion matrix and Garak's guardrail divergence tests,
this evaluator verifies deterministic text rules, latency ceilings, and detects
third-party middleware firewalls and silent refusals.
"""

from __future__ import annotations

import json
import re
from typing import Any

from attest.models import PromptAssertion, RawSample, Score, Verdict

REFUSAL_PATTERNS = [
    r"i cannot (fulfill|assist|help|comply|provide|answer|generate)",
    r"i am unable to (fulfill|assist|help|comply|provide|answer|generate)",
    r"i'?m sorry,? (but )?i (cannot|can't|am unable)",
    r"violates (our|the) (safety|content|usage) policy",
    r"against my (safety|content) guidelines",
    r"i must decline",
    r"sorry, but i can't assist with that",
]

_REFUSAL_REGEX = re.compile("|".join(REFUSAL_PATTERNS), re.IGNORECASE)

ASSERTION_TYPES = frozenset(
    {
        "contains",
        "not_contains",
        "regex",
        "is_json",
        "latency_ms_max",
        "not_refusal",
        "has_reasoning",
        "min_reasoning_tokens",
    }
)
NUMERIC_ASSERTION_TYPES = frozenset({"latency_ms_max", "min_reasoning_tokens"})


def validate_assertion(a_type: str, value: Any) -> str | None:
    """Return an error message if the assertion is malformed, else None."""
    a_type = a_type.lower().strip()
    if a_type not in ASSERTION_TYPES:
        return (
            f"unknown assertion type '{a_type}' "
            f"(expected one of: {', '.join(sorted(ASSERTION_TYPES))})"
        )
    if a_type in NUMERIC_ASSERTION_TYPES:
        try:
            float(value)
        except (TypeError, ValueError):
            return f"assertion '{a_type}' needs a numeric value, got {value!r}"
    if a_type == "regex":
        try:
            re.compile(str(value))
        except re.error as e:
            return f"invalid regex {value!r}: {e}"
    return None


def is_refusal_text(text: str) -> bool:
    """Returns True if the response contains standard canned refusal language."""
    clean = text.strip().lower()
    return bool(_REFUSAL_REGEX.search(clean))


def evaluate_sample_assertions(
    sample: RawSample,
    assertions: list[PromptAssertion],
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Evaluates declarative assertions against a single sample.
    Returns (all_required_passed, detail_records).
    """
    results: list[dict[str, Any]] = []
    all_passed = True

    for a in assertions:
        a_type = a.type.lower().strip()
        passed = False
        message = ""

        if a_type == "contains":
            expected = str(a.value)
            passed = expected.lower() in sample.raw_text.lower()
            message = f"Expected text to contain '{expected}'"

        elif a_type == "not_contains":
            unexpected = str(a.value)
            passed = unexpected.lower() not in sample.raw_text.lower()
            message = f"Expected text NOT to contain '{unexpected}'"

        elif a_type == "regex":
            pattern = str(a.value)
            try:
                passed = bool(re.search(pattern, sample.raw_text))
                message = f"Expected regex match '{pattern}'"
            except re.error as e:
                passed = False
                message = f"Invalid regex pattern '{pattern}': {e}"

        elif a_type == "is_json":
            raw = sample.raw_text.strip()
            # Strip reasoning/thinking tags if model returned CoT (e.g. DeepSeek-R1, QwQ)
            raw = re.sub(
                r"<(?:think|thought|reasoning)>.*?</(?:think|thought|reasoning)>",
                "",
                raw,
                flags=re.DOTALL | re.IGNORECASE,
            ).strip()
            # Strip markdown code fences if model enclosed JSON in ```json ... ```
            if raw.startswith("```"):
                lines = raw.splitlines()
                if len(lines) >= 2 and lines[-1].strip().startswith("```"):
                    raw = "\n".join(lines[1:-1]).strip()
            try:
                parsed = json.loads(raw)
                passed = True
                message = "Response is valid JSON"
                if isinstance(a.value, list) and isinstance(parsed, dict):
                    missing = [k for k in a.value if k not in parsed]
                    if missing:
                        passed = False
                        message = f"JSON missing required keys: {', '.join(missing)}"
                elif isinstance(a.value, str) and a.value:
                    if a.value.lower() == "object" and not isinstance(parsed, dict):
                        passed = False
                        message = f"Expected JSON object, got {type(parsed).__name__}"
                    elif a.value.lower() == "array" and not isinstance(parsed, list):
                        passed = False
                        message = f"Expected JSON array, got {type(parsed).__name__}"
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                passed = False
                message = f"Invalid JSON: {e}"

        elif a_type == "latency_ms_max":
            max_lat = float(a.value)
            lat = sample.latency_ms
            if lat is not None:
                passed = lat <= max_lat
                message = f"Latency {lat}ms <= max {max_lat}ms"
            else:
                passed = False
                message = (
                    f"Latency metric unavailable (None) for max {max_lat}ms ceiling"
                )

        elif a_type == "not_refusal":
            passed = not is_refusal_text(sample.raw_text)
            message = "Response must not be a canned refusal"

        elif a_type == "has_reasoning":
            has_tokens = bool(sample.reasoning_tokens and sample.reasoning_tokens > 0)
            has_content = bool(
                sample.reasoning_content and sample.reasoning_content.strip()
            )
            lowered_text = sample.raw_text.lower()
            has_think_tag = any(
                tag in lowered_text for tag in ("<think>", "<thought>", "<reasoning>")
            )
            passed = has_tokens or has_content or has_think_tag
            message = (
                "Response must contain reasoning/thinking trace or reasoning tokens"
                if not passed
                else "Reasoning trace confirmed"
            )

        elif a_type == "min_reasoning_tokens":
            min_tokens = int(a.value)
            curr_tokens = sample.reasoning_tokens or 0
            if curr_tokens == 0 and sample.reasoning_content:
                # Approximate tokens if provider returns reasoning_content without usage tokens details
                curr_tokens = max(1, int(len(sample.reasoning_content.split()) * 1.3))
            passed = curr_tokens >= min_tokens
            message = f"Reasoning tokens {curr_tokens} >= min {min_tokens}"

        else:
            # Never report an unrecognized rule as green (e.g. a typo like 'contain')
            passed = False
            message = f"Unknown assertion type '{a_type}'"

        if not passed and not a.optional:
            all_passed = False

        results.append(
            {
                "type": a.type,
                "value": a.value,
                "optional": a.optional,
                "passed": passed,
                "message": message,
            }
        )

    return all_passed, results


def _baseline_rule_pass_rates(
    samples: list[RawSample], assertions: list[PromptAssertion]
) -> list[float]:
    passes = [0] * len(assertions)
    for s in samples:
        _all_passed, records = evaluate_sample_assertions(s, assertions)
        for i, r in enumerate(records):
            passes[i] += int(r["passed"])
    return [p / len(samples) for p in passes]


def evaluate_batch_assertions(
    samples_by_prompt: dict[int, list[RawSample]],
    assertions_by_prompt: dict[int, list[PromptAssertion]],
    run_id: int,
    baseline_samples_by_prompt: dict[int, list[RawSample]] | None = None,
) -> Score | None:
    """
    Evaluates all prompt assertions across all samples in the run.
    Emits an overall Score with method='assertions'.

    With baseline samples, rules are judged relative to the baseline: a rule the
    baseline model itself fails in most samples is the model's own limit (a cheap
    model failing a capability probe), not a sign of substitution, and is left out.
    Only rules the baseline passes can fail the run, so a quantized or smaller
    substitute is caught by what the real model can do and it cannot.
    """
    total_assertions = 0
    passed_assertions = 0
    baseline_limited = 0
    failures: list[dict[str, Any]] = []

    for prompt_id, assertions in assertions_by_prompt.items():
        if not assertions:
            continue
        samples = samples_by_prompt.get(prompt_id, [])
        base = (baseline_samples_by_prompt or {}).get(prompt_id)
        applicable = (
            [rate > 0.5 for rate in _baseline_rule_pass_rates(base, assertions)]
            if base
            else [True] * len(assertions)
        )
        baseline_limited += applicable.count(False) * len(samples)
        for s in samples:
            _all_passed, records = evaluate_sample_assertions(s, assertions)
            for r, ok in zip(records, applicable, strict=True):
                if not ok:
                    continue
                total_assertions += 1
                if r["passed"]:
                    passed_assertions += 1
                elif not r["optional"]:
                    failures.append(
                        {
                            "prompt_id": prompt_id,
                            "assertion": r["type"],
                            "expected": r["value"],
                            "message": r["message"],
                            "latency_ms": s.latency_ms,
                            "sample_preview": s.raw_text[:120],
                        }
                    )

    if total_assertions == 0:
        if not baseline_limited:
            return None
        return Score(
            id=None,
            run_id=run_id,
            method="assertions",
            scope="aggregate",
            value=1.0,
            threshold=1.0,
            verdict=Verdict.SKIP,
            details={
                "message": "The baseline model fails every rule itself; nothing to compare",
                "baseline_limited": baseline_limited,
            },
        )

    pass_rate = passed_assertions / total_assertions
    verdict = (
        Verdict.PASS
        if not failures
        else (Verdict.WARN if pass_rate >= 0.8 else Verdict.FAIL)
    )

    return Score(
        id=None,
        run_id=run_id,
        method="assertions",
        scope="aggregate",
        value=round(pass_rate, 4),
        threshold=1.0,
        verdict=verdict,
        details={
            "total_assertions": total_assertions,
            "passed_assertions": passed_assertions,
            "pass_rate": round(pass_rate, 4),
            "failures": failures[:10],
            "failure_count": len(failures),
            "baseline_limited": baseline_limited,
        },
    )
