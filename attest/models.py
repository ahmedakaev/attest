"""
Core domain models and data transfer objects for Attest.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class Verdict(str, enum.Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"

    @property
    def color(self) -> str:
        if self == Verdict.PASS:
            return "green"
        if self == Verdict.WARN:
            return "yellow"
        if self == Verdict.FAIL:
            return "red"
        return "dim"

    @classmethod
    def aggregate(cls, scores: list[Score] | tuple[Score, ...]) -> Verdict:
        """
        Computes the unified aggregate overall verdict across evaluation scores.
        Excludes purely observational scores (e.g. gateway infrastructure detection)
        and skipped evaluations.
        """
        verdicts = [
            s.verdict
            for s in scores
            if s.verdict != Verdict.SKIP
            and s.method not in (MethodTier.INFRASTRUCTURE.value, "infrastructure")
        ]
        if any(v == Verdict.FAIL for v in verdicts):
            return Verdict.FAIL
        if any(v == Verdict.WARN for v in verdicts):
            return Verdict.WARN
        if any(v == Verdict.PASS for v in verdicts):
            return Verdict.PASS
        return Verdict.SKIP


class MethodTier(str, enum.Enum):
    QUICK_MODEL = "quick_model"
    QUICK_FINGERPRINT = "quick_fingerprint"
    QUICK_SEED = "quick_seed"
    ROUTING_PROOF = "routing_proof"
    TOKENIZER = "tokenizer"
    INFRASTRUCTURE = "infrastructure"
    JSD = "jsd"
    LATENCY_TPS = "latency_tps"
    LATENCY_DRIFT = "latency_drift"
    LATENCY_TTFT = "latency_ttft"
    EMBEDDING_COSINE = "embedding_cosine"
    MMD_PERMUTATION = "mmd_permutation"
    ASSERTIONS = "assertions"
    BILLING = "billing"
    IRIS = "iris"
    GATEWAY_LIMITS = "gateway_limits"
    BASELINE_COVERAGE = "baseline_coverage"


class BaselineStatus(str, enum.Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"


class RunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunTrigger(str, enum.Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    WEB_UI = "web_ui"


@dataclass
class PromptAssertion:
    type: str
    value: Any = None
    optional: bool = False


@dataclass
class Target:
    id: str
    base_url: str
    model: str
    encrypted_key: str | None = None
    description: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)
    wire_model: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class PromptItem:
    id: int | None
    category: str
    text: str
    params: dict[str, Any]
    samples_count: int
    battery_version: str
    assertions: list[PromptAssertion] = field(default_factory=list)
    messages: list[dict[str, Any]] | None = None


@dataclass
class Baseline:
    id: int | None
    target_id: str
    battery_version: str
    captured_at: str
    status: BaselineStatus | str = BaselineStatus.ACTIVE
    notes: str | None = None
    integrity_hash: str | None = None


@dataclass
class RawSample:
    prompt_id: int
    raw_text: str
    latency_ms: int = 0
    fingerprint: str | None = None
    model_returned: str | None = None
    usage: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    logprobs: dict[str, float] | None = None
    reasoning_content: str | None = None
    reasoning_tokens: int | None = None
    routing_proof: dict[str, Any] | None = None
    sampled_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # Time to first streamed token (content or reasoning); None when not streamed
    ttft_ms: int | None = None
    # Output cap sent with the request (max_tokens or max_completion_tokens)
    max_tokens_sent: int | None = None


@dataclass
class Run:
    id: int | None
    target_id: str
    baseline_id: int
    battery_version: str
    started_at: str
    finished_at: str | None = None
    status: RunStatus | str = RunStatus.RUNNING
    trigger: RunTrigger | str = RunTrigger.MANUAL


@dataclass
class Score:
    id: int | None
    run_id: int
    method: str
    scope: str
    value: float
    threshold: float | None
    verdict: Verdict
    details: dict[str, Any] = field(default_factory=dict)
    computed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class RunReport:
    run: Run
    target: Target
    baseline: Baseline
    scores: list[Score]
    samples_count: int
    total_tokens: int
    estimated_cost_usd: float
    overall_verdict: Verdict
    summary_message: str = ""
    failure_diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run.id,
            "target_id": self.target.id,
            "model": self.target.model,
            "baseline_id": self.baseline.id,
            "battery_version": self.run.battery_version,
            "started_at": self.run.started_at,
            "finished_at": self.run.finished_at,
            "status": getattr(self.run.status, "value", str(self.run.status)),
            "trigger": getattr(self.run.trigger, "value", str(self.run.trigger)),
            "overall_verdict": self.overall_verdict.value,
            "samples_count": self.samples_count,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "summary_message": self.summary_message,
            "failure_diagnostics": self.failure_diagnostics,
            "scores": [
                {
                    "id": s.id,
                    "method": s.method,
                    "scope": s.scope,
                    "value": s.value,
                    "threshold": s.threshold,
                    "verdict": s.verdict.value,
                    "details": s.details,
                    "computed_at": s.computed_at,
                }
                for s in self.scores
            ],
        }


@dataclass
class Schedule:
    id: int | None
    target_id: str
    interval_hours: int
    battery: str = "quick"
    enabled: bool = True
    last_run_at: str | None = None
    next_run_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
