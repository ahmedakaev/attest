"""Unit tests for Provider Battle & run comparison."""

from fastapi.testclient import TestClient

from attest.comparator.compare import compare_runs
from attest.config import AttestConfig
from attest.db import Database
from attest.models import PromptItem, RawSample, RunStatus, Score, Target, Verdict
from attest.web.app import create_app


def test_compare_runs_logic(tmp_path):
    db_file = tmp_path / "test_compare.db"
    db = Database(str(db_file))

    # Add Target A (e.g. baseline or standard provider)
    db.save_target(
        Target(
            id="provider-a",
            base_url="https://api.provider-a.com/v1",
            model="gpt-6-astra",
        )
    )
    # Add Target B (e.g. high-speed cloud cluster)
    db.save_target(
        Target(
            id="provider-b",
            base_url="https://api.provider-b.com/v1",
            model="gpt-6-astra",
            wire_model="azure/gpt-6-astra/test-azure200-de20fdc4",
        )
    )

    # Sync a prompt so prompt_id passes foreign key
    prompts = db.sync_prompts(
        [
            PromptItem(
                id=None,
                category="one_token",
                text="Name random digit",
                params={"max_tokens": 1},
                samples_count=1,
                battery_version="v1",
            )
        ],
        "v1",
    )
    pid = prompts[0].id
    assert pid is not None

    base_id = db.create_baseline(target_id="provider-a", battery_version="v1")

    # Run A
    run_a_id = db.create_run(
        target_id="provider-a",
        baseline_id=base_id,
        battery_version="v1",
        status=RunStatus.COMPLETED,
    )
    db.finish_run(run_a_id, status=RunStatus.COMPLETED)

    samples_a = [
        RawSample(
            prompt_id=pid,
            raw_text="Answer A",
            latency_ms=1000,
            usage={"completion_tokens": 50},
            headers={"server": "nginx"},
        )
        for _ in range(5)
    ]
    db.save_run_samples(run_a_id, samples_a)
    db.save_scores(
        [
            Score(
                id=None,
                run_id=run_a_id,
                method="assertions",
                scope="aggregate",
                value=1.0,
                threshold=1.0,
                verdict=Verdict.PASS,
                details={"total_assertions": 10, "passed_assertions": 10},
            ),
            Score(
                id=None,
                run_id=run_a_id,
                method="latency_tps",
                scope="aggregate",
                value=0.0,
                threshold=0.5,
                verdict=Verdict.PASS,
                details={"run_tps": {"median": 50.0}},
            ),
        ]
    )

    # Run B (2.5x faster cluster on Azure via LiteLLM)
    run_b_id = db.create_run(
        target_id="provider-b",
        baseline_id=base_id,
        battery_version="v1",
        status=RunStatus.COMPLETED,
    )
    db.finish_run(run_b_id, status=RunStatus.COMPLETED)

    samples_b = [
        RawSample(
            prompt_id=pid,
            raw_text="Answer B",
            latency_ms=400,
            usage={"completion_tokens": 50},
            model_returned="azure/gpt-6-astra/test-azure200-de20fdc4",
            headers={
                "server": "uvicorn",
                "openai-model": "azure/gpt-6-astra/test-azure200-de20fdc4",
            },
        )
        for _ in range(5)
    ]
    db.save_run_samples(run_b_id, samples_b)
    db.save_scores(
        [
            Score(
                id=None,
                run_id=run_b_id,
                method="assertions",
                scope="aggregate",
                value=1.0,
                threshold=1.0,
                verdict=Verdict.PASS,
                details={"total_assertions": 10, "passed_assertions": 10},
            ),
            Score(
                id=None,
                run_id=run_b_id,
                method="latency_tps",
                scope="aggregate",
                value=1.5,
                threshold=1.0,
                verdict=Verdict.WARN,
                details={"run_tps": {"median": 125.0}},
            ),
            Score(
                id=None,
                run_id=run_b_id,
                method="infrastructure",
                scope="aggregate",
                value=0.95,
                threshold=None,
                verdict=Verdict.PASS,
                details={
                    "proxy_gateway": "litellm",
                    "upstream_cloud": "azure",
                    "deployment_id": "test-azure200-de20fdc4",
                    "summary_ru": "Обнаружен шлюз LiteLLM с маршрутизацией в Azure",
                },
            ),
        ]
    )

    result = compare_runs(db, run_a_id, run_b_id)

    assert result.run_a.target_id == "provider-a"
    assert result.run_b.target_id == "provider-b"
    assert result.run_b.infrastructure.proxy_gateway == "litellm"
    assert result.run_b.infrastructure.upstream_cloud == "azure"
    assert result.deltas["tps_multiplier_b_vs_a"] == 2.5
    assert result.winner == "b"
    assert "быстрее" in result.recommendation_ru or "faster" in result.recommendation_en


def test_api_compare_endpoint(tmp_path):
    db_file = tmp_path / "test_api_compare.db"
    cfg = AttestConfig(database=str(db_file))
    db = Database(cfg.database)

    # Setup targets and runs
    db.save_target(Target(id="target-1", base_url="https://api.1.com/v1", model="m1"))
    db.save_target(Target(id="target-2", base_url="https://api.2.com/v1", model="m1"))
    base_id = db.create_baseline(target_id="target-1", battery_version="v1")
    r1_id = db.create_run(
        target_id="target-1",
        baseline_id=base_id,
        battery_version="v1",
        status=RunStatus.COMPLETED,
    )
    r2_id = db.create_run(
        target_id="target-2",
        baseline_id=base_id,
        battery_version="v1",
        status=RunStatus.COMPLETED,
    )
    db.finish_run(r1_id, status=RunStatus.COMPLETED)
    db.finish_run(r2_id, status=RunStatus.COMPLETED)

    app = create_app(cfg)
    client = TestClient(app, base_url="http://localhost")

    resp = client.get(f"/api/compare?run_a={r1_id}&run_b={r2_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "run_a" in data
    assert "run_b" in data
    assert "recommendation_ru" in data
    assert "deltas" in data
