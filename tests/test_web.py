"""
Tests for Attest FastAPI Web Dashboard and API endpoints.
"""

import time
from pathlib import Path

import httpx
import pytest

from attest import __version__
from attest.config import AttestConfig
from attest.db import Database
from attest.models import PromptItem, RawSample, Score, Target, Verdict
from attest.web.app import create_app, resolve_locale


@pytest.fixture
def test_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AttestConfig:
    monkeypatch.chdir(tmp_path)
    db_path = str(tmp_path / "test_web.db")
    battery_path = str(Path(__file__).parent.parent / "batteries" / "v1.yaml")

    cfg = AttestConfig(
        database=db_path,
        battery=battery_path,
    )

    # Initialize DB with a modern sample target
    db = Database(db_path)
    db.save_target(
        Target(
            id="test-gpt-5-6-luna",
            base_url="https://api.openai.com/v1",
            model="gpt-5.6-luna",
            description="Testing endpoint",
        )
    )
    return cfg


@pytest.fixture(autouse=True)
def mock_web_workers(monkeypatch: pytest.MonkeyPatch):
    from attest.models import Baseline, Run, Verdict
    from attest.service import AuditResult, BaselineCaptureResult

    async def mock_audit_async(self, target, **kwargs):
        on_sample_done = kwargs.get("on_sample_done")
        if on_sample_done:
            on_sample_done(RawSample(prompt_id=1, raw_text="mock-sample"))
        dummy_run = Run(
            id=1,
            target_id=target.id,
            baseline_id=1,
            battery_version="v1",
            started_at="2026-09-22T00:00:00Z",
            finished_at="2026-09-22T00:00:01Z",
            status="completed",
        )
        dummy_base = Baseline(
            id=1,
            target_id=target.id,
            battery_version="v1",
            captured_at="2026-09-22T00:00:00Z",
        )
        return AuditResult(
            run=dummy_run,
            target=target,
            baseline=dummy_base,
            scores=[],
            overall_verdict=Verdict.PASS,
            run_samples=[],
            prompts=[],
            duration_s=0.01,
            total_tokens=10,
            est_cost_usd=0.001,
            summary_message="Mocked audit",
            source_desc="direct",
            streak=1,
            alert_dispatched=False,
            failure_diagnostics=[],
        )

    async def mock_baseline_async(self, target, **kwargs):
        on_sample_done = kwargs.get("on_sample_done")
        if on_sample_done:
            on_sample_done(RawSample(prompt_id=1, raw_text="mock-sample"))
        return BaselineCaptureResult(
            baseline_id=1,
            samples=[],
            prompts=[],
            total_requests=0,
            captured_at="2026-09-22T00:00:00Z",
        )

    monkeypatch.setattr(
        "attest.service.AttestService.audit_target_async", mock_audit_async
    )
    monkeypatch.setattr(
        "attest.service.AttestService.capture_baseline_async", mock_baseline_async
    )


@pytest.mark.asyncio
async def test_spa_root_and_static(test_cfg: AttestConfig):
    app = create_app(test_cfg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Attest" in resp.text

        resp_css = await client.get("/static/app.css")
        assert resp_css.status_code == 200
        assert "--bg-base" in resp_css.text

        resp_js = await client.get("/static/app.js")
        assert resp_js.status_code == 200
        assert "AttestApp" in resp_js.text

        resp_module_js = await client.get("/static/js/app.js")
        assert resp_module_js.status_code == 200


@pytest.mark.asyncio
async def test_api_stats(test_cfg: AttestConfig):
    app = create_app(test_cfg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_targets"] == 1
        assert data["active_baselines"] == 0
        assert data["total_audits"] == 0


@pytest.mark.asyncio
async def test_api_targets_crud_and_estimate(test_cfg: AttestConfig):
    app = create_app(test_cfg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        # List targets
        resp = await client.get("/api/targets")
        assert resp.status_code == 200
        targets = resp.json()
        assert len(targets) == 1
        assert targets[0]["id"] == "test-gpt-5-6-luna"
        assert targets[0]["model"] == "gpt-5.6-luna"

        # Add a new target
        new_target = {
            "id": "claude-fable-5-1",
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-fable-5-1",
            "key": "test-ant-auth-key-123",
            "description": "Anthropic Claude endpoint",
        }
        resp_create = await client.post("/api/targets", json=new_target)
        assert resp_create.status_code == 200
        assert resp_create.json()["ok"] is True

        # Verify added
        resp_after = await client.get("/api/targets")
        assert len(resp_after.json()) == 2

        # Get budget estimate (default v1 and specific batteries)
        resp_est = await client.get("/api/targets/claude-fable-5-1/estimate")
        assert resp_est.status_code == 200
        est_data = resp_est.json()
        assert est_data["total_prompts"] > 0
        assert est_data["total_requests"] > 0
        assert est_data["est_total_tokens"] > 0

        resp_est_anti = await client.get(
            "/api/targets/claude-fable-5-1/estimate?battery=anti_spoof"
        )
        assert resp_est_anti.status_code == 200
        est_anti = resp_est_anti.json()
        assert est_anti["battery_version"].startswith("anti-spoof-2026")
        assert est_anti["total_requests"] >= 20

        resp_est_reason = await client.get(
            "/api/targets/claude-fable-5-1/estimate?battery=reasoning"
        )
        assert resp_est_reason.status_code == 200
        est_reason = resp_est_reason.json()
        assert est_reason["battery_version"] == "reasoning-2026"
        assert est_reason["total_requests"] == 25

        # Delete target
        resp_del = await client.delete("/api/targets/claude-fable-5-1")
        assert resp_del.status_code == 200
        assert resp_del.json()["ok"] is True

        resp_del_404 = await client.delete("/api/targets/claude-fable-5-1")
        assert resp_del_404.status_code == 404


@pytest.mark.asyncio
async def test_api_providers_catalog_and_studio(tmp_path):
    db_file = tmp_path / "test_studio.db"
    db = Database(db_file)

    prompts = [
        PromptItem(
            id=None,
            category="one_token",
            text="Pick digit",
            params={"max_tokens": 1},
            samples_count=5,
            battery_version="v1",
        )
    ]
    synced = db.sync_prompts(prompts, "v1")

    # Pre-create official target and active baseline
    db.save_target(
        Target(
            id="official-openai",
            base_url="https://api.openai.com/v1",
            model="gpt-5.6-luna",
        )
    )
    b_id = db.create_baseline("official-openai", "v1")
    db.save_baseline_samples(
        b_id, [RawSample(prompt_id=synced[0].id, raw_text="test", latency_ms=10)]
    )

    cfg = AttestConfig(database=str(db_file))
    app = create_app(cfg)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        # 1. Providers catalog
        resp_prov = await client.get("/api/providers")
        assert resp_prov.status_code == 200
        providers = resp_prov.json()
        assert len(providers) >= 7
        openrouter_p = next(p for p in providers if p["id"] == "openrouter")
        assert "openrouter.ai" in openrouter_p["base_url"]

        # 2. Studio verify with resolved baseline
        studio_req = {
            "reference_model": "gpt-5.6-luna",
            "candidate_provider": "custom",
            "candidate_url": "https://api.gateway-example.com/v1",
            "candidate_model_call": "gpt-5.6-luna",
            "candidate_key": "gw-testkey",
            "battery": "quick",
        }
        resp_verify = await client.post("/api/studio/verify", json=studio_req)
        assert resp_verify.status_code == 200
        verify_data = resp_verify.json()
        assert "task_id" in verify_data
        assert verify_data["baseline_id"] == b_id

        # Verify candidate target was saved in DB
        cand = db.get_target("custom-gpt-5-6-luna")
        assert cand is not None
        assert cand.model == "gpt-5.6-luna"
        assert cand.base_url == "https://api.gateway-example.com/v1"
        assert cand.encrypted_key is not None

        # 3. Studio verify with namespaced aggregator call (e.g. OpenRouter openai/gpt-5.6-luna)
        or_req = {
            "reference_model": "gpt-5.6-luna",
            "candidate_provider": "openrouter",
            "candidate_url": "https://openrouter.ai/api/v1",
            "candidate_model_call": "openai/gpt-5.6-luna",
            "candidate_key": "test-or-fixture-key",
            "battery": "quick",
        }
        resp_or = await client.post("/api/studio/verify", json=or_req)
        assert resp_or.status_code == 200
        or_data = resp_or.json()
        assert "task_id" in or_data
        assert or_data["baseline_id"] == b_id

        cand_or = db.get_target("openrouter-openai-gpt-5-6-luna")
        assert cand_or is not None
        assert cand_or.model == "gpt-5.6-luna"
        assert cand_or.wire_model == "openai/gpt-5.6-luna"
        # Verify cross-provider auto resolution connects candidate to official baseline
        res_b, res_src = db.resolve_target_baseline(cand_or.id)
        assert res_b is not None
        assert res_b.id == b_id
        assert "official-openai" in res_src

        # 4. Studio verify with explicit baseline_id (historical revision / drift check)
        b_hist_id = db.create_baseline(
            "official-openai", "v1", notes="Historical snapshot"
        )
        db.save_baseline_samples(
            b_hist_id,
            [RawSample(prompt_id=synced[0].id, raw_text="old", latency_ms=12)],
        )

        resp_baselines = await client.get("/api/baselines?model=gpt-5.6-luna")
        assert resp_baselines.status_code == 200
        baselines_list = resp_baselines.json()
        assert len(baselines_list) >= 2
        assert baselines_list[0]["id"] == b_hist_id
        assert baselines_list[0]["status"] == "active"
        assert baselines_list[1]["status"] == "superseded"

        # Verify explicitly targeting historical baseline
        hist_req = {
            "reference_model": "gpt-5.6-luna",
            "candidate_provider": "custom",
            "candidate_url": "https://api.gateway-example.com/v1",
            "candidate_model_call": "gpt-5.6-luna",
            "baseline_id": b_id,  # Auditing against original baseline
        }
        resp_hist = await client.post("/api/studio/verify", json=hist_req)
        assert resp_hist.status_code == 200
        assert resp_hist.json()["baseline_id"] == b_id

        # 5. Studio verify without baseline raises 400
        bad_req = {
            "reference_model": "non-existent-model",
            "candidate_provider": "custom",
            "candidate_url": "https://test.api/v1",
            "candidate_model_call": "non-existent",
        }
        resp_bad = await client.post("/api/studio/verify", json=bad_req)
        assert resp_bad.status_code == 400


@pytest.mark.asyncio
async def test_api_export_and_schedules(test_cfg: AttestConfig):
    app = create_app(test_cfg)
    db = Database(test_cfg.database)

    # Setup run with samples
    t_id = "test-gpt-5-6-luna"
    synced = db.sync_prompts(
        [
            PromptItem(
                id=None,
                category="general",
                text="hello",
                params={},
                samples_count=1,
                battery_version="v1",
            )
        ],
        "v1",
    )
    p_id = synced[0].id
    assert p_id is not None

    b_id = db.create_baseline(t_id, "v1", notes="Baseline for export")
    r_id = db.create_run(t_id, b_id, "v1", trigger="studio")
    db.save_run_samples(
        r_id, [RawSample(prompt_id=p_id, raw_text="test output", latency_ms=100)]
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        # 0. Get Run Details
        resp_details = await client.get(f"/api/runs/{r_id}")
        assert resp_details.status_code == 200
        det_data = resp_details.json()
        assert det_data["run"]["id"] == r_id
        assert det_data["target"]["id"] == t_id
        assert det_data["baseline"]["id"] == b_id
        assert det_data["run"]["samples_count"] == 1

        # 1. Export JSON
        resp_json = await client.get(f"/api/runs/{r_id}/export?format=json")
        assert resp_json.status_code == 200
        data = resp_json.json()
        assert data["attest_version"] == __version__
        assert data["target"]["id"] == t_id
        assert data["baseline"]["id"] == b_id
        assert data["run"]["id"] == r_id
        assert data["samples_count"] == 1
        assert "Content-Disposition" in resp_json.headers

        # 2. Export HTML (Russian by default)
        resp_html = await client.get(f"/api/runs/{r_id}/export?format=html")
        assert resp_html.status_code == 200
        assert "text/html" in resp_html.headers["content-type"]
        assert "<!DOCTYPE html>" in resp_html.text
        assert "Отчет о верификации и аудите на подмену" in resp_html.text
        assert t_id in resp_html.text

        # Export HTML (explicit English)
        resp_html_en = await client.get(
            f"/api/runs/{r_id}/export?format=html&locale=en"
        )
        assert resp_html_en.status_code == 200
        assert "Attest Verification & Anti-Spoofing Audit Report" in resp_html_en.text

        # 3. Schedules API CRUD
        # List initially empty
        resp_s = await client.get("/api/schedules")
        assert resp_s.status_code == 200
        assert resp_s.json() == []

        # Create schedule
        sched_payload = {
            "target_id": t_id,
            "interval_hours": 24,
            "battery": "quick",
            "enabled": True,
        }
        resp_create = await client.post("/api/schedules", json=sched_payload)
        assert resp_create.status_code == 200
        sched_id = resp_create.json()["id"]

        # List now has 1
        resp_s2 = await client.get("/api/schedules")
        assert resp_s2.status_code == 200
        s_list = resp_s2.json()
        assert len(s_list) == 1
        assert s_list[0]["id"] == sched_id
        assert s_list[0]["target_id"] == t_id
        assert s_list[0]["interval_hours"] == 24
        assert s_list[0]["has_baseline"] is True

        # Trigger schedule now
        resp_trig = await client.post(f"/api/schedules/{sched_id}/trigger")
        assert resp_trig.status_code == 200
        assert "task_id" in resp_trig.json()

        # Delete schedule
        resp_del = await client.delete(f"/api/schedules/{sched_id}")
        assert resp_del.status_code == 200
        assert resp_del.json()["deleted"] is True


@pytest.mark.asyncio
async def test_task_eviction_and_cleanup():
    from attest.web.app import TASKS, _cleanup_tasks, _register_task

    TASKS.clear()
    now = time.time()

    # Old completed task (2 hours ago)
    TASKS["old-done"] = {
        "task_id": "old-done",
        "target_id": "tgt1",
        "type": "audit",
        "status": "completed",
        "started_at": now - 7200,
    }
    # Recent completed task (5 minutes ago)
    TASKS["recent-done"] = {
        "task_id": "recent-done",
        "target_id": "tgt1",
        "type": "audit",
        "status": "completed",
        "started_at": now - 300,
    }
    # Still running task (10 hours ago) -> must NOT be evicted by TTL
    TASKS["running-long"] = {
        "task_id": "running-long",
        "target_id": "tgt1",
        "type": "audit",
        "status": "running",
        "started_at": now - 36000,
    }

    _cleanup_tasks(max_age_seconds=3600, max_items=100)

    assert "old-done" not in TASKS
    assert "recent-done" in TASKS
    assert "running-long" in TASKS

    # Test max items bounding
    for i in range(15):
        _register_task(f"t-{i}", "tgt", "audit")
        TASKS[f"t-{i}"]["status"] = "completed"

    _cleanup_tasks(max_age_seconds=99999, max_items=5)
    assert len(TASKS) <= 5


@pytest.mark.asyncio
async def test_providers_catalog_env_key(
    test_cfg: AttestConfig, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-prov-key-1234")
    app = create_app(test_cfg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        resp = await client.get("/api/providers")
        assert resp.status_code == 200
        providers = resp.json()
        assert len(providers) > 0
        or_prov = next((p for p in providers if p["id"] == "openrouter"), None)
        assert or_prov is not None
        assert or_prov["env_key"]["has_key"] is True
        assert "tes...1234" in or_prov["env_key"]["preview"]
        assert or_prov["env_key"]["source"] == "OPENROUTER_API_KEY"


@pytest.mark.asyncio
async def test_fetch_remote_models_route(test_cfg: AttestConfig):
    import respx

    app = create_app(test_cfg)
    fake_models_response = {
        "object": "list",
        "data": [
            {"id": "gpt-4o", "object": "model"},
            {"id": "o3-mini", "object": "model"},
            {"id": "claude-3-5-sonnet", "object": "model"},
        ],
    }

    with respx.mock(base_url="https://api.mock-provider.com") as respx_mock:
        respx_mock.get("/v1/models").mock(
            return_value=httpx.Response(200, json=fake_models_response)
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            resp = await client.post(
                "/api/fetch-remote-models",
                json={
                    "base_url": "https://api.mock-provider.com/v1",
                    "api_key": "test-fetch-mock-key",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["count"] == 3
            assert data["models"] == ["gpt-4o", "o3-mini", "claude-3-5-sonnet"]


@pytest.mark.asyncio
async def test_fetch_remote_models_from_pasted_chat_endpoint(test_cfg: AttestConfig):
    """'.../api/v1/chat/completions' + '/v1/models' used to hit a 404 path."""
    import respx

    app = create_app(test_cfg)
    with respx.mock(base_url="https://openrouter.ai") as respx_mock:
        route = respx_mock.get("/api/v1/models").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": "openai/gpt-5.6-luna"}]}
            )
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            resp = await client.post(
                "/api/fetch-remote-models",
                json={
                    "base_url": "https://openrouter.ai/api/v1/chat/completions",
                    "models_path": "/v1/models",
                    "api_key": "test-fetch-mock-key",
                },
            )
        assert route.called
        assert resp.json()["models"] == ["openai/gpt-5.6-luna"]


@pytest.mark.asyncio
async def test_dispute_pack_route(test_cfg: AttestConfig):
    app = create_app(test_cfg)
    db = Database(test_cfg.database)

    target = Target(
        id="disp-tgt", base_url="https://api.dispute.io", model="deepseek-r1"
    )
    db.save_target(target)
    prompts = db.sync_prompts(
        [
            PromptItem(
                id=None,
                category="math",
                text="2+2",
                params={},
                samples_count=1,
                battery_version="v1",
            )
        ],
        "v1",
    )
    b_id = db.create_baseline(target.id, "v1")
    db.save_baseline_samples(
        b_id, [RawSample(prompt_id=prompts[0].id, raw_text="4", latency_ms=100)]
    )
    r_id = db.create_run(target.id, b_id, "v1")
    db.save_run_samples(
        r_id, [RawSample(prompt_id=prompts[0].id, raw_text="4", latency_ms=100)]
    )
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r_id,
                method="exact",
                scope="global",
                value=1.0,
                threshold=1.0,
                verdict=Verdict.PASS,
            )
        ]
    )
    db.finish_run(r_id, "completed")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        # JSON endpoint
        resp_json = await client.get(f"/api/runs/{r_id}/dispute-pack")
        assert resp_json.status_code == 200
        pack = resp_json.json()
        assert pack["run_id"] == r_id
        assert pack["overall_verdict"] == "PASS"
        assert "dispute_letter_markdown" in pack

        # Markdown endpoint (defaults to Russian from test_cfg)
        resp_md = await client.get(f"/api/runs/{r_id}/dispute-pack?format=md")
        assert resp_md.status_code == 200
        assert "Претензионный пакет доказательств верификации Attest" in resp_md.text

        # Markdown endpoint (explicit English)
        resp_md_en = await client.get(
            f"/api/runs/{r_id}/dispute-pack?format=md&locale=en"
        )
        assert resp_md_en.status_code == 200
        assert "Attest Verification Dispute Evidence Pack" in resp_md_en.text


@pytest.mark.asyncio
async def test_api_locales_and_locale_resolution(test_cfg: AttestConfig):
    app = create_app(test_cfg)
    db = Database(test_cfg.database)
    t_id = "test-gpt-5-6-luna"
    db.sync_prompts(
        [
            PromptItem(
                id=None,
                category="general",
                text="test query",
                params={},
                samples_count=1,
                battery_version="v1",
            )
        ],
        "v1",
    )
    b_id = db.create_baseline(t_id, "v1")
    r_id = db.create_run(t_id, b_id, "v1")
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r_id,
                method="quick_model",
                scope="global",
                value=0.0,
                threshold=1.0,
                verdict=Verdict.FAIL,
                details={"claimed": "gpt-4o", "returned": "gpt-3.5"},
            )
        ]
    )
    db.finish_run(r_id, "completed")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        # 1. Fetch RU locale dictionary
        resp_ru = await client.get("/api/locales/ru")
        assert resp_ru.status_code == 200
        ru_data = resp_ru.json()
        assert "title" in ru_data
        assert "methods" in ru_data
        assert ru_data["targets"] == "Таргеты"

        # 2. Fetch EN locale dictionary
        resp_en = await client.get("/api/locales/en")
        assert resp_en.status_code == 200
        en_data = resp_en.json()
        assert "title" in en_data
        assert en_data["targets"] == "Targets"

        # 3. Test run details with locale=en
        resp_run_en = await client.get(f"/api/runs/{r_id}?locale=en")
        assert resp_run_en.status_code == 200
        data_en = resp_run_en.json()
        assert "FAILED" in data_en["run"]["summary_message"]
        assert len(data_en["failure_diagnostics"]) == 1
        assert "model mismatch" in data_en["failure_diagnostics"][0]["message"]

        # 4. Test run details with locale=ru
        resp_run_ru = await client.get(f"/api/runs/{r_id}?locale=ru")
        assert resp_run_ru.status_code == 200
        data_ru = resp_run_ru.json()
        assert "ПРОВАЛЕНО" in data_ru["run"]["summary_message"]
        assert "подмена модели" in data_ru["failure_diagnostics"][0]["message"]

        # 5. Export HTML with locale=en
        resp_html_en = await client.get(
            f"/api/runs/{r_id}/export?format=html&locale=en"
        )
        assert resp_html_en.status_code == 200
        assert "Root Cause Failure Diagnostics" in resp_html_en.text
        assert "model mismatch" in resp_html_en.text

        # 6. Export HTML with locale=ru
        resp_html_ru = await client.get(
            f"/api/runs/{r_id}/export?format=html&locale=ru"
        )
        assert resp_html_ru.status_code == 200
        assert "Детализированная диагностика сбоев" in resp_html_ru.text
        assert "подмена модели" in resp_html_ru.text


def test_resolve_locale_helper():
    # Explicit parameter overrides everything
    assert resolve_locale("en", None, "ru") == "en"
    assert resolve_locale("ru", None, "en") == "ru"

    # Fallback to default when nothing provided
    assert resolve_locale(None, None, "en") == "en"
    assert resolve_locale(None, None, "ru") == "ru"


@pytest.mark.asyncio
async def test_api_curated_models(test_cfg: AttestConfig):
    app = create_app(test_cfg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        resp = await client.get("/api/curated-models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "OpenAI" in data
        assert "Anthropic" in data
        assert "DeepSeek" in data
        assert "Google Gemini" in data

        all_model_ids = [m["id"] for model_list in data.values() for m in model_list]
        assert "gpt-6-astra" in all_model_ids
        assert "gpt-5.6-luna" in all_model_ids
        assert "claude-fable-5-1" in all_model_ids
        assert "deepseek-flash" in all_model_ids


@pytest.mark.asyncio
async def test_api_stats_populated(test_cfg: AttestConfig):
    db = Database(test_cfg.database)
    # 1. Create a baseline
    b_id = db.create_baseline(
        target_id="test-gpt-5-6-luna",
        battery_version="v1",
        notes="Official test baseline",
    )

    # 2. Create first run (PASS)
    r1_id = db.create_run(
        target_id="test-gpt-5-6-luna",
        baseline_id=b_id,
        battery_version="v1",
    )
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r1_id,
                method="quick_model",
                scope="model",
                value=0.0,
                threshold=0.15,
                verdict=Verdict.PASS,
            )
        ]
    )
    db.finish_run(r1_id)

    # 3. Create second run (FAIL)
    r2_id = db.create_run(
        target_id="test-gpt-5-6-luna",
        baseline_id=b_id,
        battery_version="v1",
    )
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r2_id,
                method="quick_model",
                scope="model",
                value=1.0,
                threshold=0.15,
                verdict=Verdict.FAIL,
            )
        ]
    )
    db.finish_run(r2_id)

    app = create_app(test_cfg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total_targets"] == 1
        assert stats["active_baselines"] == 1
        assert stats["total_audits"] == 2
        assert stats["passes"] == 1
        assert stats["failures"] == 1
        assert stats["warnings"] == 0


@pytest.mark.asyncio
async def test_cors_origins_header(tmp_path: Path):
    cfg = AttestConfig(
        database=str(tmp_path / "cors_test.db"),
        cors_origins=["https://lab.example.org"],
    )
    app = create_app(cfg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        resp = await client.options(
            "/api/targets",
            headers={
                "Origin": "https://lab.example.org",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert (
            resp.headers.get("access-control-allow-origin") == "https://lab.example.org"
        )


def test_env_config_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from attest.config import load_config

    monkeypatch.setenv("ATTEST_DB_PATH", str(tmp_path / "env_override.db"))
    monkeypatch.setenv("ATTEST_CORS_ORIGINS", "https://app.test,https://hub.test")

    cfg = load_config()
    assert cfg.database == str(tmp_path / "env_override.db")
    assert cfg.cors_origins == ["https://app.test", "https://hub.test"]


@pytest.mark.asyncio
async def test_foreign_origin_and_host_are_blocked(test_cfg: AttestConfig):
    app = create_app(test_cfg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:5555"
    ) as client:
        ok = await client.get("/api/targets")
        assert ok.status_code == 200

        same = await client.get(
            "/api/targets", headers={"Origin": "http://localhost:5555"}
        )
        assert same.status_code == 200

        for origin in ("https://evil.example", "http://localhost:3000", "null"):
            resp = await client.post(
                "/api/audit-all", headers={"Origin": origin}
            )
            assert resp.status_code == 403, origin
            assert "access-control-allow-origin" not in resp.headers

    # DNS rebinding: attacker domain resolving to 127.0.0.1
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://attacker.example"
    ) as client:
        resp = await client.get("/api/targets")
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_fetch_remote_models_does_not_leak_stored_keys(
    test_cfg: AttestConfig, monkeypatch: pytest.MonkeyPatch
):
    from attest.security import encrypt_api_key

    db = Database(test_cfg.database)
    db.save_target(
        Target(
            id="official-openai",
            base_url="https://api.openai.com",
            model="gpt-4o",
            encrypted_key=encrypt_api_key("test-stored-openai-secret"),
        )
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-env-openai-secret")

    sent: list[tuple[str, dict]] = []

    async def fake_get(self, url, headers=None, **kwargs):
        sent.append((str(url), dict(headers or {})))
        return httpx.Response(200, json={"data": []}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    app = create_app(test_cfg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        for body in (
            {"base_url": "https://api.openai.com.evil.example", "provider_id": "openai"},
            {"base_url": "https://evil.example/v1", "provider_id": "-"},
            {"base_url": "https://evil.example/v1", "target_id": "official-openai"},
        ):
            resp = await client.post("/api/fetch-remote-models", json=body)
            assert resp.status_code == 200

        resp = await client.post(
            "/api/fetch-remote-models",
            json={
                "base_url": "https://api.openai.com/v1",
                "models_path": "https://evil.example/models",
            },
        )
        assert resp.json()["ok"] is False

    assert sent, "expected outbound model-list requests"
    for url, headers in sent:
        assert "evil.example" in url
        assert "Authorization" not in headers, url


@pytest.mark.asyncio
async def test_studio_never_carries_a_key_to_another_host(tmp_path):
    """A candidate target re-pointed from a reseller to OpenRouter must not send the
    reseller's key there, and the OpenRouter card must not show the reseller's key."""
    import respx

    from attest.security import encrypt_api_key

    db_file = tmp_path / "keys.db"
    db = Database(db_file)
    synced = db.sync_prompts(
        [
            PromptItem(
                id=None,
                category="one_token",
                text="Pick digit",
                params={"max_tokens": 1},
                samples_count=1,
                battery_version="v1",
            )
        ],
        "v1",
    )
    db.save_target(
        Target(id="official", base_url="https://api.openai.com/v1", model="gpt-5.6-luna")
    )
    b_id = db.create_baseline("official", "v1")
    db.save_baseline_samples(
        b_id, [RawSample(prompt_id=synced[0].id, raw_text="7", latency_ms=10)]
    )
    reseller_key = "test-reseller-key-0000000000000000000000049"
    openrouter_key = "test-openrouter-key-000000000000000000000000051"
    # Named after the dropdown provider, but pointing at the reseller
    db.save_target(
        Target(
            id="openrouter-gpt-5-6-luna",
            base_url="https://reseller.example.com/v1",
            model="gpt-5.6-luna",
            encrypted_key=encrypt_api_key(reseller_key),
        )
    )
    db.save_target(
        Target(
            id="ref-openai-gpt-5-6-luna",
            base_url="https://openrouter.ai/api/v1",
            model="openai/gpt-5.6-luna",
            encrypted_key=encrypt_api_key(openrouter_key),
        )
    )

    app = create_app(AttestConfig(database=str(db_file)))
    with respx.mock(assert_all_called=False) as respx_mock:
        route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(401, json={"error": {"message": "stop"}})
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            providers = (await client.get("/api/providers")).json()
            openrouter = next(p for p in providers if p["id"] == "openrouter")
            assert openrouter["env_key"]["preview"].endswith("051")

            resp = await client.post(
                "/api/studio/verify",
                json={
                    "reference_model": "gpt-5.6-luna",
                    "candidate_provider": "openrouter",
                    "candidate_url": "https://openrouter.ai/api/v1",
                    "candidate_model_call": "gpt-5.6-luna",
                    "battery": "quick",
                },
            )
            assert resp.status_code == 200

    sent = {c.request.headers.get("authorization") for c in route.calls}
    assert f"Bearer {reseller_key}" not in sent
    assert sent <= {f"Bearer {openrouter_key}"}
