"""
Configuration models and loader for Attest.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class SamplingConfig(BaseModel):
    concurrency: int = Field(
        default=5, description="Concurrent HTTP requests to the target API"
    )
    timeout_seconds: float = Field(
        default=30.0, description="Per-request timeout in seconds"
    )
    retry_max: int = Field(
        default=3, description="Maximum retry attempts on transient network errors"
    )
    retry_backoff: float = Field(default=2.0, description="Exponential backoff factor")


class ThresholdsConfig(BaseModel):
    jsd_warn: float = Field(default=0.10, description="JSD threshold for warning")
    jsd_fail: float = Field(
        default=0.15, description="JSD threshold for failure (spoofing alert)"
    )
    reasoning_jsd_fail: float = Field(
        default=0.35,
        description="Adaptive JSD threshold for reasoning/thinking models (e.g. Gemini Thinking, DeepSeek R1, o-series)",
    )
    embedding_cosine_warn: float = Field(
        default=0.88, description="Embedding cosine similarity warn threshold"
    )
    embedding_cosine_fail: float = Field(
        default=0.80, description="Embedding cosine similarity fail threshold"
    )
    mmd_pvalue_warn: float = Field(
        default=0.05, description="MMD permutation test p-value warn threshold"
    )
    mmd_pvalue_fail: float = Field(
        default=0.01, description="MMD permutation test p-value fail threshold"
    )
    ttft_drift_warn: float = Field(
        default=0.60,
        description="Warn when median time-to-first-token shifts by >=60% (WARN only)",
    )
    iris_pvalue_warn: float = Field(
        default=0.05,
        description="IRIS random-string test p-value warn threshold (excess atypical answers)",
    )
    iris_pvalue_fail: float = Field(
        default=0.01,
        description="IRIS random-string test p-value fail threshold",
    )
    tps_drift_warn: float = Field(
        default=0.50,
        description="Deprecated: unused; TPS verdicts use tps_drop_* and tps_speedup_warn",
    )
    tps_drift_fail: float = Field(
        default=1.00,
        description="Deprecated: only reported as the threshold on skipped TPS scores",
    )
    tps_drop_warn: float = Field(
        default=0.35, description="TPS slowdown threshold for warning (35% drop)"
    )
    tps_drop_fail: float = Field(
        default=0.50,
        description="TPS slowdown threshold for failure (50% drop = 2x slower)",
    )
    tps_speedup_warn: float = Field(
        default=1.00,
        description="TPS speedup threshold for warning (100% = 2x speedup)",
    )
    latency_drift_warn: float = Field(
        default=0.60, description="Latency median drift threshold for warning (60%)"
    )
    latency_drift_fail: float = Field(
        default=1.20,
        description="Latency median drift threshold for elevated warning (120%)",
    )
    billing_prompt_scale_warn: float = Field(
        default=0.05,
        description="Warn when input tokens are billed >=5% above baseline per token",
    )
    billing_prompt_scale_fail: float = Field(
        default=0.15,
        description="Fail when input tokens are billed >=15% above baseline per token",
    )
    billing_prompt_overhead_warn: float = Field(
        default=25.0,
        description="Warn when >=25 extra input tokens are billed on every request",
    )
    billing_prompt_overhead_fail: float = Field(
        default=100.0,
        description="Fail when >=100 extra input tokens are billed on every request (hidden prompt)",
    )
    billing_completion_warn: float = Field(
        default=0.10,
        description="Warn when output text is billed >=10% more tokens than baseline",
    )
    billing_completion_fail: float = Field(
        default=0.25,
        description="Fail when output text is billed >=25% more tokens than baseline",
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Local sentence-transformers embedding model name or path",
    )
    embedding_allow_download: bool = Field(
        default=False,
        description=(
            "Allow sentence-transformers to download embedding_model from Hugging Face. "
            "Off by default: only a locally cached model is used, else the n-gram fallback."
        ),
    )


class CostConfig(BaseModel):
    cost_per_million_tokens: float = Field(
        default=5.0,
        description="Estimated blended dollar cost per 1M tokens for run reporting",
    )


class AlertingConfig(BaseModel):
    webhook_url: str | None = Field(
        default=None, description="Optional Slack / Discord / custom webhook URL"
    )
    consecutive_fails_before_alert: int = Field(
        default=2, description="Consecutive failed runs before sending alert"
    )


class TargetFileConfig(BaseModel):
    id: str
    base_url: str
    model: str
    key: str | None = None
    wire_model: str | None = None
    description: str | None = None
    extra_headers: dict[str, str] = Field(default_factory=dict)


class AttestConfig(BaseModel):
    locale: str = Field(default="ru", description="System language ('ru' or 'en')")
    database: str = Field(
        default="attest.db", description="Path to SQLite database file"
    )
    cors_origins: list[str] = Field(
        default_factory=list,
        description=(
            "Extra origins allowed to call the Web API cross-origin. Empty = same-origin only. "
            "'*' disables the origin check entirely (not recommended: any website could drive the API)."
        ),
    )
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "::1"],
        description=(
            "Host header values the Web API answers to (DNS-rebinding protection). "
            "'*' disables the check."
        ),
    )
    battery: str = Field(
        default="batteries/v1.yaml", description="Path to active battery YAML file"
    )
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    alerting: AlertingConfig = Field(default_factory=AlertingConfig)
    targets: list[TargetFileConfig] = Field(default_factory=list)


DEFAULT_CONFIG_FILENAME = "attest.yaml"


def find_config_path(explicit_path: str | Path | None = None) -> Path | None:
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return p
        return None

    # Check cwd
    cwd_config = Path.cwd() / DEFAULT_CONFIG_FILENAME
    if cwd_config.exists():
        return cwd_config

    # Check ~/.attest/attest.yaml
    home_config = Path.home() / ".attest" / DEFAULT_CONFIG_FILENAME
    if home_config.exists():
        return home_config

    return None


def load_config(explicit_path: str | Path | None = None) -> AttestConfig:
    """Load config from YAML file, falling back to defaults if not found."""
    path = find_config_path(explicit_path)
    if not path:
        cfg = AttestConfig()
    else:
        with open(path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        cfg = AttestConfig.model_validate(data)

    env_db = os.environ.get("ATTEST_DATABASE") or os.environ.get("ATTEST_DB_PATH")
    if env_db:
        cfg.database = env_db

    env_cors = os.environ.get("ATTEST_CORS_ORIGINS")
    if env_cors:
        cfg.cors_origins = [o.strip() for o in env_cors.split(",") if o.strip()]

    env_hosts = os.environ.get("ATTEST_ALLOWED_HOSTS")
    if env_hosts:
        cfg.allowed_hosts = [h.strip() for h in env_hosts.split(",") if h.strip()]

    return cfg


def create_default_config_file(
    dest_path: Path, database_path: str = "attest.db"
) -> Path:
    """Write an annotated default configuration file."""
    default_yaml = f"""# Attest Configuration File
# Documentation: https://github.com/ahmedakaev/attest

locale: ru
database: {database_path}
battery: batteries/v1.yaml

thresholds:
  jsd_warn: 0.10
  jsd_fail: 0.15
  reasoning_jsd_fail: 0.35      # Relaxed JSD fail threshold for reasoning/thinking models
  embedding_cosine_warn: 0.88
  embedding_cosine_fail: 0.80
  mmd_pvalue_warn: 0.05
  mmd_pvalue_fail: 0.01
  tps_drift_warn: 0.50
  tps_drift_fail: 1.00
  tps_drop_warn: 0.35           # Warning if generation slows down by >=35%
  tps_drop_fail: 0.50           # Failure alert if generation slows down by >=50% (2x slower)
  tps_speedup_warn: 1.00        # Warning if generation speeds up by >=100% (2x faster, likely lighter model)
  latency_drift_warn: 0.60
  latency_drift_fail: 1.20
  billing_prompt_scale_warn: 0.05     # Input tokens billed >=5% above baseline
  billing_prompt_scale_fail: 0.15
  billing_prompt_overhead_warn: 25    # Extra input tokens added to every request
  billing_prompt_overhead_fail: 100   # (e.g. a hidden system prompt you pay for)
  billing_completion_warn: 0.10       # Output text billed >=10% more tokens
  billing_completion_fail: 0.25


sampling:
  concurrency: 5
  timeout_seconds: 30.0
  retry_max: 3
  retry_backoff: 2.0

alerting:
  webhook_url: null
  consecutive_fails_before_alert: 2

cost:
  cost_per_million_tokens: 5.00

# You can configure targets here or add them via CLI:
#   attest target add --id my-gpt4o --url https://api.openai.com/v1 --model gpt-4o
targets: []
"""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(default_yaml)
    return dest_path
