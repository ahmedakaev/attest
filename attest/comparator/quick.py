"""
Level 0: Instant checks (model claim, system_fingerprint, seed determinism).
Fast, zero math, immediate signals of backend reconfiguration or obvious spoofing.
"""

from __future__ import annotations

import re
from typing import Any

from attest.models import MethodTier, RawSample, Score, Verdict


def normalize_model_name(name: str) -> str:
    """Normalize model string: strip provider namespace prefix, lowercase, strip whitespace."""
    clean = name.strip().lower()
    # Strip router/vendor namespaces like 'openai/', 'meta-llama/', 'anthropic/', 'google/'
    if "/" in clean:
        clean = clean.split("/")[-1]
    return clean


def is_compatible_model_name(claimed: str, returned: str) -> tuple[bool, str]:
    """
    Determines if returned model name is a valid alias, snapshot, or provider-namespaced
    variant of the claimed model name, versus an actual model substitution/spoofing.
    Returns (is_match, description).
    """
    c = normalize_model_name(claimed)
    r = normalize_model_name(returned)

    if c == r:
        return True, "exact match"

    # Normalize dots to dashes (e.g. claude-3.5-sonnet vs claude-3-5-sonnet)
    c_dashed = c.replace(".", "-")
    r_dashed = r.replace(".", "-")
    if c_dashed == r_dashed:
        return True, "formatting alias match"

    # Regex pattern for date stamps / snapshot suffixes: -YYYY-MM-DD or -YYYYMMDD or -MMDD or -latest or -preview
    snapshot_pattern = r"(-(\d{4}-\d{2}-\d{2}|\d{8}|\d{4}|latest|preview))"

    # Check if returned is a dated snapshot of claimed: e.g. gpt-4o -> gpt-4o-2024-08-06
    if re.fullmatch(re.escape(c_dashed) + snapshot_pattern, r_dashed):
        return True, f"snapshot match: {returned} is a dated release of {claimed}"

    # Check if claimed specified a snapshot and provider returned base alias: e.g. gpt-4o-2024-08-06 -> gpt-4o
    if re.fullmatch(re.escape(r_dashed) + snapshot_pattern, c_dashed):
        return (
            True,
            f"base alias match: provider returned base {returned} for snapshot {claimed}",
        )

    # Strip snapshot suffixes from both and compare base families:
    # e.g. claude-3-5-sonnet-latest vs claude-3-5-sonnet-20241022
    base_c = re.sub(snapshot_pattern + r"$", "", c_dashed)
    base_r = re.sub(snapshot_pattern + r"$", "", r_dashed)
    if base_c and base_c == base_r:
        return True, f"compatible snapshot variant: {returned} shares base {base_c}"

    # Check if returned is a multi-segment router/cloud deployment path:
    # e.g. 'azure/gpt-6-astra/test-azure200-de20fdc4' or 'router/openai/gpt-4o'
    raw_r_parts = [p.replace(".", "-") for p in returned.strip().lower().split("/")]
    if c_dashed in raw_r_parts:
        return True, f"deployment path alias match: {returned} routes to {claimed}"

    # Genuine mismatch
    return False, f"model mismatch: claimed '{claimed}', got '{returned}'"


def check_model_claim(
    target_model: str,
    run_samples: list[RawSample],
    run_id: int,
) -> Score:
    """Verifies that the API returned the claimed model name or compatible snapshot in its response."""
    returned_models = {s.model_returned for s in run_samples if s.model_returned}
    if not returned_models:
        return Score(
            id=None,
            run_id=run_id,
            method=MethodTier.QUICK_MODEL.value,
            scope="aggregate",
            value=1.0,
            threshold=1.0,
            verdict=Verdict.SKIP,
            details={"message": "Provider did not return 'model' field in responses"},
        )

    # Check compatibility for each returned model
    mismatches: list[str] = []
    matches_info: list[str] = []
    for m in returned_models:
        is_match, reason = is_compatible_model_name(target_model, m)
        if is_match:
            matches_info.append(f"{m} ({reason})")
        else:
            mismatches.append(m)

    if mismatches:
        return Score(
            id=None,
            run_id=run_id,
            method=MethodTier.QUICK_MODEL.value,
            scope="aggregate",
            value=0.0,
            threshold=1.0,
            verdict=Verdict.FAIL,
            details={
                "claimed": target_model,
                "returned": mismatches[0],
                "returned_differing": mismatches,
                "message": f"Provider claimed '{target_model}' but returned incompatible '{mismatches[0]}'",
            },
        )

    return Score(
        id=None,
        run_id=run_id,
        method=MethodTier.QUICK_MODEL.value,
        scope="aggregate",
        value=1.0,
        threshold=1.0,
        verdict=Verdict.PASS,
        details={
            "model": target_model,
            "returned_models": list(returned_models),
            "matches_info": matches_info,
            "matched": True,
        },
    )


def check_system_fingerprint(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    run_id: int,
) -> Score:
    """
    Checks OpenAI system_fingerprint field.
    A change indicates infrastructure/backend weight update by the provider.
    """
    base_fps = {s.fingerprint for s in baseline_samples if s.fingerprint}
    run_fps = {s.fingerprint for s in run_samples if s.fingerprint}

    if not base_fps and not run_fps:
        return Score(
            id=None,
            run_id=run_id,
            method=MethodTier.QUICK_FINGERPRINT.value,
            scope="aggregate",
            value=1.0,
            threshold=1.0,
            verdict=Verdict.SKIP,
            details={"message": "system_fingerprint not provided by this endpoint"},
        )

    if base_fps == run_fps:
        return Score(
            id=None,
            run_id=run_id,
            method=MethodTier.QUICK_FINGERPRINT.value,
            scope="aggregate",
            value=1.0,
            threshold=1.0,
            verdict=Verdict.PASS,
            details={"fingerprint": next(iter(base_fps)), "matched": True},
        )

    return Score(
        id=None,
        run_id=run_id,
        method=MethodTier.QUICK_FINGERPRINT.value,
        scope="aggregate",
        value=0.5,
        threshold=1.0,
        verdict=Verdict.WARN,
        details={
            "baseline_fingerprints": list(base_fps),
            "run_fingerprints": list(run_fps),
            "message": "system_fingerprint changed since baseline (backend updated)",
        },
    )


def check_seed_determinism(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    prompts_map: dict[int, Any],
    run_id: int,
) -> Score:
    """Checks exact reproducibility for zero-temperature or explicit seed prompts.

    Capped at WARN: two endpoints serving the same model do not guarantee
    byte-identical long answers at temperature 0 (GPU batching nondeterminism),
    so a mismatch alone cannot prove a swap. Prompts where the model reasoned are
    left out: reasoning models ignore temperature and never repeat themselves.
    """
    # Find prompt_ids that specified deterministic sampling
    det_prompt_ids = set()
    for pid, p in prompts_map.items():
        params = p.params if hasattr(p, "params") else {}
        if params.get("temperature", 1.0) == 0.0 or "seed" in params:
            det_prompt_ids.add(pid)

    if not det_prompt_ids:
        return Score(
            id=None,
            run_id=run_id,
            method=MethodTier.QUICK_SEED.value,
            scope="aggregate",
            value=1.0,
            threshold=1.0,
            verdict=Verdict.SKIP,
            details={"message": "No deterministic seed/temp=0 prompts found"},
        )

    reasoned = {
        s.prompt_id
        for s in (*baseline_samples, *run_samples)
        if s.reasoning_content or (s.reasoning_tokens or 0) > 0
    }
    det_prompt_ids -= reasoned

    base_by_p: dict[int, list[str]] = {}
    for s in baseline_samples:
        if s.prompt_id in det_prompt_ids:
            base_by_p.setdefault(s.prompt_id, []).append(s.raw_text.strip().lower())

    run_by_p: dict[int, list[str]] = {}
    for s in run_samples:
        if s.prompt_id in det_prompt_ids:
            run_by_p.setdefault(s.prompt_id, []).append(s.raw_text.strip().lower())

    matches = 0
    total = 0
    for pid in det_prompt_ids:
        b_list = base_by_p.get(pid, [])
        r_list = run_by_p.get(pid, [])
        if b_list and r_list:
            total += 1
            # Check if any baseline matches any run sample for this deterministic probe
            if any(b == r for b in b_list for r in r_list):
                matches += 1

    if total == 0:
        return Score(
            id=None,
            run_id=run_id,
            method=MethodTier.QUICK_SEED.value,
            scope="aggregate",
            value=1.0,
            threshold=1.0,
            verdict=Verdict.SKIP,
            details={"message": "No matching deterministic samples"},
        )

    ratio = matches / total
    verdict = Verdict.PASS if ratio >= 0.8 else Verdict.WARN

    return Score(
        id=None,
        run_id=run_id,
        method=MethodTier.QUICK_SEED.value,
        scope="aggregate",
        value=ratio,
        threshold=0.8,
        verdict=verdict,
        details={
            "deterministic_matches": matches,
            "total_deterministic_prompts": total,
            "match_ratio": round(ratio, 4),
            "skipped_reasoning_prompts": len(reasoned),
        },
    )


def check_routing_proof(
    claimed_model: str,
    run_samples: list[RawSample],
    run_id: int = 0,
) -> Score:
    """
    Level 0: Compares provider-reported routing metadata against the claimed model.
    The metadata is unsigned, so only a contradiction is meaningful:
    metadata names a different model -> Verdict.FAIL (provider self-reports a swap);
    metadata matches -> Verdict.SKIP (forgeable, so it must not count as a PASS);
    no metadata -> Verdict.SKIP.
    """
    proof_dict = next((s.routing_proof for s in run_samples if s.routing_proof), None)
    if not proof_dict:
        return Score(
            id=None,
            run_id=run_id,
            method=MethodTier.ROUTING_PROOF.value,
            scope="aggregate",
            value=0.0,
            threshold=None,
            verdict=Verdict.SKIP,
            details={
                "message": "No routing metadata present in responses",
                "has_proof": False,
            },
        )

    from attest.detection.routing_proof import (
        RoutingProof,
        verify_routing_proof_against_model,
    )

    proof = RoutingProof.from_dict(proof_dict)
    is_match, reason = verify_routing_proof_against_model(claimed_model, proof)

    verdict = Verdict.SKIP if is_match else Verdict.FAIL
    val = 1.0 if is_match else 0.0

    return Score(
        id=None,
        run_id=run_id,
        method=MethodTier.ROUTING_PROOF.value,
        scope="aggregate",
        value=val,
        threshold=1.0,
        verdict=verdict,
        details={
            "has_proof": True,
            "signature_verified": False,
            "endpoint_slug": proof.endpoint_slug,
            "upstream_provider": proof.upstream_provider,
            "upstream_model": proof.upstream_model,
            "model_snapshot": proof.model_snapshot,
            "router": proof.router,
            "claimed_model": claimed_model,
            "is_match": is_match,
            "reason": reason,
        },
    )


def run_quick_checks(
    target_model: str,
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    prompts_map: dict[int, Any],
    run_id: int,
    all_run_samples: list[RawSample] | None = None,
    all_baseline_samples: list[RawSample] | None = None,
) -> list[Score]:
    """Execute all Level 0 quick checks.

    all_*_samples: the model claim, routing and tokenizer checks read response
    metadata and billed input tokens, which output truncation does not affect, so
    they get the samples that answer-based checks (seed) leave out.
    """
    meta_run = all_run_samples if all_run_samples is not None else run_samples
    meta_base = (
        all_baseline_samples if all_baseline_samples is not None else baseline_samples
    )
    from attest.detection.tokenizer import check_tokenizer_fingerprint

    scores = [
        check_model_claim(target_model, meta_run, run_id),
        check_routing_proof(target_model, meta_run, run_id),
        check_tokenizer_fingerprint(
            target_model,
            meta_run,
            prompts_map,
            run_id,
            baseline_samples=meta_base,
        ),
        check_system_fingerprint(baseline_samples, run_samples, run_id),
        check_seed_determinism(baseline_samples, run_samples, prompts_map, run_id),
    ]
    return scores
