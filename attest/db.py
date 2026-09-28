"""
SQLite database engine and queries for Attest.
Zero ORM, lightweight, fast, WAL-enabled.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from attest.migrations import SCHEMA_SQL, apply_migrations, has_column, init_database
from attest.models import (
    Baseline,
    BaselineStatus,
    PromptAssertion,
    PromptItem,
    RawSample,
    Run,
    RunReport,
    RunStatus,
    RunTrigger,
    Schedule,
    Score,
    Target,
    Verdict,
)
from attest.security import get_or_create_master_key
from attest.utils import calculate_token_cost, canonicalize_model_name


def _parse_baseline_status(val: Any) -> BaselineStatus | str:
    if isinstance(val, BaselineStatus):
        return val
    try:
        return BaselineStatus(str(val))
    except ValueError:
        return str(val) if val is not None else "active"


def _parse_run_status(val: Any) -> RunStatus | str:
    if isinstance(val, RunStatus):
        return val
    try:
        return RunStatus(str(val))
    except ValueError:
        return str(val) if val is not None else "running"


def _parse_run_trigger(val: Any) -> RunTrigger | str:
    if isinstance(val, RunTrigger):
        return val
    try:
        return RunTrigger(str(val))
    except ValueError:
        return str(val) if val is not None else "manual"


# SCHEMA_SQL and migrations are encapsulated in attest.migrations.
# Re-exported here for full backwards compatibility.
__all__ = ["SCHEMA_SQL", "Database", "compute_samples_hash", "compute_samples_hmac"]


def compute_samples_hash(samples: list[RawSample]) -> str:
    """
    Legacy unkeyed SHA-256 checksum over core sample fields.
    Only detects accidental corruption (anyone able to edit rows can recompute it);
    kept solely to verify baselines captured before HMAC integrity was introduced.
    """
    hasher = hashlib.sha256()
    sorted_samples = sorted(
        samples,
        key=lambda s: (
            s.prompt_id,
            s.sampled_at,
            s.raw_text,
            s.fingerprint or "",
            s.model_returned or "",
        ),
    )
    for s in sorted_samples:
        payload = (
            f"prompt_id:{s.prompt_id}|"
            f"text:{s.raw_text}|"
            f"lat:{s.latency_ms}|"
            f"fp:{s.fingerprint or ''}|"
            f"model:{s.model_returned or ''}|"
            f"time:{s.sampled_at}\n"
        )
        hasher.update(payload.encode("utf-8"))
    return hasher.hexdigest()


INTEGRITY_HMAC_PREFIX = "hmac-sha256:"


def _integrity_key() -> bytes:
    return hashlib.sha256(
        b"attest/baseline-integrity/v1" + get_or_create_master_key()
    ).digest()


def compute_samples_hmac(samples: list[RawSample]) -> str:
    """
    Keyed HMAC-SHA256 over every field the comparators consume (including logprobs
    and usage), using a key derived from the Attest master key. Without the master key
    a tampered baseline cannot be re-sealed, unlike a plain SHA-256 stored alongside it.
    """
    records = sorted(
        json.dumps(
            {
                # Added only when measured, so baselines sealed before TTFT still verify
                **({"ttft_ms": s.ttft_ms} if s.ttft_ms is not None else {}),
                **(
                    {"max_tokens_sent": s.max_tokens_sent}
                    if s.max_tokens_sent is not None
                    else {}
                ),
                "prompt_id": s.prompt_id,
                "raw_text": s.raw_text,
                "latency_ms": s.latency_ms,
                "fingerprint": s.fingerprint,
                "model_returned": s.model_returned,
                "usage": s.usage or {},
                "headers": s.headers or {},
                "logprobs": s.logprobs or None,
                "reasoning_content": s.reasoning_content,
                "reasoning_tokens": s.reasoning_tokens,
                "routing_proof": s.routing_proof or None,
                "sampled_at": s.sampled_at,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        for s in samples
    )
    mac = hmac.new(_integrity_key(), digestmod=hashlib.sha256)
    for rec in records:
        mac.update(rec.encode("utf-8") + b"\n")
    return INTEGRITY_HMAC_PREFIX + mac.hexdigest()


class Database:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = (
                os.environ.get("ATTEST_DATABASE")
                or os.environ.get("ATTEST_DB_PATH")
                or "attest.db"
            )
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connection() as conn:
            init_database(conn)

    def reseal_legacy_baselines(self) -> int:
        """
        Upgrades baselines sealed with the legacy unkeyed SHA-256 (or not sealed at all)
        to the keyed HMAC. Only HMAC seals are accepted during audits, so a tamperer cannot
        downgrade a baseline to a hash they can recompute. This is deliberately an explicit
        user action ('attest baseline reseal'), never automatic: running it declares the
        current contents trusted. Baselines whose legacy hash no longer matches are skipped.
        Returns the number of resealed baselines.
        """
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, integrity_hash FROM baselines "
                "WHERE integrity_hash IS NULL OR integrity_hash NOT LIKE ?",
                (INTEGRITY_HMAC_PREFIX + "%",),
            ).fetchall()
        resealed = 0
        for row in rows:
            samples = self.get_baseline_samples(row["id"])
            if not samples:
                continue
            legacy = row["integrity_hash"]
            if legacy is not None and legacy != compute_samples_hash(samples):
                continue
            with self.connection() as conn:
                conn.execute(
                    "UPDATE baselines SET integrity_hash = ? WHERE id = ?",
                    (compute_samples_hmac(samples), row["id"]),
                )
            resealed += 1
        return resealed

    @staticmethod
    def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
        return has_column(conn, table, column)

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        apply_migrations(conn)

    # --- Targets ---
    def save_target(self, target: Target) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO targets (id, base_url, model, encrypted_key, description, extra_headers, wire_model, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    base_url = excluded.base_url,
                    model = excluded.model,
                    encrypted_key = COALESCE(excluded.encrypted_key, targets.encrypted_key),
                    description = excluded.description,
                    extra_headers = excluded.extra_headers,
                    wire_model = excluded.wire_model
                """,
                (
                    target.id,
                    target.base_url,
                    target.model,
                    target.encrypted_key,
                    target.description,
                    json.dumps(target.extra_headers),
                    target.wire_model,
                    target.created_at,
                ),
            )

    def get_target(self, target_id: str) -> Target | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM targets WHERE id = ?", (target_id,)
            ).fetchone()
            if not row:
                return None
            return Target(
                id=row["id"],
                base_url=row["base_url"],
                model=row["model"],
                encrypted_key=row["encrypted_key"],
                description=row["description"],
                extra_headers=json.loads(row["extra_headers"] or "{}"),
                wire_model=row["wire_model"],
                created_at=row["created_at"],
            )

    def list_targets(self) -> list[Target]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM targets ORDER BY id ASC").fetchall()
            return [
                Target(
                    id=r["id"],
                    base_url=r["base_url"],
                    model=r["model"],
                    encrypted_key=r["encrypted_key"],
                    description=r["description"],
                    extra_headers=json.loads(r["extra_headers"] or "{}"),
                    wire_model=r["wire_model"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def delete_target(self, target_id: str) -> bool:
        with self.connection() as conn:
            cur = conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))
            return cur.rowcount > 0

    def find_encrypted_key_for_url(self, base_url: str | None) -> str | None:
        """Find an existing encrypted API key for a target matching the same base URL or host."""
        if not base_url:
            return None
        clean_target = base_url.rstrip("/").lower()
        targets = self.list_targets()

        # 1. Exact match on normalized base URL
        for t in targets:
            if t.encrypted_key:
                clean_t = (t.base_url or "").rstrip("/").lower()
                if clean_t == clean_target:
                    return t.encrypted_key

        # 2. Hostname match (e.g. api.example.com matches api.example.com/v1)
        try:
            from urllib.parse import urlparse

            parsed_target = urlparse(clean_target)
            target_host = parsed_target.netloc or parsed_target.path
            for t in targets:
                if t.encrypted_key:
                    clean_t = (t.base_url or "").rstrip("/").lower()
                    parsed_t = urlparse(clean_t)
                    t_host = parsed_t.netloc or parsed_t.path
                    if target_host and t_host and target_host == t_host:
                        return t.encrypted_key
        except (ValueError, AttributeError):
            return None

        return None

    # --- Prompts ---
    def sync_prompts(
        self, prompts: list[PromptItem], battery_version: str
    ) -> list[PromptItem]:
        result: list[PromptItem] = []
        with self.connection() as conn:
            for p in prompts:
                assertions_json = (
                    json.dumps(
                        [
                            {"type": a.type, "value": a.value, "optional": a.optional}
                            for a in p.assertions
                        ]
                    )
                    if p.assertions
                    else None
                )
                messages_json = json.dumps(p.messages) if p.messages else None
                cur = conn.execute(
                    """
                    INSERT INTO prompts (category, text, params, samples_count, battery_version, assertions, messages)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(text, category, battery_version) DO UPDATE SET
                        params = excluded.params,
                        samples_count = excluded.samples_count,
                        assertions = excluded.assertions,
                        messages = excluded.messages
                    RETURNING id
                    """,
                    (
                        p.category,
                        p.text,
                        json.dumps(p.params),
                        p.samples_count,
                        battery_version,
                        assertions_json,
                        messages_json,
                    ),
                )
                prompt_id = cur.fetchone()[0]
                result.append(
                    PromptItem(
                        id=prompt_id,
                        category=p.category,
                        text=p.text,
                        params=p.params,
                        samples_count=p.samples_count,
                        battery_version=battery_version,
                        assertions=p.assertions,
                        messages=p.messages,
                    )
                )
        return result

    def get_prompts(self, battery_version: str) -> list[PromptItem]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM prompts WHERE battery_version = ? ORDER BY id ASC",
                (battery_version,),
            ).fetchall()
            items: list[PromptItem] = []
            for r in rows:
                d = dict(r)
                raw_asserts = d.get("assertions")
                assertions: list[PromptAssertion] = []
                if raw_asserts:
                    try:
                        for a in json.loads(raw_asserts):
                            assertions.append(
                                PromptAssertion(
                                    type=a.get("type", ""),
                                    value=a.get("value"),
                                    optional=a.get("optional", False),
                                )
                            )
                    except (json.JSONDecodeError, TypeError, KeyError):
                        assertions = []
                messages: list[dict[str, Any]] | None = None
                raw_msgs = d.get("messages")
                if raw_msgs:
                    try:
                        messages = json.loads(raw_msgs)
                    except (json.JSONDecodeError, TypeError):
                        messages = None
                items.append(
                    PromptItem(
                        id=d["id"],
                        category=d["category"],
                        text=d["text"],
                        params=json.loads(d["params"]),
                        samples_count=d["samples_count"],
                        battery_version=d["battery_version"],
                        assertions=assertions,
                        messages=messages,
                    )
                )
            return items

    # --- Baselines ---
    def create_baseline(
        self,
        target_id: str,
        battery_version: str,
        notes: str | None = None,
        status: BaselineStatus | str = BaselineStatus.ACTIVE,
    ) -> int:
        status_str = status.value if isinstance(status, BaselineStatus) else str(status)
        with self.connection() as conn:
            # Mark prior active baselines as superseded
            conn.execute(
                "UPDATE baselines SET status = ? WHERE target_id = ? AND status = ?",
                (
                    BaselineStatus.SUPERSEDED.value,
                    target_id,
                    BaselineStatus.ACTIVE.value,
                ),
            )
            now = datetime.now(UTC).isoformat()
            cur = conn.execute(
                """
                INSERT INTO baselines (target_id, battery_version, captured_at, status, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (target_id, battery_version, now, status_str, notes),
            )
            return cur.lastrowid

    def save_baseline_samples(self, baseline_id: int, samples: list[RawSample]) -> None:
        int_hash = compute_samples_hmac(samples) if samples else None
        with self.connection() as conn:
            conn.executemany(
                """
                INSERT INTO baseline_samples (
                    baseline_id, prompt_id, raw_text, latency_ms,
                    fingerprint, model_returned, usage, headers, logprobs,
                    reasoning_content, reasoning_tokens, routing_proof, sampled_at, ttft_ms, max_tokens_sent
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        baseline_id,
                        s.prompt_id,
                        s.raw_text,
                        s.latency_ms,
                        s.fingerprint,
                        s.model_returned,
                        json.dumps(s.usage or {}),
                        json.dumps(s.headers or {}),
                        json.dumps(s.logprobs) if s.logprobs else None,
                        s.reasoning_content,
                        s.reasoning_tokens,
                        json.dumps(s.routing_proof) if s.routing_proof else None,
                        s.sampled_at,
                        s.ttft_ms,
                        s.max_tokens_sent,
                    )
                    for s in samples
                ],
            )
            if int_hash:
                conn.execute(
                    "UPDATE baselines SET integrity_hash = ? WHERE id = ?",
                    (int_hash, baseline_id),
                )

    def create_baseline_with_samples(
        self,
        target_id: str,
        battery_version: str,
        samples: list[RawSample],
        notes: str | None = None,
        status: BaselineStatus | str = BaselineStatus.ACTIVE,
    ) -> int:
        """
        Atomically creates a baseline and inserts all its samples within a single transaction,
        marking prior active baselines as superseded only upon complete success.
        """
        status_str = status.value if isinstance(status, BaselineStatus) else str(status)
        int_hash = compute_samples_hmac(samples) if samples else None
        now = datetime.now(UTC).isoformat()
        with self.connection() as conn:
            conn.execute(
                "UPDATE baselines SET status = ? WHERE target_id = ? AND status = ?",
                (
                    BaselineStatus.SUPERSEDED.value,
                    target_id,
                    BaselineStatus.ACTIVE.value,
                ),
            )
            cur = conn.execute(
                """
                INSERT INTO baselines (target_id, battery_version, captured_at, status, notes, integrity_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (target_id, battery_version, now, status_str, notes, int_hash),
            )
            baseline_id = cur.lastrowid
            if samples:
                conn.executemany(
                    """
                    INSERT INTO baseline_samples (
                        baseline_id, prompt_id, raw_text, latency_ms,
                        fingerprint, model_returned, usage, headers, logprobs,
                        reasoning_content, reasoning_tokens, routing_proof, sampled_at, ttft_ms, max_tokens_sent
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            baseline_id,
                            s.prompt_id,
                            s.raw_text,
                            s.latency_ms,
                            s.fingerprint,
                            s.model_returned,
                            json.dumps(s.usage or {}),
                            json.dumps(s.headers or {}),
                            json.dumps(s.logprobs) if s.logprobs else None,
                            s.reasoning_content,
                            s.reasoning_tokens,
                            json.dumps(s.routing_proof) if s.routing_proof else None,
                            s.sampled_at,
                            s.ttft_ms,
                            s.max_tokens_sent,
                        )
                        for s in samples
                    ],
                )
            return baseline_id

    def get_active_baseline(self, target_id: str) -> Baseline | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM baselines
                WHERE target_id = ? AND status = ?
                ORDER BY id DESC LIMIT 1
                """,
                (target_id, BaselineStatus.ACTIVE.value),
            ).fetchone()
            if not row:
                return None
            return Baseline(
                id=row["id"],
                target_id=row["target_id"],
                battery_version=row["battery_version"],
                captured_at=row["captured_at"],
                status=_parse_baseline_status(row["status"]),
                notes=row["notes"],
                integrity_hash=row["integrity_hash"],
            )

    def get_active_baseline_for_model(
        self, model: str, exclude_target_id: str | None = None
    ) -> Baseline | None:
        """
        Find an active baseline captured for any target matching the specified model name.
        Supports exact match and cross-provider canonical matching (e.g. 'openai/gpt-5.5' matches 'gpt-5.5').
        """
        canonical = canonicalize_model_name(model)
        with self.connection() as conn:
            # 1. Exact match on model
            query = """
                SELECT b.* FROM baselines b
                JOIN targets t ON b.target_id = t.id
                WHERE t.model = ? AND b.status = ?
            """
            params: list[str] = [model, BaselineStatus.ACTIVE.value]
            if exclude_target_id:
                query += " AND b.target_id != ?"
                params.append(exclude_target_id)
            query += " ORDER BY b.id DESC LIMIT 1"
            row = conn.execute(query, tuple(params)).fetchone()
            if row:
                return Baseline(
                    id=row["id"],
                    target_id=row["target_id"],
                    battery_version=row["battery_version"],
                    captured_at=row["captured_at"],
                    status=_parse_baseline_status(row["status"]),
                    notes=row["notes"],
                    integrity_hash=row["integrity_hash"],
                )

            # 2. Cross-provider canonical fallback
            if canonical:
                fallback_query = """
                    SELECT b.* FROM baselines b
                    JOIN targets t ON b.target_id = t.id
                    WHERE (t.model = ? OR t.model LIKE '%/' || ? OR ? LIKE '%/' || t.model)
                      AND b.status = ?
                """
                fallback_params: list[str] = [
                    canonical,
                    canonical,
                    model,
                    BaselineStatus.ACTIVE.value,
                ]
                if exclude_target_id:
                    fallback_query += " AND b.target_id != ?"
                    fallback_params.append(exclude_target_id)
                fallback_query += " ORDER BY b.id DESC LIMIT 1"
                row = conn.execute(fallback_query, tuple(fallback_params)).fetchone()
                if row:
                    return Baseline(
                        id=row["id"],
                        target_id=row["target_id"],
                        battery_version=row["battery_version"],
                        captured_at=row["captured_at"],
                        status=_parse_baseline_status(row["status"]),
                        notes=row["notes"],
                        integrity_hash=row["integrity_hash"],
                    )

            return None

    def resolve_target_baseline(
        self,
        target_id: str,
        against_target_or_model: str | None = None,
    ) -> tuple[Baseline | None, str]:
        """
        Resolves the baseline for auditing a target:
        1. If against_target_or_model is explicitly given:
           - if numeric (e.g. '42'): fetch baseline by ID
           - if matching a target ID: fetch that target's active baseline
           - if matching a model name: fetch active baseline for that model
        2. If target has its own direct active baseline: return it ('direct')
        3. If another target has an active baseline for the exact same model: return it ('inherited')
        4. Otherwise: (None, 'missing')
        """
        if against_target_or_model:
            if against_target_or_model.isdigit():
                b = self.get_baseline(int(against_target_or_model))
                if b:
                    return b, f"explicit #{b.id}"
            b = self.get_active_baseline(against_target_or_model)
            if b:
                return b, f"target '{against_target_or_model}'"
            b = self.get_active_baseline_for_model(against_target_or_model)
            if b:
                return b, f"model '{against_target_or_model}' (from '{b.target_id}')"

        direct = self.get_active_baseline(target_id)
        if direct:
            return direct, "direct"

        target = self.get_target(target_id)
        if target:
            model_b = self.get_active_baseline_for_model(
                target.model, exclude_target_id=target_id
            )
            if model_b:
                return model_b, f"model '{target.model}' (from '{model_b.target_id}')"

        return None, "missing"

    def get_baseline(self, baseline_id: int) -> Baseline | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM baselines WHERE id = ?", (baseline_id,)
            ).fetchone()
            if not row:
                return None
            return Baseline(
                id=row["id"],
                target_id=row["target_id"],
                battery_version=row["battery_version"],
                captured_at=row["captured_at"],
                status=_parse_baseline_status(row["status"]),
                notes=row["notes"],
                integrity_hash=row["integrity_hash"],
            )

    def list_baselines(self, target_id: str) -> list[Baseline]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM baselines WHERE target_id = ? ORDER BY id DESC",
                (target_id,),
            ).fetchall()
            return [
                Baseline(
                    id=r["id"],
                    target_id=r["target_id"],
                    battery_version=r["battery_version"],
                    captured_at=r["captured_at"],
                    status=_parse_baseline_status(r["status"]),
                    notes=r["notes"],
                    integrity_hash=r["integrity_hash"],
                )
                for r in rows
            ]

    def verify_baseline_integrity(
        self, baseline_id: int
    ) -> tuple[bool, str | None, str | None]:
        """
        Verifies baseline samples against the stored keyed HMAC seal.
        Only 'hmac-sha256:' seals are accepted (legacy seals are upgraded on open).
        Returns: (is_valid, stored_hash, computed_hash)
        A baseline without samples has nothing to verify and returns (True, stored, None).
        """
        baseline = self.get_baseline(baseline_id)
        if not baseline:
            return False, None, None
        samples = self.get_baseline_samples(baseline_id)
        stored = baseline.integrity_hash
        if not samples:
            return True, stored, None
        computed_hash = compute_samples_hmac(samples)
        if not stored or not stored.startswith(INTEGRITY_HMAC_PREFIX):
            return False, stored, computed_hash
        return hmac.compare_digest(stored, computed_hash), stored, computed_hash

    def list_all_baselines(
        self,
        target_id: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List historical baselines with target details and sample counts.
        Optionally filter by target_id or model name (supports canonical model matching).
        """
        query = """
            SELECT b.id, b.target_id, b.battery_version, b.captured_at, b.status, b.notes, b.integrity_hash,
                   t.model, t.base_url,
                   COUNT(bs.id) AS samples_count
            FROM baselines b
            JOIN targets t ON b.target_id = t.id
            LEFT JOIN baseline_samples bs ON b.id = bs.baseline_id
            WHERE 1=1
        """
        params: list[Any] = []
        if target_id:
            query += " AND b.target_id = ?"
            params.append(target_id)
        if model:
            canonical = canonicalize_model_name(model)
            query += (
                " AND (t.model = ? OR t.model LIKE '%/' || ? OR ? LIKE '%/' || t.model)"
            )
            params.extend([model, canonical, model])
        query += " GROUP BY b.id ORDER BY b.id DESC"

        with self.connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                {
                    "id": r["id"],
                    "target_id": r["target_id"],
                    "model": r["model"],
                    "base_url": r["base_url"],
                    "battery_version": r["battery_version"],
                    "captured_at": r["captured_at"],
                    "status": r["status"],
                    "notes": r["notes"],
                    "integrity_hash": r["integrity_hash"],
                    "samples_count": r["samples_count"],
                }
                for r in rows
            ]

    def get_baseline_samples(self, baseline_id: int) -> list[RawSample]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM baseline_samples WHERE baseline_id = ? ORDER BY id ASC",
                (baseline_id,),
            ).fetchall()
            return [
                RawSample(
                    prompt_id=d["prompt_id"],
                    raw_text=d["raw_text"],
                    latency_ms=d["latency_ms"],
                    fingerprint=d["fingerprint"],
                    model_returned=d["model_returned"],
                    usage=json.loads(d["usage"] or "{}"),
                    headers=json.loads(d["headers"] or "{}"),
                    logprobs=json.loads(d["logprobs"]) if d.get("logprobs") else None,
                    reasoning_content=d.get("reasoning_content"),
                    reasoning_tokens=d.get("reasoning_tokens"),
                    routing_proof=json.loads(d["routing_proof"])
                    if d.get("routing_proof")
                    else None,
                    sampled_at=d["sampled_at"],
                    ttft_ms=d.get("ttft_ms"),
                    max_tokens_sent=d.get("max_tokens_sent"),
                )
                for d in (dict(r) for r in rows)
            ]

    # --- Runs ---
    def create_run(
        self,
        target_id: str,
        baseline_id: int,
        battery_version: str,
        trigger: RunTrigger | str = RunTrigger.MANUAL,
        status: RunStatus | str = RunStatus.RUNNING,
    ) -> int:
        trigger_str = trigger.value if isinstance(trigger, RunTrigger) else str(trigger)
        status_str = status.value if isinstance(status, RunStatus) else str(status)
        with self.connection() as conn:
            now = datetime.now(UTC).isoformat()
            cur = conn.execute(
                """
                INSERT INTO runs (target_id, baseline_id, battery_version, started_at, status, trigger)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (target_id, baseline_id, battery_version, now, status_str, trigger_str),
            )
            return cur.lastrowid

    def save_run_samples(self, run_id: int, samples: list[RawSample]) -> None:
        with self.connection() as conn:
            conn.executemany(
                """
                INSERT INTO run_samples (
                    run_id, prompt_id, raw_text, latency_ms,
                    fingerprint, model_returned, usage, headers, logprobs,
                    reasoning_content, reasoning_tokens, routing_proof, sampled_at, ttft_ms, max_tokens_sent
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        s.prompt_id,
                        s.raw_text,
                        s.latency_ms,
                        s.fingerprint,
                        s.model_returned,
                        json.dumps(s.usage or {}),
                        json.dumps(s.headers or {}),
                        json.dumps(s.logprobs) if s.logprobs else None,
                        s.reasoning_content,
                        s.reasoning_tokens,
                        json.dumps(s.routing_proof) if s.routing_proof else None,
                        s.sampled_at,
                        s.ttft_ms,
                        s.max_tokens_sent,
                    )
                    for s in samples
                ],
            )

    def finish_run(
        self, run_id: int, status: RunStatus | str = RunStatus.COMPLETED
    ) -> None:
        status_str = status.value if isinstance(status, RunStatus) else str(status)
        with self.connection() as conn:
            now = datetime.now(UTC).isoformat()
            conn.execute(
                "UPDATE runs SET finished_at = ?, status = ? WHERE id = ?",
                (now, status_str, run_id),
            )

    def cleanup_stale_runs(self) -> int:
        """Mark any runs left in 'running' status (e.g. after crash or server restart) as failed."""
        with self.connection() as conn:
            now = datetime.now(UTC).isoformat()
            cur = conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE status = ?",
                (RunStatus.FAILED.value, now, RunStatus.RUNNING.value),
            )
            return cur.rowcount

    def get_run(self, run_id: int) -> Run | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return None
            return Run(
                id=row["id"],
                target_id=row["target_id"],
                baseline_id=row["baseline_id"],
                battery_version=row["battery_version"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                status=_parse_run_status(row["status"]),
                trigger=_parse_run_trigger(row["trigger"]),
            )

    def get_latest_run(self, target_id: str) -> Run | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE target_id = ? ORDER BY id DESC LIMIT 1",
                (target_id,),
            ).fetchone()
            if not row:
                return None
            return Run(
                id=row["id"],
                target_id=row["target_id"],
                baseline_id=row["baseline_id"],
                battery_version=row["battery_version"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                status=_parse_run_status(row["status"]),
                trigger=_parse_run_trigger(row["trigger"]),
            )

    def list_runs(self, target_id: str | None = None, limit: int = 20) -> list[Run]:
        with self.connection() as conn:
            if target_id:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE target_id = ? ORDER BY id DESC LIMIT ?",
                    (target_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                Run(
                    id=r["id"],
                    target_id=r["target_id"],
                    baseline_id=r["baseline_id"],
                    battery_version=r["battery_version"],
                    started_at=r["started_at"],
                    finished_at=r["finished_at"],
                    status=_parse_run_status(r["status"]),
                    trigger=_parse_run_trigger(r["trigger"]),
                )
                for r in rows
            ]

    def count_consecutive_failures(self, target_id: str) -> int:
        """
        Returns the number of consecutive non-PASS completed runs (FAIL or WARN) for this target,
        evaluating backwards from the most recent completed run.
        """
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT r.id,
                    CASE
                        WHEN EXISTS (SELECT 1 FROM scores WHERE run_id = r.id AND verdict = 'FAIL') THEN 'FAIL'
                        WHEN EXISTS (SELECT 1 FROM scores WHERE run_id = r.id AND verdict = 'WARN') THEN 'WARN'
                        WHEN EXISTS (SELECT 1 FROM scores WHERE run_id = r.id AND verdict = 'PASS' AND method != 'infrastructure') THEN 'PASS'
                        ELSE COALESCE(
                            (SELECT verdict FROM scores WHERE run_id = r.id AND scope = 'overall' LIMIT 1),
                            'SKIP'
                        )
                    END as overall_verdict
                FROM runs r
                WHERE r.target_id = ? AND r.status = 'completed'
                ORDER BY r.id DESC
                LIMIT 50
                """,
                (target_id,),
            ).fetchall()
            streak = 0
            for r in rows:
                verdict = r["overall_verdict"]
                if verdict in ("FAIL", "WARN"):
                    streak += 1
                elif verdict == "PASS":
                    break
            return streak

    def get_run_samples(self, run_id: int) -> list[RawSample]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM run_samples WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
            return [
                RawSample(
                    prompt_id=d["prompt_id"],
                    raw_text=d["raw_text"],
                    latency_ms=d["latency_ms"],
                    fingerprint=d["fingerprint"],
                    model_returned=d["model_returned"],
                    usage=json.loads(d["usage"] or "{}"),
                    headers=json.loads(d["headers"] or "{}"),
                    logprobs=json.loads(d["logprobs"]) if d.get("logprobs") else None,
                    reasoning_content=d.get("reasoning_content"),
                    reasoning_tokens=d.get("reasoning_tokens"),
                    routing_proof=json.loads(d["routing_proof"])
                    if d.get("routing_proof")
                    else None,
                    sampled_at=d["sampled_at"],
                    ttft_ms=d.get("ttft_ms"),
                    max_tokens_sent=d.get("max_tokens_sent"),
                )
                for d in (dict(r) for r in rows)
            ]

    # --- Scores ---
    def save_scores(self, scores: list[Score]) -> None:
        with self.connection() as conn:
            conn.executemany(
                """
                INSERT INTO scores (run_id, method, scope, value, threshold, verdict, details, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        s.run_id,
                        s.method,
                        s.scope,
                        s.value,
                        s.threshold,
                        s.verdict.value,
                        json.dumps(s.details),
                        s.computed_at,
                    )
                    for s in scores
                ],
            )

    def get_scores(self, run_id: int) -> list[Score]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM scores WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
            return [
                Score(
                    id=r["id"],
                    run_id=r["run_id"],
                    method=r["method"],
                    scope=r["scope"],
                    value=r["value"],
                    threshold=r["threshold"],
                    verdict=Verdict(r["verdict"]),
                    details=json.loads(r["details"] or "{}"),
                    computed_at=r["computed_at"],
                )
                for r in rows
            ]

    # --- Schedules ---
    def create_or_update_schedule(
        self,
        target_id: str,
        interval_hours: int = 24,
        battery: str = "quick",
        enabled: bool = True,
    ) -> int:
        with self.connection() as conn:
            now = datetime.now(UTC)
            next_run = (now + timedelta(hours=interval_hours)).isoformat()
            now_iso = now.isoformat()
            cur = conn.execute(
                """
                INSERT INTO schedules (target_id, interval_hours, battery, enabled, last_run_at, next_run_at, created_at)
                VALUES (?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(target_id) DO UPDATE SET
                    interval_hours = excluded.interval_hours,
                    battery = excluded.battery,
                    enabled = excluded.enabled,
                    next_run_at = excluded.next_run_at
                """,
                (
                    target_id,
                    interval_hours,
                    battery,
                    1 if enabled else 0,
                    next_run,
                    now_iso,
                ),
            )
            if cur.lastrowid:
                return cur.lastrowid
            row = conn.execute(
                "SELECT id FROM schedules WHERE target_id = ?", (target_id,)
            ).fetchone()
            return row["id"] if row else 0

    def list_schedules(self) -> list[Schedule]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM schedules ORDER BY id ASC").fetchall()
            return [
                Schedule(
                    id=r["id"],
                    target_id=r["target_id"],
                    interval_hours=r["interval_hours"],
                    battery=r["battery"],
                    enabled=bool(r["enabled"]),
                    last_run_at=r["last_run_at"],
                    next_run_at=r["next_run_at"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def get_schedule(self, schedule_id: int) -> Schedule | None:
        with self.connection() as conn:
            r = conn.execute(
                "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
            if not r:
                return None
            return Schedule(
                id=r["id"],
                target_id=r["target_id"],
                interval_hours=r["interval_hours"],
                battery=r["battery"],
                enabled=bool(r["enabled"]),
                last_run_at=r["last_run_at"],
                next_run_at=r["next_run_at"],
                created_at=r["created_at"],
            )

    def get_schedule_for_target(self, target_id: str) -> Schedule | None:
        with self.connection() as conn:
            r = conn.execute(
                "SELECT * FROM schedules WHERE target_id = ?", (target_id,)
            ).fetchone()
            if not r:
                return None
            return Schedule(
                id=r["id"],
                target_id=r["target_id"],
                interval_hours=r["interval_hours"],
                battery=r["battery"],
                enabled=bool(r["enabled"]),
                last_run_at=r["last_run_at"],
                next_run_at=r["next_run_at"],
                created_at=r["created_at"],
            )

    def get_due_schedules(self) -> list[Schedule]:
        with self.connection() as conn:
            now_iso = datetime.now(UTC).isoformat()
            rows = conn.execute(
                """
                SELECT * FROM schedules
                WHERE enabled = 1 AND (next_run_at IS NULL OR next_run_at <= ?)
                ORDER BY id ASC
                """,
                (now_iso,),
            ).fetchall()
            return [
                Schedule(
                    id=r["id"],
                    target_id=r["target_id"],
                    interval_hours=r["interval_hours"],
                    battery=r["battery"],
                    enabled=bool(r["enabled"]),
                    last_run_at=r["last_run_at"],
                    next_run_at=r["next_run_at"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def delete_schedule(self, schedule_id: int) -> bool:
        with self.connection() as conn:
            cur = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            return cur.rowcount > 0

    def record_schedule_tick(
        self, schedule_id: int, interval_hours: int | None = None
    ) -> None:
        with self.connection() as conn:
            now = datetime.now(UTC)
            now_iso = now.isoformat()
            if interval_hours is None:
                r = conn.execute(
                    "SELECT interval_hours FROM schedules WHERE id = ?", (schedule_id,)
                ).fetchone()
                interval_hours = r["interval_hours"] if r else 24
            next_run = (now + timedelta(hours=interval_hours)).isoformat()
            conn.execute(
                "UPDATE schedules SET last_run_at = ?, next_run_at = ? WHERE id = ?",
                (now_iso, next_run, schedule_id),
            )

    # --- Run Report Assembly ---
    def get_run_report(
        self, run_id: int, cost_per_million: float = 5.0, locale: str = "ru"
    ) -> RunReport | None:
        """
        Assembles a comprehensive domain RunReport entity encapsulating run details,
        target info, baseline info, scores, overall verdict, and cost metrics.
        """
        run = self.get_run(run_id)
        if not run:
            return None

        target = self.get_target(run.target_id) or Target(
            id=run.target_id, base_url="—", model="—"
        )
        baseline = self.get_baseline(run.baseline_id) or Baseline(
            id=run.baseline_id,
            target_id=run.target_id,
            battery_version=run.battery_version,
            captured_at="—",
        )
        scores = self.get_scores(run_id)
        samples = self.get_run_samples(run_id)
        overall = Verdict.aggregate(scores)

        total_tokens = sum(
            (s.usage.get("total_tokens", 0) if s.usage else (len(s.raw_text) // 3))
            for s in samples
        )
        est_cost = calculate_token_cost(total_tokens, cost_per_million)

        from attest.i18n import (
            build_pipeline_summary_message,
            format_failure_diagnostics,
        )

        diagnostics = format_failure_diagnostics(scores, locale=locale)
        summary_msg = build_pipeline_summary_message(
            overall, diagnostics, locale=locale
        )

        return RunReport(
            run=run,
            target=target,
            baseline=baseline,
            scores=scores,
            samples_count=len(samples),
            total_tokens=total_tokens,
            estimated_cost_usd=est_cost,
            overall_verdict=overall,
            summary_message=summary_msg,
            failure_diagnostics=diagnostics,
        )

    # --- Background Tasks (Multi-worker persistent state) ---
    def create_task(
        self, task_id: str, target_id: str, task_type: str, total: int = 0
    ) -> dict[str, Any]:
        """Registers a background task in the persistent database."""
        now = time.time()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks (id, target_id, type, status, total, completed, result, error, started_at, updated_at)
                VALUES (?, ?, ?, 'running', ?, 0, NULL, NULL, ?, ?)
                """,
                (task_id, target_id, task_type, total, now, now),
            )
        return {
            "task_id": task_id,
            "target_id": target_id,
            "type": task_type,
            "status": "running",
            "started_at": now,
            "total": total,
            "completed": 0,
            "result": None,
            "error": None,
        }

    def update_task_progress(
        self, task_id: str, completed: int, total: int | None = None
    ) -> None:
        """Updates task progress counter and timestamp."""
        now = time.time()
        with self.connection() as conn:
            if total is not None:
                conn.execute(
                    "UPDATE tasks SET completed = ?, total = ?, updated_at = ? WHERE id = ?",
                    (completed, total, now, task_id),
                )
            else:
                conn.execute(
                    "UPDATE tasks SET completed = ?, updated_at = ? WHERE id = ?",
                    (completed, now, task_id),
                )

    def complete_task(self, task_id: str, result: dict[str, Any] | None = None) -> None:
        """Marks a background task as completed with an optional serialized result."""
        now = time.time()
        res_json = json.dumps(result) if result is not None else None
        with self.connection() as conn:
            conn.execute(
                "UPDATE tasks SET status = 'completed', result = ?, updated_at = ? WHERE id = ?",
                (res_json, now, task_id),
            )

    def fail_task(self, task_id: str, error: str) -> None:
        """Marks a background task as failed with an error message."""
        now = time.time()
        with self.connection() as conn:
            conn.execute(
                "UPDATE tasks SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                (str(error), now, task_id),
            )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Retrieves task state by ID across any process or worker."""
        with self.connection() as conn:
            r = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not r:
                return None
            res_val = None
            if r["result"]:
                try:
                    res_val = json.loads(r["result"])
                except (json.JSONDecodeError, TypeError):
                    res_val = r["result"]
            return {
                "task_id": r["id"],
                "target_id": r["target_id"],
                "type": r["type"],
                "status": r["status"],
                "total": r["total"],
                "completed": r["completed"],
                "result": res_val,
                "error": r["error"],
                "started_at": r["started_at"],
                "updated_at": r["updated_at"],
            }

    def cleanup_old_tasks(self, max_age_seconds: float = 86400.0) -> int:
        """Evicts terminal tasks older than max_age_seconds."""
        cutoff = time.time() - max_age_seconds
        with self.connection() as conn:
            cur = conn.execute(
                "DELETE FROM tasks WHERE status IN ('completed', 'failed') AND updated_at < ?",
                (cutoff,),
            )
            return cur.rowcount

    def get_system_stats(self, limit_runs: int = 100) -> dict[str, int]:
        """
        Calculates aggregated system telemetry (total targets, active baselines,
        total audits, passes, warnings, failures) in a single fast query.
        """
        with self.connection() as conn:
            t_row = conn.execute("SELECT COUNT(*) as c FROM targets").fetchone()
            total_targets = t_row["c"] if t_row else 0

            b_row = conn.execute(
                """
                SELECT COUNT(DISTINCT t.id) as c
                FROM targets t
                JOIN targets t2 ON t.model = t2.model
                JOIN baselines b ON b.target_id = t2.id
                WHERE b.status = 'active'
                """
            ).fetchone()
            active_baselines = b_row["c"] if b_row else 0

            runs_query = """
            WITH recent_runs AS (
                SELECT id FROM runs ORDER BY id DESC LIMIT ?
            ),
            run_verdicts AS (
                SELECT 
                    r.id,
                    CASE 
                        WHEN SUM(CASE WHEN UPPER(s.verdict) = 'FAIL' AND s.method NOT IN ('infrastructure', 'infrastructure_probe') THEN 1 ELSE 0 END) > 0 THEN 'FAIL'
                        WHEN SUM(CASE WHEN UPPER(s.verdict) = 'WARN' AND s.method NOT IN ('infrastructure', 'infrastructure_probe') THEN 1 ELSE 0 END) > 0 THEN 'WARN'
                        WHEN SUM(CASE WHEN UPPER(s.verdict) = 'PASS' AND s.method NOT IN ('infrastructure', 'infrastructure_probe') THEN 1 ELSE 0 END) > 0 THEN 'PASS'
                        ELSE 'SKIP'
                    END as verdict
                FROM recent_runs rr
                JOIN runs r ON r.id = rr.id
                LEFT JOIN scores s ON s.run_id = r.id
                GROUP BY r.id
            )
            SELECT 
                COUNT(*) as total_audits,
                COALESCE(SUM(CASE WHEN verdict = 'PASS' THEN 1 ELSE 0 END), 0) as passes,
                COALESCE(SUM(CASE WHEN verdict = 'WARN' THEN 1 ELSE 0 END), 0) as warnings,
                COALESCE(SUM(CASE WHEN verdict = 'FAIL' THEN 1 ELSE 0 END), 0) as failures
            FROM run_verdicts
            """
            r_row = conn.execute(runs_query, (limit_runs,)).fetchone()
            total_audits = r_row["total_audits"] if r_row else 0
            passes = r_row["passes"] if r_row else 0
            warnings = r_row["warnings"] if r_row else 0
            failures = r_row["failures"] if r_row else 0

            return {
                "total_targets": total_targets,
                "active_baselines": active_baselines,
                "total_audits": total_audits,
                "passes": passes,
                "warnings": warnings,
                "failures": failures,
            }

    # --- Custom Providers ---

    def _ensure_custom_providers_table(self, conn: sqlite3.Connection) -> None:
        """Create custom_providers table if it doesn't exist (lazy migration)."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_providers (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                base_url    TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                model_prefix TEXT NOT NULL DEFAULT '',
                encrypted_key TEXT,
                created_at  TEXT NOT NULL
            );
        """)

    def get_custom_providers(self) -> list[dict]:
        """Return all user-saved custom providers as dicts compatible with ProviderSpec.to_dict()."""
        with self.connection() as conn:
            self._ensure_custom_providers_table(conn)
            rows = conn.execute(
                "SELECT id, name, base_url, description, model_prefix FROM custom_providers ORDER BY created_at"
            ).fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "base_url": row["base_url"],
                    "description": row["description"],
                    "model_prefix": row["model_prefix"],
                    "is_trusted_reference": False,
                    "popular_models": [],
                    "docs_url": "",
                    "env_key": {"has_key": False, "preview": "", "source": ""},
                }
            )
        return result

    def save_custom_provider(
        self,
        provider_id: str,
        name: str,
        base_url: str,
        description: str = "",
        model_prefix: str = "",
        encrypted_key: str | None = None,
    ) -> None:
        """Insert or update a user-defined custom provider."""
        now = datetime.now(UTC).isoformat()
        with self.connection() as conn:
            self._ensure_custom_providers_table(conn)
            conn.execute(
                """
                INSERT INTO custom_providers (id, name, base_url, description, model_prefix, encrypted_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    base_url = excluded.base_url,
                    description = excluded.description,
                    model_prefix = excluded.model_prefix,
                    encrypted_key = COALESCE(excluded.encrypted_key, custom_providers.encrypted_key)
                """,
                (
                    provider_id,
                    name,
                    base_url,
                    description,
                    model_prefix,
                    encrypted_key,
                    now,
                ),
            )

    def delete_custom_provider(self, provider_id: str) -> None:
        """Delete a user-defined custom provider by ID."""
        with self.connection() as conn:
            self._ensure_custom_providers_table(conn)
            conn.execute("DELETE FROM custom_providers WHERE id = ?", (provider_id,))
