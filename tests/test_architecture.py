"""
Architectural integrity and regression tests for Attest refactoring.
Tests domain models, decoupled comparator, fault-tolerant runner,
persistent tasks, and configuration synchronization.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from attest.comparator.compare import compare_runs_data
from attest.config import load_config
from attest.db import Database
from attest.models import (
    PromptItem,
    RawSample,
    Run,
    Score,
    Target,
    Verdict,
)
from attest.sampling.base import ProviderAdapter
from attest.sampling.runner import SamplingBatteryError, run_sampling_battery
from attest.service import AttestService


def test_verdict_aggregate_logic():
    """Verify centralized Verdict.aggregate behavior and edge cases."""
    # Empty -> SKIP
    assert Verdict.aggregate([]) == Verdict.SKIP

    # All PASS -> PASS
    s_pass1 = Score(
        id=1,
        run_id=1,
        method="exact",
        scope="g",
        value=1.0,
        threshold=1.0,
        verdict=Verdict.PASS,
    )
    s_pass2 = Score(
        id=2,
        run_id=1,
        method="jsd",
        scope="g",
        value=0.01,
        threshold=0.05,
        verdict=Verdict.PASS,
    )
    assert Verdict.aggregate([s_pass1, s_pass2]) == Verdict.PASS

    # With WARN -> WARN
    s_warn = Score(
        id=3,
        run_id=1,
        method="latency",
        scope="g",
        value=50.0,
        threshold=100.0,
        verdict=Verdict.WARN,
    )
    assert Verdict.aggregate([s_pass1, s_warn]) == Verdict.WARN

    # With FAIL -> FAIL
    s_fail = Score(
        id=4,
        run_id=1,
        method="model",
        scope="g",
        value=0.0,
        threshold=1.0,
        verdict=Verdict.FAIL,
    )
    assert Verdict.aggregate([s_pass1, s_warn, s_fail]) == Verdict.FAIL

    # Pure SKIP -> SKIP
    s_skip = Score(
        id=5,
        run_id=1,
        method="emb",
        scope="g",
        value=0.0,
        threshold=0.8,
        verdict=Verdict.SKIP,
    )
    assert Verdict.aggregate([s_skip]) == Verdict.SKIP
    assert Verdict.aggregate([s_pass1, s_skip]) == Verdict.PASS
    assert Verdict.aggregate([s_warn, s_skip]) == Verdict.WARN

    # Infrastructure failure ignored for model verdict
    s_infra_fail = Score(
        id=6,
        run_id=1,
        method="infrastructure",
        scope="g",
        value=0.0,
        threshold=1.0,
        verdict=Verdict.FAIL,
    )
    assert Verdict.aggregate([s_pass1, s_infra_fail]) == Verdict.PASS


def test_decoupled_pure_comparator():
    """Verify compare_runs_data executes purely in-memory without a database."""
    tgt_a = Target(id="tgt-a", base_url="https://api.a.com", model="gpt-4o")
    run_a = Run(
        id=101,
        target_id="tgt-a",
        baseline_id=1,
        battery_version="v1",
        started_at="2026-09-22T00:00:00Z",
    )
    scores_a = [
        Score(
            id=1,
            run_id=101,
            method="exact",
            scope="g",
            value=0.9,
            threshold=0.8,
            verdict=Verdict.PASS,
        )
    ]
    samples_a = [RawSample(prompt_id=1, raw_text="response a", latency_ms=120)]

    tgt_b = Target(id="tgt-b", base_url="https://api.b.com", model="gpt-4o")
    run_b = Run(
        id=102,
        target_id="tgt-b",
        baseline_id=1,
        battery_version="v1",
        started_at="2026-09-22T00:05:00Z",
    )
    scores_b = [
        Score(
            id=2,
            run_id=102,
            method="exact",
            scope="g",
            value=0.7,
            threshold=0.8,
            verdict=Verdict.FAIL,
        )
    ]
    samples_b = [RawSample(prompt_id=1, raw_text="response b", latency_ms=300)]

    res = compare_runs_data(
        target_a=tgt_a,
        run_a=run_a,
        scores_a=scores_a,
        samples_a=samples_a,
        target_b=tgt_b,
        run_b=run_b,
        scores_b=scores_b,
        samples_b=samples_b,
    )

    assert res.run_a.run_id == 101
    assert res.run_b.run_id == 102
    assert res.run_a.overall_verdict == Verdict.PASS
    assert res.run_b.overall_verdict == Verdict.FAIL
    assert res.run_a.median_latency_ms == 120.0
    assert res.run_b.median_latency_ms == 300.0
    assert res.winner == "a"


def test_db_get_run_report(tmp_path: Path):
    """Verify Database.get_run_report produces rich RunReport entity."""
    db_file = tmp_path / "test_report.db"
    db = Database(db_file)

    target = Target(id="test-tgt", base_url="https://api.test.com", model="gpt-4o")
    db.save_target(target)
    prompts = db.sync_prompts(
        [
            PromptItem(
                id=None,
                category="c1",
                text="q1",
                params={},
                samples_count=1,
                battery_version="v1",
            ),
            PromptItem(
                id=None,
                category="c2",
                text="q2",
                params={},
                samples_count=1,
                battery_version="v1",
            ),
        ],
        "v1",
    )
    b_id = db.create_baseline(target.id, "v1")
    r_id = db.create_run(target.id, b_id, "v1")
    db.save_run_samples(
        r_id,
        [
            RawSample(
                prompt_id=prompts[0].id,
                raw_text="ans1",
                latency_ms=100,
                usage={"total_tokens": 15},
            ),
            RawSample(
                prompt_id=prompts[1].id,
                raw_text="ans2",
                latency_ms=200,
                usage={"total_tokens": 25},
            ),
        ],
    )
    db.save_scores(
        scores=[
            Score(
                id=None,
                run_id=r_id,
                method="quick_model",
                scope="g",
                value=0.0,
                threshold=1.0,
                verdict=Verdict.FAIL,
                details={"claimed": "gpt-4o", "returned": "gpt-3.5"},
            ),
            Score(
                id=None,
                run_id=r_id,
                method="exact",
                scope="g",
                value=1.0,
                threshold=1.0,
                verdict=Verdict.PASS,
            ),
        ],
    )
    db.finish_run(r_id, "completed")

    report = db.get_run_report(r_id)
    assert report is not None
    assert report.run.id == r_id
    assert report.overall_verdict == Verdict.FAIL
    assert len(report.scores) == 2
    assert report.samples_count == 2
    assert report.total_tokens == 40
    assert report.estimated_cost_usd >= 0
    assert len(report.failure_diagnostics) == 1
    assert "gpt-4o" in report.failure_diagnostics[0]["message"]

    d = report.to_dict()
    assert d["run_id"] == r_id
    assert d["overall_verdict"] == "FAIL"
    assert d["total_tokens"] == 40


@pytest.mark.asyncio
async def test_fault_tolerant_sampling():
    """Verify run_sampling_battery tolerates partial failures and raises on exceeding threshold."""
    prompts = [
        PromptItem(
            id=i + 1,
            category="c",
            text=f"q{i + 1}",
            params={},
            samples_count=1,
            battery_version="v1",
        )
        for i in range(5)
    ]

    class FlakyAdapter(ProviderAdapter):
        def __init__(self, fail_indices: set[int]):
            self.fail_indices = fail_indices

        async def sample(
            self, prompt_id: int, prompt_text: str, params: dict, messages=None
        ) -> RawSample:
            if prompt_id in self.fail_indices:
                raise RuntimeError(f"Connection timed out on prompt {prompt_id}")
            return RawSample(prompt_id=prompt_id, raw_text=f"resp-{prompt_id}")

        async def close(self) -> None:
            pass

    # Case 1: 1 failure out of 5 (20%) with max_error_rate=0.25 -> should succeed with 4 samples
    adapter_ok = FlakyAdapter(fail_indices={1})
    samples = await run_sampling_battery(adapter_ok, prompts, max_error_rate=0.25)
    assert len(samples) == 4
    assert {s.prompt_id for s in samples} == {2, 3, 4, 5}

    # Case 2: 2 failures out of 5 (40%) with max_error_rate=0.20 -> should raise SamplingBatteryError
    adapter_bad = FlakyAdapter(fail_indices={1, 2})
    with pytest.raises(SamplingBatteryError) as exc_info:
        await run_sampling_battery(adapter_bad, prompts, max_error_rate=0.20)
    assert "40.0% > 20% max error threshold" in str(exc_info.value)


def test_sqlite_tasks_persistence(tmp_path: Path):
    """Verify multi-worker tasks table lifecycle in SQLite."""
    db_file = tmp_path / "test_tasks.db"
    db = Database(db_file)

    # 1. Create task
    db.create_task(task_id="t-100", target_id="target-alpha", task_type="audit")
    t1 = db.get_task("t-100")
    assert t1 is not None
    assert t1["task_id"] == "t-100"
    assert t1["target_id"] == "target-alpha"
    assert t1["status"] == "running"
    assert t1["completed"] == 0

    # 2. Update progress
    db.update_task_progress("t-100", completed=5, total=20)
    t2 = db.get_task("t-100")
    assert t2["completed"] == 5
    assert t2["total"] == 20

    # 3. Complete task
    db.complete_task("t-100", result={"verdict": "PASS"})
    t3 = db.get_task("t-100")
    assert t3["status"] == "completed"
    assert t3["result"] == {"verdict": "PASS"}

    # 4. Fail another task
    db.create_task(task_id="t-200", target_id="target-beta", task_type="baseline")
    db.fail_task("t-200", error="Auth failure")
    t4 = db.get_task("t-200")
    assert t4["status"] == "failed"
    assert t4["error"] == "Auth failure"

    # 5. Cleanup old tasks
    # Set updated_at artificially in the past
    with db.connection() as conn:
        conn.execute("UPDATE tasks SET updated_at = 1000.0 WHERE id = 't-100'")
    db.cleanup_old_tasks(max_age_seconds=100.0)
    assert db.get_task("t-100") is None
    assert db.get_task("t-200") is not None


def test_sync_targets_from_config(tmp_path: Path):
    """Verify sync_targets_from_config populates SQLite targets from attest.yaml."""
    cfg_file = tmp_path / "attest.yaml"
    cfg_content = """
database: "targets_sync.db"
targets:
  - id: "yaml-openai"
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o"
    key: "test-yaml-key-123"
    description: "Synced from YAML"
"""
    cfg_file.write_text(cfg_content)
    db_file = tmp_path / "targets_sync.db"
    db = Database(db_file)

    cfg = load_config(str(cfg_file))
    service = AttestService(db=db, config=cfg)

    synced_count = service.sync_targets_from_config()
    assert synced_count == 1

    target = db.get_target("yaml-openai")
    assert target is not None
    assert target.base_url == "https://api.openai.com/v1"
    assert target.model == "gpt-4o"
    assert target.encrypted_key is not None
