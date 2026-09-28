"""
Service layer orchestrating verification, baseline capture, and diagnostics.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from attest.alerting.webhook import dispatch_webhook_alert
from attest.battery.loader import estimate_battery_cost, load_battery
from attest.comparator.pipeline import ComparatorPipeline
from attest.config import AttestConfig
from attest.db import Database
from attest.models import (
    Baseline,
    BaselineStatus,
    MethodTier,
    PromptItem,
    RawSample,
    Run,
    RunStatus,
    RunTrigger,
    Score,
    Target,
    Verdict,
)
from attest.sampling.openai_compat import OpenAICompatAdapter
from attest.sampling.runner import (
    SamplingBatteryError,
    run_sampling_battery,
    safe_async_run,
)
from attest.security import (
    encrypt_api_key,
    mask_key_for_diagnostics,
    resolve_api_key,
)
from attest.utils import calculate_token_cost

logger = logging.getLogger("attest.service")


class AttestServiceError(Exception):
    """Base exception for service operations."""


class BaselineNotFoundError(AttestServiceError):
    """Raised when a baseline cannot be resolved for a target or model."""


class BaselineIntegrityError(AttestServiceError):
    """Raised when a baseline fails cryptographic integrity checks."""


@dataclass
class BaselineCaptureResult:
    baseline_id: int
    samples: list[RawSample]
    prompts: list[PromptItem]
    total_requests: int
    captured_at: str


@dataclass
class AuditResult:
    run: Run
    target: Target
    baseline: Baseline
    scores: list[Score]
    overall_verdict: Verdict
    run_samples: list[RawSample]
    prompts: list[PromptItem]
    duration_s: float
    total_tokens: int
    est_cost_usd: float
    summary_message: str
    source_desc: str
    streak: int
    alert_dispatched: bool
    failure_diagnostics: list[dict[str, Any]] = field(default_factory=list)


class AttestService:
    def __init__(self, db: Database, config: AttestConfig):
        self.db = db
        self.config = config

    def _resolve_target_key(self, target: Target) -> tuple[str, str]:
        """API key for a target plus a masked note of which key it is and where it
        came from, appended to sampling errors so a stale or borrowed key is obvious."""
        api_key, source = resolve_api_key(
            target.id, target.encrypted_key, base_url=target.base_url
        )
        if source == "encrypted_db":
            origin = f"stored for target '{target.id}'"
        else:
            origin = f"from {source.removeprefix('env:')} env var"
        if not api_key:
            fallback_enc = self.db.find_encrypted_key_for_url(target.base_url)
            if fallback_enc:
                api_key, _ = resolve_api_key(
                    target.id, fallback_enc, base_url=target.base_url
                )
                origin = "borrowed from another target on the same host"
        if not api_key:
            raise ValueError(f"No API key available for target '{target.id}'")
        return api_key, f"API key {mask_key_for_diagnostics(api_key)}, {origin}"

    def estimate_battery(self, battery_path: str | None = None) -> dict[str, Any]:
        battery_file = battery_path or self.config.battery
        _, prompts = load_battery(battery_file)
        return estimate_battery_cost(prompts)

    async def capture_baseline_async(
        self,
        target: Target,
        battery_path: str | None = None,
        note: str | None = None,
        on_sample_done: Callable[[RawSample], None] | None = None,
        status: BaselineStatus | str = BaselineStatus.ACTIVE,
    ) -> BaselineCaptureResult:
        battery_file = battery_path or self.config.battery
        version, prompts_data = load_battery(battery_file)
        prompts = self.db.sync_prompts(prompts_data, version)

        api_key, key_desc = self._resolve_target_key(target)

        adapter = OpenAICompatAdapter(
            base_url=target.base_url,
            model=target.wire_model or target.model,
            api_key=api_key,
            extra_headers=target.extra_headers,
            timeout_seconds=self.config.sampling.timeout_seconds,
            retry_max=self.config.sampling.retry_max,
            retry_backoff=self.config.sampling.retry_backoff,
        )

        est = estimate_battery_cost(prompts)
        samples: list[RawSample] = []

        def _handle_sample(s: RawSample):
            samples.append(s)
            if on_sample_done:
                on_sample_done(s)

        try:
            await run_sampling_battery(
                adapter=adapter,
                prompts=prompts,
                concurrency=self.config.sampling.concurrency,
                on_sample_done=_handle_sample,
            )
        except SamplingBatteryError as err:
            raise SamplingBatteryError(f"{err} [{key_desc}]") from err
        finally:
            await adapter.close()

        if not samples:
            raise AttestServiceError(
                "No samples were captured during baseline execution."
            )

        baseline_id = self.db.create_baseline_with_samples(
            target_id=target.id,
            battery_version=version,
            samples=samples,
            notes=note,
            status=status,
        )

        baseline_obj = self.db.get_baseline(baseline_id)
        captured_at = baseline_obj.captured_at if baseline_obj else ""

        return BaselineCaptureResult(
            baseline_id=baseline_id,
            samples=samples,
            prompts=prompts,
            total_requests=est["total_requests"],
            captured_at=captured_at,
        )

    def capture_baseline(
        self,
        target: Target,
        battery_path: str | None = None,
        note: str | None = None,
        on_sample_done: Callable[[RawSample], None] | None = None,
        status: BaselineStatus | str = BaselineStatus.ACTIVE,
    ) -> BaselineCaptureResult:
        return safe_async_run(
            self.capture_baseline_async(
                target=target,
                battery_path=battery_path,
                note=note,
                on_sample_done=on_sample_done,
                status=status,
            )
        )

    async def audit_target_async(
        self,
        target: Target,
        battery_path: str | None = None,
        mmd: bool = False,
        against: str | None = None,
        trigger: RunTrigger | str = RunTrigger.MANUAL,
        on_sample_done: Callable[[RawSample], None] | None = None,
    ) -> AuditResult:
        baseline, source_desc = self.db.resolve_target_baseline(
            target.id, against_target_or_model=against
        )
        if not baseline or baseline.id is None:
            raise BaselineNotFoundError(
                f"No active baseline found for target '{target.id}' or model '{target.model}'"
            )

        valid, stored_hash, comp_hash = self.db.verify_baseline_integrity(baseline.id)
        if not valid:
            raise BaselineIntegrityError(
                f"Baseline #{baseline.id} ({source_desc}) failed HMAC integrity check "
                f"(stored: {stored_hash}, computed: {comp_hash}). The baseline was modified, "
                f"the master key changed, or it predates HMAC sealing "
                f"(run 'attest baseline reseal' only if you trust its current contents)."
            )

        baseline_samples = self.db.get_baseline_samples(baseline.id)
        if not baseline_samples:
            raise ValueError(
                f"Baseline #{baseline.id} ({source_desc}) has no samples stored."
            )

        battery_file = battery_path or self.config.battery
        version, prompts_data = load_battery(battery_file)
        prompts = self.db.sync_prompts(prompts_data, version)

        # Prompts the baseline never sampled have nothing to be compared with: skip
        # them before paying for requests (e.g. a level-3 run on a level-1 baseline)
        covered = {s.prompt_id for s in baseline_samples}
        uncovered = [p for p in prompts if p.id not in covered]
        if len(uncovered) == len(prompts):
            raise AttestServiceError(
                f"Baseline #{baseline.id} ({baseline.battery_version}) covers none of "
                f"the prompts of battery '{version}'. Capture the baseline with this "
                f"battery, or with a higher defence level of the same family."
            )
        prompts = [p for p in prompts if p.id in covered]

        api_key, key_desc = self._resolve_target_key(target)

        adapter = OpenAICompatAdapter(
            base_url=target.base_url,
            model=target.wire_model or target.model,
            api_key=api_key,
            extra_headers=target.extra_headers,
            timeout_seconds=self.config.sampling.timeout_seconds,
            retry_max=self.config.sampling.retry_max,
            retry_backoff=self.config.sampling.retry_backoff,
        )

        run_id = self.db.create_run(
            target_id=target.id,
            baseline_id=baseline.id,
            battery_version=version,
            trigger=trigger,
            status=RunStatus.RUNNING,
        )

        run_samples: list[RawSample] = []
        start_time = time.perf_counter()

        def _handle_sample(s: RawSample):
            run_samples.append(s)
            if on_sample_done:
                on_sample_done(s)

        try:
            try:
                await run_sampling_battery(
                    adapter=adapter,
                    prompts=prompts,
                    concurrency=self.config.sampling.concurrency,
                    on_sample_done=_handle_sample,
                )
            except SamplingBatteryError as err:
                raise SamplingBatteryError(f"{err} [{key_desc}]") from err
            finally:
                await adapter.close()
                if run_samples:
                    self.db.save_run_samples(run_id=run_id, samples=run_samples)

            duration_s = time.perf_counter() - start_time

            pipeline = ComparatorPipeline(thresholds=self.config.thresholds)
            pipe_result = pipeline.execute(
                target=target,
                baseline_samples=baseline_samples,
                run_samples=run_samples,
                prompts=prompts,
                run_id=run_id,
                include_level3_mmd=mmd,
                locale=self.config.locale,
            )

            if uncovered:
                pipe_result.scores.append(
                    Score(
                        id=None,
                        run_id=run_id,
                        method=MethodTier.BASELINE_COVERAGE.value,
                        scope="aggregate",
                        value=float(len(uncovered)),
                        threshold=None,
                        verdict=Verdict.SKIP,
                        details={
                            "skipped_prompts": len(uncovered),
                            "skipped_requests": sum(p.samples_count for p in uncovered),
                            "baseline_battery": baseline.battery_version,
                            "message": (
                                f"{len(uncovered)} prompts were not run: baseline "
                                f"#{baseline.id} has no samples for them. Capture the "
                                "baseline at this level to check them too."
                            ),
                        },
                    )
                )
            self.db.save_scores(pipe_result.scores)
            self.db.finish_run(run_id=run_id, status=RunStatus.COMPLETED)
        except Exception:
            self.db.finish_run(run_id=run_id, status=RunStatus.FAILED)
            raise

        total_tokens = sum(
            (s.usage.get("total_tokens", 0) if s.usage else (len(s.raw_text) // 3))
            for s in run_samples
        )
        est_cost_usd = calculate_token_cost(
            total_tokens=total_tokens,
            cost_per_million=self.config.cost.cost_per_million_tokens,
        )

        run_obj = self.db.get_run(run_id)
        if run_obj is None:
            raise AttestServiceError(
                f"Run #{run_id} could not be retrieved from database."
            )

        streak = 0
        alert_dispatched = False
        if self.config.alerting.webhook_url and pipe_result.overall_verdict in (
            Verdict.WARN,
            Verdict.FAIL,
        ):
            streak = self.db.count_consecutive_failures(target.id)
            if streak >= self.config.alerting.consecutive_fails_before_alert:
                alert_dispatched = await dispatch_webhook_alert(
                    webhook_url=self.config.alerting.webhook_url,
                    target=target,
                    run=run_obj,
                    overall_verdict=pipe_result.overall_verdict,
                    summary_message=f"[Streak: {streak}/{self.config.alerting.consecutive_fails_before_alert}] {pipe_result.summary_message}",
                    diagnostics=pipe_result.failure_diagnostics,
                    locale=self.config.locale,
                )
            else:
                logger.info(
                    "Webhook alert suppressed: streak %d < threshold %d",
                    streak,
                    self.config.alerting.consecutive_fails_before_alert,
                )

        return AuditResult(
            run=run_obj,
            target=target,
            baseline=baseline,
            scores=pipe_result.scores,
            overall_verdict=pipe_result.overall_verdict,
            run_samples=run_samples,
            prompts=prompts,
            duration_s=duration_s,
            total_tokens=total_tokens,
            est_cost_usd=est_cost_usd,
            summary_message=pipe_result.summary_message,
            source_desc=source_desc,
            streak=streak,
            alert_dispatched=alert_dispatched,
            failure_diagnostics=pipe_result.failure_diagnostics,
        )

    def audit_target(
        self,
        target: Target,
        battery_path: str | None = None,
        mmd: bool = False,
        against: str | None = None,
        trigger: RunTrigger | str = RunTrigger.MANUAL,
        on_sample_done: Callable[[RawSample], None] | None = None,
    ) -> AuditResult:
        return safe_async_run(
            self.audit_target_async(
                target=target,
                battery_path=battery_path,
                mmd=mmd,
                against=against,
                trigger=trigger,
                on_sample_done=on_sample_done,
            )
        )

    def compare_runs(self, run_a_id: int, run_b_id: int):
        """Perform side-by-side comparative analysis between two evaluation runs."""
        from attest.comparator.compare import compare_runs

        return compare_runs(self.db, run_a_id, run_b_id)

    def sync_targets_from_config(self) -> int:
        """
        Synchronizes targets defined in attest.yaml into the SQLite database.
        Returns the count of newly registered targets.
        """
        if not self.config.targets:
            return 0

        synced = 0
        for tf in self.config.targets:
            existing = self.db.get_target(tf.id)
            if not existing:
                enc_key = encrypt_api_key(tf.key) if tf.key else None
                new_target = Target(
                    id=tf.id,
                    base_url=tf.base_url,
                    model=tf.model,
                    encrypted_key=enc_key,
                    wire_model=tf.wire_model,
                    description=tf.description,
                    extra_headers=tf.extra_headers,
                )
                self.db.save_target(new_target)
                synced += 1
                logger.info("Synced target '%s' from config file into database", tf.id)
        return synced
