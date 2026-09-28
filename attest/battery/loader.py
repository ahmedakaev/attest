"""
Loader and cost estimator for YAML prompt batteries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from attest.comparator.assertion import validate_assertion
from attest.models import PromptAssertion, PromptItem


def resolve_battery_path(
    battery_path: str | Path | None = None,
    default: str | Path | None = None,
) -> Path:
    """
    Resolves a battery alias ('quick', 'anti_spoof', 'reasoning', 'v1') or file path
    to an existing Path on disk.
    """
    bundled_path = Path(__file__).parent / "default_battery.yaml"

    target_candidate = battery_path or default
    if target_candidate:
        p = Path(target_candidate)
        if p.exists() and p.is_file():
            return p

        clean_name = str(target_candidate).strip().lower().replace("-", "_")
        yaml_name = (
            f"{clean_name}.yaml"
            if not clean_name.endswith((".yaml", ".yml"))
            else clean_name
        )

        cwd_cand = Path.cwd() / "batteries" / yaml_name
        if cwd_cand.exists() and cwd_cand.is_file():
            return cwd_cand

        repo_cand = (
            Path(__file__).resolve().parent.parent.parent / "batteries" / yaml_name
        )
        if repo_cand.exists() and repo_cand.is_file():
            return repo_cand

    std_cwd = Path.cwd() / "batteries" / "v1.yaml"
    if std_cwd.exists():
        return std_cwd

    std_repo = Path(__file__).resolve().parent.parent.parent / "batteries" / "v1.yaml"
    if std_repo.exists():
        return std_repo

    if bundled_path.exists():
        return bundled_path

    raise FileNotFoundError(
        f"Battery file not found for '{battery_path}' or bundled fallback."
    )


def _prompt_key(p: PromptItem) -> tuple[str, str, str]:
    return (p.category, p.text, json.dumps(p.messages, sort_keys=True))


def load_battery(
    battery_path: str | Path | None = None,
    _chain: tuple[Path, ...] = (),
) -> tuple[str, list[PromptItem]]:
    """
    Loads and validates a battery YAML file.
    Falls back to package bundled battery if local path does not exist.

    `include: [iris, quick, ...]` pulls in other batteries first (recursively), so a
    defence level contains every lower level without copying prompts. The same prompt
    (category, text, messages) is kept once, with the largest sample count. All
    prompts take this file's version, so levels sharing one version share prompt rows
    in the database and a baseline captured at a higher level covers the lower ones.
    """
    target_path = resolve_battery_path(battery_path)
    if target_path.resolve() in _chain:
        raise ValueError(f"Battery include cycle through '{target_path}'")
    chain = (*_chain, target_path.resolve())

    with open(target_path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    version = str(data.get("version", "v1"))
    includes = data.get("include") or []
    if not isinstance(includes, list):
        raise TypeError(f"Battery '{target_path}': include must be a list")
    prompts_data = data.get("prompts") or []
    if not isinstance(prompts_data, list) or (not prompts_data and not includes):
        raise ValueError(f"Battery '{target_path}' contains no valid prompts list.")

    merged: dict[tuple[str, str, str], PromptItem] = {}

    def add(p: PromptItem) -> None:
        key = _prompt_key(p)
        if key in merged:
            merged[key].samples_count = max(merged[key].samples_count, p.samples_count)
        else:
            p.battery_version = version
            merged[key] = p

    for inc in includes:
        inc_name = str(inc).strip()
        inc_path = resolve_battery_path(inc_name)
        # resolve_battery_path falls back to v1 for unknown names; refuse that here
        if inc_path.stem.lower() != Path(inc_name).stem.lower().replace("-", "_"):
            raise ValueError(
                f"Battery '{target_path}': included battery '{inc_name}' not found"
            )
        for p in load_battery(inc_path, chain)[1]:
            add(p)

    items: list[PromptItem] = []
    for idx, item in enumerate(prompts_data):
        category = str(item.get("category", "general")).strip()
        text = str(item.get("text", "")).strip()
        raw_messages = item.get("messages")
        messages = (
            raw_messages if isinstance(raw_messages, list) and raw_messages else None
        )
        if not text and messages:
            for m in reversed(messages):
                if isinstance(m, dict) and m.get("role") == "user":
                    text = str(m.get("content", ""))
                    break
            if not text:
                text = str(messages)
        elif not text:
            raise ValueError(f"Prompt at index {idx} in {target_path} has empty text.")

        params = dict(item.get("params", {}))
        if "system_prompt" in item and "system_prompt" not in params:
            params["system_prompt"] = str(item["system_prompt"])
        samples_count = int(item.get("samples", 1))
        samples_count = max(samples_count, 1)

        raw_assertions = item.get("assert", [])
        assertions: list[PromptAssertion] = []
        if isinstance(raw_assertions, list):
            for a in raw_assertions:
                if isinstance(a, dict) and "type" in a:
                    error = validate_assertion(str(a["type"]), a.get("value"))
                    if error:
                        raise ValueError(
                            f"Prompt at index {idx} in {target_path}: {error}"
                        )
                    assertions.append(
                        PromptAssertion(
                            type=str(a["type"]),
                            value=a.get("value"),
                            optional=bool(a.get("optional", False)),
                        )
                    )

        items.append(
            PromptItem(
                id=None,
                category=category,
                text=text,
                params=params,
                samples_count=samples_count,
                battery_version=version,
                assertions=assertions,
                messages=messages,
            )
        )

    for p in items:
        add(p)
    return version, list(merged.values())


def estimate_battery_cost(
    prompts: list[PromptItem],
    input_cost_per_1m: float = 2.50,
    output_cost_per_1m: float = 10.00,
) -> dict[str, Any]:
    """
    Estimate total requests, token volume, and dollar cost for a complete battery run.
    Uses conservative prompt token lengths + requested max_tokens.
    """
    total_requests = 0
    est_prompt_tokens = 0
    est_completion_tokens = 0
    categories_breakdown: dict[str, dict[str, int]] = {}

    for p in prompts:
        # Rough token estimation: 1 token ~= 4 characters for English / 1 token per Asian char
        text_tokens = max(5, int(len(p.text) / 3.5))
        max_output_tokens = int(p.params.get("max_tokens", 50))
        n_samples = p.samples_count

        total_requests += n_samples
        prompt_t = text_tokens * n_samples
        comp_t = max_output_tokens * n_samples

        est_prompt_tokens += prompt_t
        est_completion_tokens += comp_t

        if p.category not in categories_breakdown:
            categories_breakdown[p.category] = {"requests": 0, "tokens": 0}
        categories_breakdown[p.category]["requests"] += n_samples
        categories_breakdown[p.category]["tokens"] += prompt_t + comp_t

    total_tokens = est_prompt_tokens + est_completion_tokens
    est_cost_usd = (est_prompt_tokens / 1_000_000) * input_cost_per_1m + (
        est_completion_tokens / 1_000_000
    ) * output_cost_per_1m

    return {
        "total_prompts": len(prompts),
        "total_requests": total_requests,
        "est_prompt_tokens": est_prompt_tokens,
        "est_completion_tokens": est_completion_tokens,
        "est_total_tokens": total_tokens,
        "est_cost_usd": est_cost_usd,
        "by_category": categories_breakdown,
    }
