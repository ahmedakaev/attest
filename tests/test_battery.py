from pathlib import Path

from attest.battery.loader import (
    estimate_battery_cost,
    load_battery,
    resolve_battery_path,
)


def test_resolve_battery_path():
    assert resolve_battery_path("quick").name == "quick.yaml"
    assert resolve_battery_path("anti_spoof").name == "anti_spoof.yaml"
    assert resolve_battery_path("anti-spoof").name == "anti_spoof.yaml"
    assert resolve_battery_path("reasoning").name == "reasoning.yaml"
    assert resolve_battery_path("v1").name == "v1.yaml"
    assert resolve_battery_path("frontier_probe").name == "frontier_probe.yaml"
    assert resolve_battery_path("all_tests").name == "all_tests.yaml"
    assert (
        resolve_battery_path(None, default="batteries/quick.yaml").name == "quick.yaml"
    )


def test_load_default_battery_v1():
    battery_path = Path("batteries/v1.yaml")
    assert battery_path.exists()
    version, prompts = load_battery(battery_path)

    assert version == "v1"
    assert len(prompts) >= 30

    categories = {p.category for p in prompts}
    assert "one_token" in categories
    assert "factual" in categories
    assert "code" in categories
    assert "style" in categories
    assert "temporal_cutoff" in categories
    assert "concurrency_memory_safety" in categories
    assert "recursive_schema" in categories
    assert "tensor_precision" in categories
    assert "mmlu_pro_advanced" in categories
    assert "proxy_leak" in categories


def test_load_anti_spoof_battery():
    version, prompts = load_battery("anti_spoof")
    assert version.startswith("anti-spoof-2026")
    assert len(prompts) >= 13

    categories = {p.category for p in prompts}
    assert "bpe_fingerprint" in categories
    assert "micro_discriminator" in categories
    assert "cross_lingual_probe" in categories
    assert "temporal_cutoff" in categories
    assert "concurrency_memory_safety" in categories
    assert "recursive_schema" in categories
    assert "tensor_precision" in categories
    assert "mmlu_pro_advanced" in categories
    assert "proxy_canary" in categories

    est = estimate_battery_cost(prompts)
    assert est["total_requests"] >= 20
    assert est["est_cost_usd"] < 0.10


def test_load_reasoning_battery():
    version, prompts = load_battery("reasoning")
    assert version == "reasoning-2026"
    assert len(prompts) == 7

    categories = {p.category for p in prompts}
    assert "combinatorial_csp" in categories
    assert "aime_math" in categories
    assert "concurrency_invariants" in categories
    assert "game_theory" in categories
    assert "discrete_deduction" in categories
    assert "bpe_fingerprint" in categories

    est = estimate_battery_cost(prompts)
    assert est["total_requests"] == 25
    assert est["est_cost_usd"] < 0.05


def test_load_quick_battery():
    version, prompts = load_battery("quick")
    assert version == "quick-v1"
    assert len(prompts) >= 10
    est = estimate_battery_cost(prompts)
    assert est["total_requests"] == 87


def test_load_frontier_probe_battery():
    version, prompts = load_battery("frontier_probe")
    assert version == "frontier-probe-2026"
    assert len(prompts) == 2
    est = estimate_battery_cost(prompts)
    assert est["total_requests"] == 4


def test_load_all_tests_battery():
    version, prompts = load_battery("all_tests")
    assert version == "all-tests-2026"
    assert len(prompts) == 42
    est = estimate_battery_cost(prompts)
    assert est["total_requests"] == 162


def test_estimate_battery_cost():
    _version, prompts = load_battery("batteries/v1.yaml")
    est = estimate_battery_cost(prompts)

    assert est["total_requests"] > 300
    assert est["est_total_tokens"] > 1000
    assert est["est_cost_usd"] > 0.0
    assert "one_token" in est["by_category"]
