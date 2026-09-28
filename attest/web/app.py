"""
FastAPI Backend Server for Attest Web Dashboard.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("attest.web")

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from attest import __version__
from attest.battery.loader import (
    estimate_battery_cost,
    load_battery,
    resolve_battery_path,
)
from attest.config import AttestConfig, load_config
from attest.db import Database
from attest.i18n import (
    build_pipeline_summary_message,
    format_failure_diagnostics,
    normalize_locale,
)
from attest.models import Baseline, RawSample, Target, Verdict
from attest.providers import (
    canonicalize_model_name,
    get_curated_models_by_vendor,
    list_providers,
)
from attest.reporting import build_html_report, generate_dispute_pack
from attest.security import (
    detect_env_key_for_provider,
    encrypt_api_key,
    mask_key,
    resolve_api_key,
    url_hostname,
)
from attest.service import AttestService

STATIC_DIR = Path(__file__).parent / "static"

# In-memory background task registry
TASKS: dict[str, dict[str, Any]] = {}


def resolve_locale(
    locale_param: str | None = None,
    request: Request | None = None,
    default_locale: str = "ru",
) -> str:
    """
    Resolves request locale with precedence:
    1. Explicit parameter (?locale=en)
    2. Accept-Language request header
    3. Application/system configured default locale
    """
    if locale_param:
        return normalize_locale(locale_param)

    if request:
        accept = request.headers.get("accept-language", "")
        if accept:
            first_lang = accept.split(",")[0].split(";")[0].strip().lower()
            if first_lang.startswith("en"):
                return "en"
            if first_lang.startswith("ru"):
                return "ru"

    return normalize_locale(default_locale)


def _cleanup_tasks(max_age_seconds: float = 3600.0, max_items: int = 200) -> None:
    """Evicts completed/failed tasks older than max_age_seconds, keeping TASKS bounded."""
    now = time.time()
    to_remove = [
        tid
        for tid, t in list(TASKS.items())
        if t.get("status") in ("completed", "failed")
        and (now - t.get("started_at", 0)) > max_age_seconds
    ]
    for tid in to_remove:
        TASKS.pop(tid, None)

    if len(TASKS) > max_items:
        non_running = sorted(
            [
                (tid, t.get("started_at", 0))
                for tid, t in TASKS.items()
                if t.get("status") != "running"
            ],
            key=lambda x: x[1],
        )
        for tid, _ in non_running[: len(TASKS) - max_items]:
            TASKS.pop(tid, None)


def _register_task(
    task_id: str,
    target_id: str,
    task_type: str,
    db: Database | None = None,
) -> dict[str, Any]:
    """Registers a task in TASKS registry and database, automatically evicting expired tasks."""
    _cleanup_tasks()
    t_info = {
        "task_id": task_id,
        "target_id": target_id,
        "type": task_type,
        "status": "running",
        "started_at": time.time(),
        "total": 0,
        "completed": 0,
        "result": None,
        "error": None,
    }
    TASKS[task_id] = t_info
    if db is not None:
        try:
            db.cleanup_old_tasks(max_age_seconds=86400.0)
            db.create_task(task_id=task_id, target_id=target_id, task_type=task_type)
        except Exception as e:  # noqa: BLE001
            logger.debug("Failed to persist task %s to database: %s", task_id, e)
    return t_info


class TargetCreateRequest(BaseModel):
    id: str = Field(..., description="Unique target identifier")
    base_url: str = Field(..., description="OpenAI-compatible base URL")
    model: str = Field(..., description="Claimed model name")
    key: str | None = Field(default=None, description="API key to encrypt")
    description: str | None = Field(default=None, description="Target description")
    wire_model: str | None = Field(
        default=None, description="Optional wire model name for API calls"
    )


class ScheduleCreateRequest(BaseModel):
    target_id: str = Field(..., description="Target identifier to monitor")
    interval_hours: int = Field(
        default=24, ge=1, le=720, description="Periodic frequency in hours"
    )
    battery: str = Field(
        default="quick",
        description="Battery type: 'quick', 'anti_spoof', 'reasoning', or 'v1'",
    )
    enabled: bool = Field(default=True, description="Enable or disable monitoring")


class StudioVerifyRequest(BaseModel):
    reference_model: str = Field(
        ..., description="Canonical model to audit against, e.g. gpt-5.6-luna"
    )
    candidate_provider: str = Field(
        default="custom", description="Known provider ID, e.g. openrouter, deepseek, or 'custom'"
    )
    candidate_url: str = Field(..., description="Candidate API base URL")
    candidate_model_call: str = Field(
        ..., description="Model string sent to candidate API"
    )
    candidate_key: str | None = Field(default=None, description="API key")
    candidate_target_id: str | None = Field(
        default=None, description="Optional target ID slug"
    )
    save_target: bool = Field(
        default=True, description="Whether to persist candidate target"
    )
    battery: str = Field(
        default="quick",
        description="Battery type: 'quick', 'anti_spoof', 'reasoning', or 'v1'",
    )
    mmd: bool = Field(default=False, description="Run Level 3 MMD test")
    baseline_id: int | None = Field(
        default=None,
        description="Optional specific baseline revision ID to audit against",
    )


class FetchRemoteModelsRequest(BaseModel):
    base_url: str = Field(..., description="Provider base URL")
    api_key: str | None = Field(default=None, description="API Key")
    provider_id: str | None = Field(default=None, description="Known provider ID")
    target_id: str | None = Field(
        default=None, description="Existing target ID to resolve key from"
    )
    models_path: str | None = Field(
        default=None,
        description="Optional custom path to fetch models, e.g. /v1/models or /models",
    )


def create_app(config: AttestConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    db = Database(cfg.database)

    async def _scheduler_loop():
        # Delay first check after startup
        await asyncio.sleep(5)
        while True:
            try:
                due_schedules = await asyncio.to_thread(db.get_due_schedules)
                for sched in due_schedules:
                    target = await asyncio.to_thread(db.get_target, sched.target_id)
                    if not target:
                        continue
                    baseline, _ = await asyncio.to_thread(
                        db.resolve_target_baseline, target.id
                    )
                    if not baseline:
                        continue

                    # Update tick schedule
                    await asyncio.to_thread(
                        db.record_schedule_tick, sched.id, sched.interval_hours
                    )

                    task_id = f"sched-{str(uuid.uuid4())[:6]}"
                    _register_task(task_id, target.id, "audit", db=db)
                    battery_path = str(
                        resolve_battery_path(sched.battery, default=cfg.battery)
                    )

                    def _on_sched_done(t: asyncio.Task):
                        if not t.cancelled() and t.exception():
                            logger.error(
                                "Scheduled audit worker error: %s", t.exception()
                            )

                    stask = asyncio.create_task(
                        _run_audit_worker(
                            task_id=task_id,
                            target=target,
                            mmd=False,
                            against=None,
                            battery_path=battery_path,
                            trigger="scheduled",
                        )
                    )
                    stask.add_done_callback(_on_sched_done)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Periodic scheduler error: %s", exc)
            await asyncio.sleep(30)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Auto-cleanup stale running runs on startup
        await asyncio.to_thread(db.cleanup_stale_runs)
        sched_task = asyncio.create_task(_scheduler_loop())
        try:
            yield
        finally:
            sched_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sched_task

    app = FastAPI(
        title="Attest Web Dashboard",
        description="Behavioral Verification & Anti-Spoofing Detector for LLM APIs",
        version=__version__,
        lifespan=lifespan,
    )

    cors_origins = list(cfg.cors_origins)
    if cors_origins:
        allow_all = "*" in cors_origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=not allow_all,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # The API has no user auth and can spend API credits and use stored keys, so it must
    # only answer the local dashboard: reject foreign Host headers (DNS rebinding) and
    # cross-origin browser requests (CSRF / drive-by from any open web page).
    allowed_hosts = {h.strip().lower().strip("[]") for h in cfg.allowed_hosts}
    any_host = "*" in allowed_hosts
    any_origin = "*" in cors_origins
    extra_origins = {o.rstrip("/") for o in cors_origins}

    @app.middleware("http")
    async def _local_access_guard(request: Request, call_next):
        host = url_hostname(request.headers.get("host", ""))
        if not any_host and host not in allowed_hosts:
            return JSONResponse(
                status_code=403, content={"detail": f"Host '{host}' is not allowed"}
            )
        origin = request.headers.get("origin")
        if origin and not any_origin:
            same_origin = (
                urlparse(origin).netloc.lower()
                == request.headers.get("host", "").lower()
            )
            if not same_origin and origin.rstrip("/") not in extra_origins:
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"Cross-origin request from '{origin}' blocked"},
                )
        return await call_next(request)

    service = AttestService(db=db, config=cfg)
    try:
        service.sync_targets_from_config()
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to auto-sync targets from config file: %s", e)

    # --- Background Task Workers ---
    async def _run_baseline_worker(
        task_id: str, target: Target, battery_path: str | None = None
    ):
        if not target.encrypted_key:
            target.encrypted_key = db.find_encrypted_key_for_url(target.base_url)
        task_info = TASKS[task_id]
        try:
            battery_file = battery_path or cfg.battery
            est = await asyncio.to_thread(service.estimate_battery, battery_file)
            task_info["total"] = est["total_requests"]
            db.update_task_progress(task_id, completed=0, total=est["total_requests"])

            completed_samples = 0

            def _on_done(s: RawSample):
                nonlocal completed_samples
                completed_samples += 1
                task_info["completed"] = completed_samples
                db.update_task_progress(task_id, completed=completed_samples)

            res = await service.capture_baseline_async(
                target=target,
                battery_path=battery_file,
                note="Captured via Web Dashboard",
                on_sample_done=_on_done,
            )

            res_dict = {
                "baseline_id": res.baseline_id,
                "samples_count": len(res.samples),
                "captured_at": time.time(),
            }
            task_info["status"] = "completed"
            task_info["result"] = res_dict
            db.complete_task(task_id, result=res_dict)
        except Exception as e:  # noqa: BLE001
            task_info["status"] = "failed"
            task_info["error"] = str(e)
            db.fail_task(task_id, error=str(e))

    async def _run_audit_worker(
        task_id: str,
        target: Target,
        mmd: bool = False,
        against: str | None = None,
        battery_path: str | None = None,
        trigger: str = "web_ui",
    ):
        if not target.encrypted_key:
            target.encrypted_key = db.find_encrypted_key_for_url(target.base_url)
        task_info = TASKS[task_id]
        try:
            battery_file = battery_path or cfg.battery
            est = await asyncio.to_thread(service.estimate_battery, battery_file)
            task_info["total"] = est["total_requests"]
            db.update_task_progress(task_id, completed=0, total=est["total_requests"])

            completed_samples = 0

            def _on_done(s: RawSample):
                nonlocal completed_samples
                completed_samples += 1
                task_info["completed"] = completed_samples
                db.update_task_progress(task_id, completed=completed_samples)

            res = await service.audit_target_async(
                target=target,
                battery_path=battery_file,
                mmd=mmd,
                against=against,
                trigger=trigger,
                on_sample_done=_on_done,
            )

            res_dict = {
                "run_id": res.run.id,
                "verdict": res.overall_verdict.value,
                "summary": res.summary_message,
                "duration_s": round(res.duration_s, 2),
                "total_tokens": res.total_tokens,
                "est_cost_usd": round(res.est_cost_usd, 4),
            }
            task_info["status"] = "completed"
            task_info["result"] = res_dict
            db.complete_task(task_id, result=res_dict)
        except Exception as e:  # noqa: BLE001
            task_info["status"] = "failed"
            task_info["error"] = str(e)
            db.fail_task(task_id, error=str(e))

    # --- REST API Endpoints ---
    @app.get("/api/targets")
    def list_targets():
        targets = db.list_targets()
        out = []
        for t in targets:
            enc_key = t.encrypted_key or db.find_encrypted_key_for_url(t.base_url)
            key, source = resolve_api_key(t.id, enc_key, base_url=t.base_url)
            if not t.encrypted_key and enc_key and key:
                source = "inherited_db"
            baseline, source_desc = db.resolve_target_baseline(t.id)
            latest_run = db.get_latest_run(t.id)

            latest_run_dict = None
            if latest_run and latest_run.id:
                scores = db.get_scores(latest_run.id)
                overall = Verdict.aggregate(scores)
                latest_run_dict = {
                    "id": latest_run.id,
                    "started_at": latest_run.started_at,
                    "finished_at": latest_run.finished_at,
                    "status": latest_run.status,
                    "verdict": overall.value,
                }

            out.append(
                {
                    "id": t.id,
                    "base_url": t.base_url,
                    "model": t.model,
                    "wire_model": t.wire_model,
                    "description": t.description,
                    "key_preview": mask_key(key),
                    "key_source": source,
                    "has_key": bool(key),
                    "active_baseline": (
                        {
                            "id": baseline.id,
                            "captured_at": baseline.captured_at,
                            "battery_version": baseline.battery_version,
                            "notes": baseline.notes,
                            "integrity_hash": baseline.integrity_hash,
                            "source_target_id": baseline.target_id,
                            "is_inherited": baseline.target_id != t.id,
                            "source_desc": source_desc,
                        }
                        if baseline
                        else None
                    ),
                    "latest_run": latest_run_dict,
                }
            )
        return out

    @app.post("/api/targets")
    def create_target(req: TargetCreateRequest):
        clean_id = req.id.strip().lower()
        enc_key = encrypt_api_key(req.key.strip()) if req.key else None
        if not enc_key:
            enc_key = db.find_encrypted_key_for_url(req.base_url.strip())
        target = Target(
            id=clean_id,
            base_url=req.base_url.strip(),
            model=req.model.strip(),
            wire_model=req.wire_model.strip() if req.wire_model else None,
            encrypted_key=enc_key,
            description=req.description,
        )
        db.save_target(target)
        return {"ok": True, "id": clean_id}

    @app.delete("/api/targets/{target_id}")
    def delete_target(target_id: str):
        if not db.delete_target(target_id):
            raise HTTPException(status_code=404, detail="Target not found")
        return {"ok": True}

    @app.get("/api/targets/{target_id}/estimate")
    def get_estimate(target_id: str, battery: str | None = None):
        target = db.get_target(target_id)
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")
        battery_file = str(resolve_battery_path(battery, default=cfg.battery))
        version, prompts = load_battery(battery_file)
        est = estimate_battery_cost(prompts)
        est["battery_version"] = version
        return est

    @app.get("/api/baselines")
    def get_baselines_catalog(target_id: str | None = None, model: str | None = None):
        """Returns all historical baselines with target info, sample count, and status."""
        return db.list_all_baselines(target_id=target_id, model=model)

    @app.get("/api/baselines/{baseline_id}/verify-integrity")
    def verify_baseline_integrity_route(baseline_id: int):
        valid, stored, computed = db.verify_baseline_integrity(baseline_id)
        return {
            "baseline_id": baseline_id,
            "valid": valid,
            "stored_hash": stored,
            "computed_hash": computed,
        }

    @app.get("/api/providers")
    def get_providers_catalog():
        """Returns known provider registry with detected env or db key status."""
        out = []
        db_targets = db.list_targets()
        for p in list_providers():
            p_data = p.to_dict()
            has_key, preview, source = detect_env_key_for_provider(p.id)
            if not has_key:
                # Check if any target in DB is configured with this provider
                # Match on the host only: a target named 'openrouter-...' may point
                # at a reseller, and its key is not an OpenRouter key
                p_host = url_hostname(p.base_url)
                for t in db_targets:
                    if p_host and url_hostname(t.base_url) == p_host:
                        k, _ = resolve_api_key(
                            t.id,
                            stored_encrypted_key=t.encrypted_key,
                            base_url=t.base_url,
                        )
                        if k:
                            has_key = True
                            preview = mask_key(k)
                            source = f"db ({t.id})"
                            break
            p_data["env_key"] = {
                "has_key": has_key,
                "preview": preview,
                "source": source,
            }
            out.append(p_data)

        # Append user-saved custom providers from DB
        custom_providers = db.get_custom_providers()
        out.extend(custom_providers)

        return out

    class CustomProviderRequest(BaseModel):
        name: str = Field(..., description="Display name of the provider")
        base_url: str = Field(..., description="Base URL of the OpenAI-compatible endpoint")
        api_key: str | None = Field(default=None, description="API key to store encrypted")
        description: str | None = Field(default=None, description="Optional description")
        model_prefix: str | None = Field(default=None, description="Optional model prefix, e.g. 'openai/'")

    @app.post("/api/providers/custom")
    def save_custom_provider(req: CustomProviderRequest):
        """Save a user-defined provider to the database for reuse."""
        import re as _re
        provider_id = "custom_" + _re.sub(r"[^a-z0-9]+", "_", req.name.lower()).strip("_")
        encrypted_key = encrypt_api_key(req.api_key) if req.api_key else None
        db.save_custom_provider(
            provider_id=provider_id,
            name=req.name,
            base_url=req.base_url,
            description=req.description or "",
            model_prefix=req.model_prefix or "",
            encrypted_key=encrypted_key,
        )
        return {
            "id": provider_id,
            "name": req.name,
            "base_url": req.base_url,
            "description": req.description or "",
            "model_prefix": req.model_prefix or "",
            "is_trusted_reference": False,
            "popular_models": [],
            "docs_url": "",
            "env_key": {"has_key": bool(req.api_key), "preview": mask_key(req.api_key) if req.api_key else "", "source": "db"},
        }

    @app.delete("/api/providers/custom/{provider_id}")
    def delete_custom_provider(provider_id: str):
        """Delete a user-defined custom provider from the database."""
        db.delete_custom_provider(provider_id)
        return {"ok": True}

    @app.get("/api/curated-models")
    def get_curated_models_route():
        """Returns official 2026 curated models grouped by vendor for studio dropdowns, plus active target models from DB."""
        curated = get_curated_models_by_vendor()
        db_targets = db.list_targets()
        if db_targets:
            db_models = []
            seen = set()
            for cat_models in curated.values():
                for m in cat_models:
                    seen.add(m["id"])
            for t in db_targets:
                if t.model and t.model not in seen:
                    seen.add(t.model)
                    db_models.append(
                        {"id": t.model, "name": f"{t.model} [Target: {t.id}]"}
                    )
            if db_models:
                curated["Configured Endpoints (DB)"] = db_models
        return curated

    @app.post("/api/fetch-remote-models")
    async def fetch_remote_models_route(req: FetchRemoteModelsRequest):
        """
        Queries GET {base_url}/models with the resolved API key,
        returning available model IDs dynamically to eliminate manual typing.
        """
        clean_base = req.base_url.rstrip("/")
        # A pasted chat endpoint ('.../v1/chat/completions') is not the API root
        clean_base = clean_base.removesuffix("/chat/completions")
        if req.models_path and req.models_path.strip():
            custom_path = req.models_path.strip()
            if custom_path.startswith(("http://", "https://")):
                url = custom_path
            elif custom_path.startswith("/"):
                if clean_base.endswith("/v1") and custom_path.startswith("/v1/"):
                    url = f"{clean_base[:-3]}{custom_path}"
                else:
                    url = f"{clean_base}{custom_path}"
            else:
                url = f"{clean_base}/{custom_path}"
        elif clean_base.endswith("/chat/completions"):
            url = clean_base.replace("/chat/completions", "/models")
        elif clean_base.endswith("/models"):
            url = clean_base
        else:
            url = f"{clean_base}/models"

        # Never send a key to a host other than the one the user entered
        base_host = url_hostname(clean_base)
        if url_hostname(url) != base_host:
            return {
                "ok": False,
                "error": "models_path must point to the same host as base_url.",
                "models": [],
                "count": 0,
            }

        key = (req.api_key or "").strip()
        if not key and req.target_id:
            t = db.get_target(req.target_id)
            if t and url_hostname(t.base_url) == base_host:
                key, _ = resolve_api_key(t.id, t.encrypted_key, base_url=t.base_url)
        if not key:
            # Stored keys are only reused for targets on exactly the same host
            for t in db.list_targets():
                if t.encrypted_key and url_hostname(t.base_url) == base_host:
                    key, _ = resolve_api_key(
                        t.id, t.encrypted_key, base_url=t.base_url
                    )
                    if key:
                        break
        if not key:
            probe_id = f"{req.provider_id or 'remote'}-probe"
            key, _ = resolve_api_key(probe_id, base_url=clean_base)

        # No identifying User-Agent/Referer: a provider could otherwise flag this key
        # as belonging to an auditor and treat its later audit traffic specially.
        headers: dict[str, str] = {}
        if key:
            headers["Authorization"] = f"Bearer {key}"

        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404 and "/v1" not in url:
                    fallback_url = f"{clean_base}/v1/models"
                    try:
                        fb_resp = await client.get(fallback_url, headers=headers)
                        if fb_resp.status_code != 404:
                            resp = fb_resp
                            clean_base = f"{clean_base}/v1"
                    except (httpx.RequestError, OSError):
                        pass
                if resp.status_code == 401:
                    return {
                        "ok": False,
                        "error": "Authentication failed (HTTP 401). Invalid or missing API key.",
                        "models": [],
                        "count": 0,
                    }
                if resp.status_code == 403:
                    return {
                        "ok": False,
                        "error": f"Access forbidden (HTTP 403): {resp.text[:200]}",
                        "models": [],
                        "count": 0,
                    }
                resp.raise_for_status()
                data = resp.json()

            raw_models = []
            if isinstance(data, list):
                raw_models = data
            elif isinstance(data, dict):
                raw_models = data.get("data") or data.get("models") or []

            model_ids = []
            for item in raw_models:
                if isinstance(item, str) and item.strip():
                    model_ids.append(item.strip())
                elif isinstance(item, dict) and "id" in item:
                    mid = str(item["id"]).strip()
                    if mid:
                        model_ids.append(mid)

            # Deduplicate preserving order
            seen = set()
            unique_models = []
            for m in model_ids:
                if m not in seen:
                    seen.add(m)
                    unique_models.append(m)

            return {
                "ok": True,
                "models": unique_models,
                "count": len(unique_models),
                "base_url": clean_base,
            }
        except httpx.HTTPStatusError as e:
            return {
                "ok": False,
                "error": f"Provider returned HTTP {e.response.status_code}: {e.response.text[:200]}",
                "models": [],
                "count": 0,
            }
        except (httpx.RequestError, OSError) as e:
            return {
                "ok": False,
                "error": f"Failed to connect to {clean_base}: {e}",
                "models": [],
                "count": 0,
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"Error querying models: {e}",
                "models": [],
                "count": 0,
            }

    @app.post("/api/studio/verify")
    def trigger_studio_verification(
        req: StudioVerifyRequest,
        background_tasks: BackgroundTasks,
    ):
        """
        High-level Verification Studio endpoint:
        Takes reference model & candidate provider details, resolves or registers candidate,
        verifies against reference baseline, and returns live task info.
        """
        target_id = req.candidate_target_id
        if not target_id:
            safe_prov = re.sub(r"[^A-Za-z0-9_-]", "-", req.candidate_provider)
            safe_model = re.sub(r"[^A-Za-z0-9_-]", "-", req.candidate_model_call)
            target_id = f"{safe_prov}-{safe_model}"

        canonical_model = canonicalize_model_name(
            req.reference_model or req.candidate_model_call
        )
        target = db.get_target(target_id)
        if target:
            if req.candidate_key:
                target.encrypted_key = encrypt_api_key(req.candidate_key)
            elif not target.encrypted_key or url_hostname(
                target.base_url
            ) != url_hostname(req.candidate_url):
                # The stored key belongs to the old host: never carry it to a new
                # one (an OpenRouter key must not reach a reseller under audit)
                target.encrypted_key = db.find_encrypted_key_for_url(req.candidate_url)
            target.base_url = req.candidate_url
            target.model = canonical_model
            target.wire_model = req.candidate_model_call
            target.description = (
                f"Studio Candidate ({req.candidate_provider}) -> {req.reference_model}"
            )
            if req.save_target:
                db.save_target(target)
        else:
            enc_key = encrypt_api_key(req.candidate_key) if req.candidate_key else None
            if not enc_key:
                enc_key = db.find_encrypted_key_for_url(req.candidate_url)
            target = Target(
                id=target_id,
                base_url=req.candidate_url,
                model=canonical_model,
                wire_model=req.candidate_model_call,
                encrypted_key=enc_key,
                description=f"Studio Candidate ({req.candidate_provider}) -> {req.reference_model}",
            )
            if req.save_target:
                db.save_target(target)

        # Baseline resolution: explicit revision ID if provided, otherwise active baseline
        if req.baseline_id:
            baseline = db.get_baseline(req.baseline_id)
            if not baseline:
                raise HTTPException(
                    status_code=404,
                    detail=f"Baseline revision #{req.baseline_id} not found.",
                )
        else:
            baseline = db.get_active_baseline_for_model(req.reference_model)
            if not baseline:
                baseline = db.get_active_baseline_for_model(req.candidate_model_call)
            if not baseline:
                baseline = db.get_active_baseline(target.id)

        if not baseline:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No active reference baseline found for model '{req.reference_model}'. "
                    f"Please capture an official baseline for '{req.reference_model}' first."
                ),
            )

        battery_path = str(resolve_battery_path(req.battery, default=cfg.battery))

        task_id = str(uuid.uuid4())[:8]
        _register_task(task_id, target.id, "audit", db=db)

        background_tasks.add_task(
            _run_audit_worker,
            task_id,
            target,
            req.mmd,
            str(baseline.id),
            battery_path,
            "studio",
        )
        return {
            "task_id": task_id,
            "target_id": target.id,
            "baseline_id": baseline.id,
            "reference_model": req.reference_model,
        }

    @app.post("/api/targets/{target_id}/baseline")
    def trigger_baseline(
        target_id: str,
        background_tasks: BackgroundTasks,
        battery: str = "v1",
    ):
        target = db.get_target(target_id)
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")

        if not target.encrypted_key:
            inherited = db.find_encrypted_key_for_url(target.base_url)
            if inherited:
                target.encrypted_key = inherited
                db.save_target(target)

        battery_path = str(resolve_battery_path(battery, default=cfg.battery))

        task_id = str(uuid.uuid4())[:8]
        _register_task(task_id, target.id, "baseline", db=db)

        background_tasks.add_task(_run_baseline_worker, task_id, target, battery_path)
        return {"task_id": task_id}

    @app.post("/api/targets/{target_id}/run")
    def trigger_audit(
        target_id: str,
        background_tasks: BackgroundTasks,
        mmd: bool = False,
        against: str | None = None,
        battery: str | None = None,
    ):
        target = db.get_target(target_id)
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")

        if not target.encrypted_key:
            inherited = db.find_encrypted_key_for_url(target.base_url)
            if inherited:
                target.encrypted_key = inherited
                db.save_target(target)

        baseline, source_desc = db.resolve_target_baseline(target.id, against)
        if not baseline:
            raise HTTPException(
                status_code=400,
                detail=f"No active baseline found for target '{target_id}' or model '{target.model}'. Please capture an official baseline first.",
            )

        battery_path = (
            str(resolve_battery_path(battery, default=cfg.battery)) if battery else None
        )

        task_id = str(uuid.uuid4())[:8]
        _register_task(task_id, target.id, "audit", db=db)

        background_tasks.add_task(
            _run_audit_worker, task_id, target, mmd, against, battery_path
        )
        return {
            "task_id": task_id,
            "baseline_id": baseline.id,
            "baseline_source": source_desc,
        }

    @app.post("/api/audit-all")
    def trigger_audit_all(background_tasks: BackgroundTasks, mmd: bool = False):
        targets = db.list_targets()
        triggered = []
        for t in targets:
            b, _ = db.resolve_target_baseline(t.id)
            if b:
                task_id = str(uuid.uuid4())[:8]
                _register_task(task_id, t.id, "audit", db=db)
                background_tasks.add_task(_run_audit_worker, task_id, t, mmd)
                triggered.append({"target_id": t.id, "task_id": task_id})
        return {"triggered": triggered, "count": len(triggered)}

    @app.get("/api/tasks/{task_id}")
    def get_task_status(task_id: str):
        persisted = db.get_task(task_id)
        if persisted:
            return persisted
        if task_id not in TASKS:
            raise HTTPException(status_code=404, detail="Task not found")
        return TASKS[task_id]

    @app.get("/api/targets/{target_id}/runs")
    def get_target_runs(target_id: str, limit: int = 15):
        runs = db.list_runs(target_id=target_id, limit=limit)
        out = []
        for r in runs:
            if not r.id:
                continue
            scores = db.get_scores(r.id)
            overall = Verdict.aggregate(scores)
            out.append(
                {
                    "id": r.id,
                    "target_id": r.target_id,
                    "baseline_id": r.baseline_id,
                    "started_at": r.started_at,
                    "finished_at": r.finished_at,
                    "status": r.status,
                    "verdict": overall.value,
                    "scores_count": len(scores),
                }
            )
        return out

    @app.get("/api/targets/{target_id}/history")
    def get_target_history(target_id: str, limit: int = 30):
        from attest.reporting.history import build_target_history

        if not db.get_target(target_id):
            raise HTTPException(status_code=404, detail="Target not found")
        return build_target_history(db, target_id, limit=max(1, min(limit, 200)))

    @app.get("/api/locales/{lang}")
    def get_locale_bundle(lang: str):
        """
        Returns the localized UI string dictionary for the requested language.
        Reads from static/locales/{lang}.json with fallback to ru.json.
        """
        loc = normalize_locale(lang)
        bundle_path = STATIC_DIR / "locales" / f"{loc}.json"
        if not bundle_path.exists():
            bundle_path = STATIC_DIR / "locales" / "ru.json"
        if not bundle_path.exists():
            raise HTTPException(status_code=404, detail="Locale dictionary not found")
        try:
            with open(bundle_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Failed to load locale: {e}")

    @app.get("/api/runs/{run_id}")
    def get_run_details(
        run_id: int,
        request: Request,
        locale: str | None = Query(
            None, description="Preferred language code ('ru' or 'en')"
        ),
    ):
        loc = resolve_locale(locale, request, default_locale=cfg.locale)
        run_obj = db.get_run(run_id)
        if not run_obj:
            raise HTTPException(status_code=404, detail="Run not found")

        target = db.get_target(run_obj.target_id)
        baseline = db.get_baseline(run_obj.baseline_id)
        b_target = (
            db.get_target(baseline.target_id)
            if baseline and baseline.target_id
            else None
        )
        scores = db.get_scores(run_id)
        samples = db.get_run_samples(run_id)
        baseline_samples = (
            db.get_baseline_samples(run_obj.baseline_id) if run_obj.baseline_id else []
        )

        overall = Verdict.aggregate(scores)

        total_tokens = sum(
            (s.usage.get("total_tokens", 0) if s.usage else (len(s.raw_text) // 3))
            for s in samples
        )

        diagnostics = format_failure_diagnostics(scores, locale=loc)
        summary_msg = build_pipeline_summary_message(overall, diagnostics, locale=loc)

        # Extract assertion failures by prompt_id
        assert_score = next((s for s in scores if s.method == "assertions"), None)
        assert_failures_by_pid: dict[int, list[dict[str, Any]]] = {}
        if assert_score and isinstance(assert_score.details, dict):
            for f in assert_score.details.get("failures", []):
                pid = f.get("prompt_id")
                if pid is not None:
                    assert_failures_by_pid.setdefault(int(pid), []).append(f)

        prompts = db.get_prompts(run_obj.battery_version)
        prompts_map = {p.id: p for p in prompts if p.id is not None}

        # Group samples by prompt_id
        run_by_prompt: dict[int, list[RawSample]] = {}
        for s in samples:
            run_by_prompt.setdefault(s.prompt_id, []).append(s)

        base_by_prompt: dict[int, list[RawSample]] = {}
        for bs in baseline_samples:
            base_by_prompt.setdefault(bs.prompt_id, []).append(bs)

        ordered_pids: list[int] = []
        for p in prompts:
            if p.id is not None and (p.id in run_by_prompt or p.id in base_by_prompt):
                ordered_pids.append(p.id)
        for pid in sorted(set(run_by_prompt.keys()) | set(base_by_prompt.keys())):
            if pid not in ordered_pids:
                ordered_pids.append(pid)

        samples_comparison: list[dict[str, Any]] = []
        for pid in ordered_pids:
            p_def = prompts_map.get(pid)
            c_list = run_by_prompt.get(pid, [])
            b_list = base_by_prompt.get(pid, [])
            c_first = c_list[0] if c_list else None
            b_first = b_list[0] if b_list else None

            c_texts = [s.raw_text for s in c_list]
            b_texts = [s.raw_text for s in b_list]

            c_models = list(
                dict.fromkeys(s.model_returned for s in c_list if s.model_returned)
            )
            b_models = list(
                dict.fromkeys(s.model_returned for s in b_list if s.model_returned)
            )

            c_lat_avg = (
                int(sum(s.latency_ms for s in c_list) / len(c_list)) if c_list else 0
            )
            b_lat_avg = (
                int(sum(s.latency_ms for s in b_list) / len(b_list)) if b_list else 0
            )

            p_failures = assert_failures_by_pid.get(pid, [])

            model_mismatch = False
            expected_model = (
                target.model if target else (b_models[0] if b_models else None)
            )
            if c_models and expected_model and c_models[0] != expected_model:
                model_mismatch = True

            text_exact_match = (c_texts == b_texts) if (c_texts and b_texts) else False
            has_error = len(p_failures) > 0 or model_mismatch

            samples_comparison.append(
                {
                    "prompt_id": pid,
                    "category": p_def.category if p_def else "general",
                    "prompt_text": p_def.text if p_def else f"Prompt #{pid}",
                    "model_mismatch": model_mismatch,
                    "text_exact_match": text_exact_match,
                    "has_discrepancy": has_error
                    or (
                        not text_exact_match
                        and p_def
                        and p_def.category in ("factual", "identity", "math_json")
                    ),
                    "candidate": {
                        "raw_text": c_first.raw_text if c_first else "",
                        "all_texts": c_texts,
                        "wire_model": c_first.model_returned
                        if c_first
                        else (c_models[0] if c_models else None),
                        "latency_ms": c_lat_avg,
                        "fingerprint": c_first.fingerprint if c_first else None,
                        "usage": c_first.usage if c_first else None,
                        "headers": c_first.headers if c_first else {},
                        "logprobs": c_first.logprobs if c_first else None,
                        "reasoning_content": c_first.reasoning_content
                        if c_first
                        else None,
                        "routing_proof": c_first.routing_proof if c_first else None,
                        "samples_count": len(c_list),
                    },
                    "baseline": {
                        "raw_text": b_first.raw_text if b_first else "",
                        "all_texts": b_texts,
                        "wire_model": b_first.model_returned
                        if b_first
                        else (b_models[0] if b_models else None),
                        "latency_ms": b_lat_avg,
                        "fingerprint": b_first.fingerprint if b_first else None,
                        "usage": b_first.usage if b_first else None,
                        "headers": b_first.headers if b_first else {},
                        "logprobs": b_first.logprobs if b_first else None,
                        "reasoning_content": b_first.reasoning_content
                        if b_first
                        else None,
                        "routing_proof": b_first.routing_proof if b_first else None,
                        "samples_count": len(b_list),
                    },
                    "assertion_failures": [
                        {
                            "assertion": f.get("assertion"),
                            "expected": f.get("expected"),
                            "message": f.get("message"),
                        }
                        for f in p_failures
                    ],
                }
            )

        candidate_proof = next(
            (s.routing_proof for s in samples if s.routing_proof), None
        )
        baseline_proof = next(
            (s.routing_proof for s in baseline_samples if s.routing_proof), None
        )

        provenance = {
            "candidate": {
                "target_id": target.id if target else run_obj.target_id,
                "configured_model": target.model if target else "Unknown",
                "base_url": target.base_url if target else "Unknown",
                "description": target.description if target else None,
                "routing_proof": candidate_proof,
            },
            "baseline": {
                "baseline_id": baseline.id if baseline else run_obj.baseline_id,
                "target_id": (
                    baseline.target_id
                    if baseline
                    else (b_target.id if b_target else None)
                ),
                "configured_model": (
                    b_target.model
                    if b_target
                    else (target.model if target else "Unknown")
                ),
                "base_url": (
                    b_target.base_url
                    if b_target
                    else (target.base_url if target else "Unknown")
                ),
                "captured_at": baseline.captured_at if baseline else None,
                "battery_version": baseline.battery_version if baseline else None,
                "notes": baseline.notes if baseline else None,
                "routing_proof": baseline_proof,
            }
            if baseline
            else None,
        }

        return {
            "run": {
                "id": run_obj.id,
                "target_id": run_obj.target_id,
                "baseline_id": run_obj.baseline_id,
                "battery_version": run_obj.battery_version,
                "started_at": run_obj.started_at,
                "finished_at": run_obj.finished_at,
                "status": run_obj.status,
                "verdict": overall.value,
                "summary_message": summary_msg,
                "samples_count": len(samples),
                "total_tokens": total_tokens,
            },
            "target": (
                {
                    "id": target.id,
                    "model": target.model,
                    "wire_model": target.wire_model,
                    "base_url": target.base_url,
                }
                if target
                else None
            ),
            "baseline": (
                {
                    "id": baseline.id,
                    "captured_at": baseline.captured_at,
                    "battery_version": baseline.battery_version,
                    # Which endpoint and model the reference answers came from
                    "target_id": baseline.target_id,
                    "model": (b_target.wire_model or b_target.model) if b_target else None,
                    "base_url": b_target.base_url if b_target else None,
                }
                if baseline
                else None
            ),
            "scores": [
                {
                    "method": s.method,
                    "scope": s.scope,
                    "value": s.value,
                    "threshold": s.threshold,
                    "verdict": s.verdict.value,
                    "details": s.details,
                }
                for s in scores
            ],
            "failure_diagnostics": diagnostics,
            "provenance": provenance,
            "samples_comparison": samples_comparison,
        }

    @app.get("/api/runs/{run_id}/export")
    def export_run_report(
        run_id: int,
        request: Request,
        format: str = "json",
        download: bool = False,
        locale: str | None = Query(
            None, description="Preferred language code ('ru' or 'en')"
        ),
    ):
        """
        Exports verification report as structured JSON evidence pack or
        self-contained printable HTML/PDF dispute report.
        """
        loc = resolve_locale(locale, request, default_locale=cfg.locale)
        run_obj = db.get_run(run_id)
        if not run_obj:
            raise HTTPException(status_code=404, detail="Run not found")

        target = db.get_target(run_obj.target_id)
        baseline = db.get_baseline(run_obj.baseline_id)
        scores = db.get_scores(run_id)
        samples = db.get_run_samples(run_id)

        overall = Verdict.aggregate(scores)

        diagnostics = format_failure_diagnostics(scores, locale=loc)

        if format.lower() == "html":
            html_content = build_html_report(
                target=target or Target(id=run_obj.target_id, base_url="—", model="—"),
                baseline=baseline
                or Baseline(
                    id=run_obj.baseline_id,
                    target_id=run_obj.target_id,
                    battery_version="—",
                    captured_at="—",
                ),
                run=run_obj,
                scores=scores,
                overall_verdict=overall,
                samples=samples,
                failure_diagnostics=diagnostics,
                locale=loc,
            )
            headers = {}
            if download:
                headers["Content-Disposition"] = (
                    f'attachment; filename="attest-dispute-report-run-{run_id}.html"'
                )
            return HTMLResponse(content=html_content, headers=headers)

        # JSON Evidence Pack Export
        export_data = {
            "attest_version": __version__,
            "exported_at": datetime.now(UTC).isoformat(),
            "locale": loc,
            "verdict": overall.value,
            "failure_diagnostics": diagnostics,
            "target": (
                {
                    "id": target.id,
                    "model": target.model,
                    "base_url": target.base_url,
                    "description": target.description,
                }
                if target
                else {"id": run_obj.target_id}
            ),
            "baseline": (
                {
                    "id": baseline.id,
                    "battery_version": baseline.battery_version,
                    "captured_at": baseline.captured_at,
                    "status": baseline.status,
                    "notes": baseline.notes,
                }
                if baseline
                else {"id": run_obj.baseline_id}
            ),
            "run": {
                "id": run_obj.id,
                "target_id": run_obj.target_id,
                "baseline_id": run_obj.baseline_id,
                "started_at": run_obj.started_at,
                "finished_at": run_obj.finished_at,
                "status": run_obj.status,
                "trigger": run_obj.trigger,
                "battery_version": run_obj.battery_version,
            },
            "scores": [
                {
                    "method": s.method,
                    "scope": s.scope,
                    "value": s.value,
                    "threshold": s.threshold,
                    "verdict": s.verdict.value,
                    "details": s.details,
                    "computed_at": s.computed_at,
                }
                for s in scores
            ],
            "samples_count": len(samples),
            "samples": [
                {
                    "prompt_id": smp.prompt_id,
                    "latency_ms": smp.latency_ms,
                    "raw_text": smp.raw_text,
                    "fingerprint": smp.fingerprint,
                    "model_returned": smp.model_returned,
                    "usage": smp.usage,
                    "logprobs": smp.logprobs,
                    "sampled_at": smp.sampled_at,
                }
                for smp in samples
            ],
        }
        json_bytes = json.dumps(export_data, indent=2, ensure_ascii=False).encode(
            "utf-8"
        )
        headers = {
            "Content-Disposition": f'attachment; filename="attest-audit-run-{run_id}.json"'
        }
        return Response(
            content=json_bytes, media_type="application/json", headers=headers
        )

    @app.get("/api/runs/{run_id}/dispute-pack")
    def get_run_dispute_pack(
        run_id: int,
        request: Request,
        format: str = "json",
        download: bool = False,
        locale: str | None = Query(
            None, description="Preferred language code ('ru' or 'en')"
        ),
    ):
        """
        Generates a comprehensive dispute forensic pack including
        cryptographic baseline verification, paired candidate vs baseline samples,
        and ready-to-file formal dispute notice.
        """
        loc = resolve_locale(locale, request, default_locale=cfg.locale)
        try:
            pack = generate_dispute_pack(db, run_id, locale=loc)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        if format.lower() in ("md", "markdown"):
            md_content = pack["dispute_letter_markdown"]
            headers = {}
            if download:
                headers["Content-Disposition"] = (
                    f'attachment; filename="attest-dispute-pack-run-{run_id}.md"'
                )
            return PlainTextResponse(
                content=md_content, media_type="text/markdown", headers=headers
            )

        if download:
            json_bytes = json.dumps(pack, indent=2, ensure_ascii=False).encode("utf-8")
            headers = {
                "Content-Disposition": f'attachment; filename="attest-dispute-pack-run-{run_id}.json"'
            }
            return Response(
                content=json_bytes, media_type="application/json", headers=headers
            )

        return pack

    @app.get("/api/compare")
    def compare_runs_endpoint(
        run_a: int = Query(..., description="First run ID to compare"),
        run_b: int = Query(..., description="Second run ID to compare"),
        locale: str | None = Query(
            None, description="Preferred language code ('ru' or 'en')"
        ),
    ):
        """
        Side-by-side comparative analysis between two audit runs.
        Returns metrics, infrastructure breakdown, TPS/latency deltas, and winner recommendation.
        """
        from attest.comparator.compare import compare_runs

        try:
            res = compare_runs(db, run_a, run_b)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (RuntimeError, KeyError) as e:
            raise HTTPException(status_code=500, detail=str(e))

        return res.to_dict()

    # --- Schedules & Recurring Drift Monitoring ---
    @app.get("/api/schedules")
    def list_schedules():
        schedules = db.list_schedules()
        targets = {t.id: t for t in db.list_targets()}
        out = []
        for s in schedules:
            tgt = targets.get(s.target_id)
            has_baseline = db.resolve_target_baseline(s.target_id)[0] is not None
            out.append(
                {
                    "id": s.id,
                    "target_id": s.target_id,
                    "target_model": tgt.model if tgt else "—",
                    "base_url": tgt.base_url if tgt else "—",
                    "interval_hours": s.interval_hours,
                    "battery": s.battery,
                    "enabled": s.enabled,
                    "last_run_at": s.last_run_at,
                    "next_run_at": s.next_run_at,
                    "created_at": s.created_at,
                    "has_baseline": has_baseline,
                }
            )
        return out

    @app.post("/api/schedules")
    def create_or_update_schedule(req: ScheduleCreateRequest):
        tgt = db.get_target(req.target_id)
        if not tgt:
            raise HTTPException(
                status_code=404, detail=f"Target '{req.target_id}' not found"
            )
        sched_id = db.create_or_update_schedule(
            target_id=req.target_id,
            interval_hours=req.interval_hours,
            battery=req.battery,
            enabled=req.enabled,
        )
        return {"id": sched_id, "target_id": req.target_id, "status": "saved"}

    @app.delete("/api/schedules/{schedule_id}")
    def delete_schedule(schedule_id: int):
        success = db.delete_schedule(schedule_id)
        if not success:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return {"deleted": True, "id": schedule_id}

    @app.post("/api/schedules/{schedule_id}/trigger")
    def trigger_schedule_now(schedule_id: int, background_tasks: BackgroundTasks):
        sched = db.get_schedule(schedule_id)
        if not sched:
            raise HTTPException(status_code=404, detail="Schedule not found")
        tgt = db.get_target(sched.target_id)
        if not tgt:
            raise HTTPException(status_code=404, detail="Target not found")
        baseline, _ = db.resolve_target_baseline(tgt.id)
        if not baseline:
            raise HTTPException(
                status_code=400,
                detail=f"Target '{tgt.id}' has no baseline. Capture an official snapshot first.",
            )

        db.record_schedule_tick(sched.id, sched.interval_hours)
        task_id = f"sched-{str(uuid.uuid4())[:6]}"
        _register_task(task_id, tgt.id, "audit", db=db)
        battery_path = str(resolve_battery_path(sched.battery, default=cfg.battery))

        background_tasks.add_task(
            _run_audit_worker,
            task_id,
            tgt,
            False,
            None,
            battery_path,
            "scheduled",
        )
        return {"task_id": task_id, "target_id": tgt.id}

    @app.get("/api/stats")
    def get_system_stats():
        return db.get_system_stats(limit_runs=100)

    # --- Static Files & SPA Route ---
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        async def serve_spa():
            index_file = STATIC_DIR / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
            return {"message": "Attest Web UI static files not found."}

    return app
