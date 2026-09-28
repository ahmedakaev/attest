"""
Tests for per-target run history (TTFT, speed, billing across runs).
"""

import json

import httpx
import pytest
from click.testing import CliRunner

from attest.cli import cli
from attest.config import AttestConfig
from attest.db import Database
from attest.models import PromptItem, RawSample, Score, Target, Verdict
from attest.reporting.history import build_target_history
from attest.web.app import create_app


def _seed(db_path) -> Database:
    db = Database(db_path)
    db.save_target(Target(id="prov", base_url="https://api.example.com/v1", model="m"))
    pid = db.sync_prompts(
        [
            PromptItem(
                id=None,
                category="factual",
                text="q",
                params={},
                samples_count=3,
                battery_version="v1",
            )
        ],
        "v1",
    )[0].id
    base_id = db.create_baseline_with_samples(
        "prov", "v1", [RawSample(prompt_id=pid, raw_text="a", latency_ms=900)]
    )

    def run(ttft, latency, overcharge, verdict):
        run_id = db.create_run("prov", base_id, "v1")
        db.save_run_samples(
            run_id,
            [
                RawSample(
                    prompt_id=pid,
                    raw_text="a" * 100,
                    latency_ms=latency,
                    ttft_ms=ttft,
                    usage={"completion_tokens": 51},
                )
                for _ in range(3)
            ],
        )
        db.save_scores(
            [
                Score(
                    id=None,
                    run_id=run_id,
                    method="billing",
                    scope="aggregate",
                    value=overcharge,
                    threshold=0.25,
                    verdict=verdict,
                    details={},
                )
            ]
        )

    run(400, 1400, 0.0, Verdict.PASS)  # 50 decode tokens in 1 s
    run(2000, 2500, 0.12, Verdict.WARN)  # queueing grew, decode 100 tok/s
    run(None, 2000, 0.0, Verdict.PASS)  # unstreamed run: no TTFT
    return db


def test_build_target_history(tmp_path):
    db = _seed(tmp_path / "h.db")
    history = build_target_history(db, "prov")

    assert [h["run_id"] for h in history] == sorted(h["run_id"] for h in history)
    first, second, third = history
    assert first["ttft_ms"] == 400 and first["tps"] == 50.0
    assert first["tps_decode_only"] is True
    assert second["ttft_ms"] == 2000 and second["tps"] == 100.0
    assert second["overcharge"] == 0.12 and second["verdict"] == "WARN"
    assert third["ttft_ms"] is None and third["tps_decode_only"] is False
    assert third["tps"] == 25.5  # end-to-end: 51 tokens / 2 s
    assert first["iris_dilution"] is None

    assert len(build_target_history(db, "prov", limit=2)) == 2
    assert build_target_history(db, "missing") == []


def test_history_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "h.db"
    _seed(db_path)
    cfg_path = tmp_path / "attest.yaml"
    cfg_path.write_text(f"database: {db_path}\n")

    runner = CliRunner()
    res = runner.invoke(cli, ["report", "history", "prov", "-c", str(cfg_path)])
    assert res.exit_code == 0, res.output
    assert "History: prov" in res.output
    assert "+12%" in res.output

    res = runner.invoke(
        cli, ["report", "history", "prov", "--json", "-c", str(cfg_path)]
    )
    assert res.exit_code == 0
    assert len(json.loads(res.output)) == 3

    res = runner.invoke(cli, ["report", "history", "nope", "-c", str(cfg_path)])
    assert res.exit_code == 1


@pytest.mark.asyncio
async def test_history_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "h.db"
    _seed(db_path)
    app = create_app(AttestConfig(database=str(db_path)))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        resp = await client.get("/api/targets/prov/history?limit=2")
        assert resp.status_code == 200
        assert [h["ttft_ms"] for h in resp.json()] == [2000, None]

        assert (await client.get("/api/targets/nope/history")).status_code == 404
