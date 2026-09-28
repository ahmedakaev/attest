"""
Database schema definition and versioned migrations for Attest.
Zero ORM, lightweight, fast, WAL-enabled.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version         INTEGER PRIMARY KEY,
    applied_at      TEXT NOT NULL,
    description     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
    id              TEXT PRIMARY KEY,
    base_url        TEXT NOT NULL,
    model           TEXT NOT NULL,
    encrypted_key   TEXT,
    description     TEXT,
    extra_headers   TEXT,
    wire_model      TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    text            TEXT NOT NULL,
    params          TEXT NOT NULL,
    samples_count   INTEGER NOT NULL DEFAULT 1,
    battery_version TEXT NOT NULL,
    assertions      TEXT,
    messages        TEXT,
    UNIQUE(text, category, battery_version)
);

CREATE TABLE IF NOT EXISTS baselines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id       TEXT NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    battery_version TEXT NOT NULL,
    captured_at     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    notes           TEXT,
    integrity_hash  TEXT
);

CREATE TABLE IF NOT EXISTS baseline_samples (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    baseline_id         INTEGER NOT NULL REFERENCES baselines(id) ON DELETE CASCADE,
    prompt_id           INTEGER NOT NULL REFERENCES prompts(id),
    raw_text            TEXT NOT NULL,
    latency_ms          INTEGER,
    fingerprint         TEXT,
    model_returned      TEXT,
    usage               TEXT,
    headers             TEXT,
    logprobs            TEXT,
    reasoning_content   TEXT,
    reasoning_tokens    INTEGER,
    routing_proof       TEXT,
    sampled_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id       TEXT NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    baseline_id     INTEGER NOT NULL REFERENCES baselines(id),
    battery_version TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    trigger         TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS run_samples (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    prompt_id           INTEGER NOT NULL REFERENCES prompts(id),
    raw_text            TEXT NOT NULL,
    latency_ms          INTEGER,
    fingerprint         TEXT,
    model_returned      TEXT,
    usage               TEXT,
    headers             TEXT,
    logprobs            TEXT,
    reasoning_content   TEXT,
    reasoning_tokens    INTEGER,
    routing_proof       TEXT,
    sampled_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    method          TEXT NOT NULL,
    scope           TEXT NOT NULL,
    value           REAL NOT NULL,
    threshold       REAL,
    verdict         TEXT NOT NULL,
    details         TEXT,
    computed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    score_id        INTEGER REFERENCES scores(id),
    severity        TEXT NOT NULL,
    message         TEXT NOT NULL,
    acknowledged    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schedules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id       TEXT NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    interval_hours  INTEGER NOT NULL DEFAULT 24,
    battery         TEXT NOT NULL DEFAULT 'quick',
    enabled         INTEGER NOT NULL DEFAULT 1,
    last_run_at     TEXT,
    next_run_at     TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(target_id)
);

CREATE INDEX IF NOT EXISTS idx_baseline_samples_baseline ON baseline_samples(baseline_id);
CREATE INDEX IF NOT EXISTS idx_run_samples_run ON run_samples(run_id);
CREATE INDEX IF NOT EXISTS idx_scores_run ON scores(run_id);
CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(enabled, next_run_at);
"""


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check whether a column exists in a given table."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = [r["name"] if isinstance(r, sqlite3.Row) else r[1] for r in cur.fetchall()]
    return column in cols


MIGRATIONS: list[tuple[int, str, list[tuple[str, str, str]]]] = [
    (
        2,
        "add_sample_logprobs_and_reasoning",
        [
            ("baseline_samples", "logprobs", "TEXT"),
            ("baseline_samples", "reasoning_content", "TEXT"),
            ("baseline_samples", "reasoning_tokens", "INTEGER"),
            ("run_samples", "logprobs", "TEXT"),
            ("run_samples", "reasoning_content", "TEXT"),
            ("run_samples", "reasoning_tokens", "INTEGER"),
        ],
    ),
    (
        3,
        "add_prompt_assertions_and_messages",
        [
            ("prompts", "assertions", "TEXT"),
            ("prompts", "messages", "TEXT"),
        ],
    ),
    (
        4,
        "add_target_wire_model",
        [
            ("targets", "wire_model", "TEXT"),
        ],
    ),
    (
        5,
        "add_baseline_integrity_hash",
        [
            ("baselines", "integrity_hash", "TEXT"),
        ],
    ),
    (
        7,
        "add_routing_proof_columns",
        [
            ("baseline_samples", "routing_proof", "TEXT"),
            ("run_samples", "routing_proof", "TEXT"),
        ],
    ),
    (
        8,
        "add_sample_ttft",
        [
            ("baseline_samples", "ttft_ms", "INTEGER"),
            ("run_samples", "ttft_ms", "INTEGER"),
        ],
    ),
    (
        9,
        "add_sample_max_tokens_sent",
        [
            ("baseline_samples", "max_tokens_sent", "INTEGER"),
            ("run_samples", "max_tokens_sent", "INTEGER"),
        ],
    ),
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    """
    Executes versioned schema migrations sequentially, tracking applied revisions
    in the schema_migrations table.
    """
    applied_rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    applied_versions = {
        r["version"] if isinstance(r, sqlite3.Row) else r[0] for r in applied_rows
    }

    now_iso = datetime.now(UTC).isoformat()
    if 1 not in applied_versions:
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
            (1, now_iso, "initial_core_schema"),
        )
        applied_versions.add(1)

    for version, desc, col_specs in MIGRATIONS:
        if version not in applied_versions:
            for table, col, col_type in col_specs:
                if not has_column(conn, table, col):
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};")
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (version, now_iso, desc),
            )
            applied_versions.add(version)

    # Migration 6: tasks table
    if 6 not in applied_versions:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id              TEXT PRIMARY KEY,
            target_id       TEXT NOT NULL,
            type            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'running',
            total           INTEGER NOT NULL DEFAULT 0,
            completed       INTEGER NOT NULL DEFAULT 0,
            result          TEXT,
            error           TEXT,
            started_at      REAL NOT NULL,
            updated_at      REAL NOT NULL
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
            (6, now_iso, "add_tasks_table"),
        )
        applied_versions.add(6)


def init_database(conn: sqlite3.Connection) -> None:
    """Initialize base schema, enable WAL, and apply pending migrations."""
    conn.executescript(SCHEMA_SQL)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    apply_migrations(conn)
