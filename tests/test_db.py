from pathlib import Path

from attest.db import Database
from attest.models import PromptItem, RawSample, Score, Target, Verdict


def test_database_lifecycle(tmp_path):
    db_file = tmp_path / "test_attest.db"
    db = Database(db_file)

    # 1. Target
    target = Target(
        id="unit-test-target",
        base_url="https://api.test.com/v1",
        model="gpt-4o",
        encrypted_key="gAAAAAB...",
        description="Target for unit testing",
    )
    db.save_target(target)
    loaded = db.get_target("unit-test-target")
    assert loaded is not None
    assert loaded.model == "gpt-4o"

    # 2. Prompts
    prompts = [
        PromptItem(
            id=None,
            category="one_token",
            text="Name random digit",
            params={"max_tokens": 5},
            samples_count=10,
            battery_version="v1",
        )
    ]
    synced = db.sync_prompts(prompts, "v1")
    assert len(synced) == 1
    assert synced[0].id is not None

    # 3. Baseline
    b_id = db.create_baseline(
        target_id=target.id, battery_version="v1", notes="Init baseline"
    )
    active_b = db.get_active_baseline(target.id)
    assert active_b is not None
    assert active_b.id == b_id

    samples = [
        RawSample(
            prompt_id=synced[0].id,
            raw_text="7",
            latency_ms=120,
            fingerprint="fp_test",
            model_returned="gpt-4o",
            usage={"total_tokens": 10},
            headers={"server": "test"},
        )
    ]
    db.save_baseline_samples(b_id, samples)
    b_samples = db.get_baseline_samples(b_id)
    assert len(b_samples) == 1
    assert b_samples[0].raw_text == "7"

    # 4. Run & Scores
    run_id = db.create_run(target_id=target.id, baseline_id=b_id, battery_version="v1")
    db.save_run_samples(run_id, samples)
    score = Score(
        id=None,
        run_id=run_id,
        method="jsd",
        scope="aggregate",
        value=0.01,
        threshold=0.15,
        verdict=Verdict.PASS,
        details={"mean_jsd": 0.01},
    )
    db.save_scores([score])
    db.finish_run(run_id)

    scores = db.get_scores(run_id)
    assert len(scores) == 1
    assert scores[0].verdict == Verdict.PASS


def test_database_logprobs_and_stale_cleanup(tmp_path):
    db_file = tmp_path / "test_logprobs.db"
    db = Database(db_file)

    target = Target(id="t1", base_url="https://api.openai.com/v1", model="gpt-4o")
    db.save_target(target)
    b_id = db.create_baseline("t1", "v1")

    prompts = [
        PromptItem(
            id=None,
            category="one_token",
            text="Pick a digit",
            params={"max_tokens": 1},
            samples_count=1,
            battery_version="v1",
        )
    ]
    synced = db.sync_prompts(prompts, "v1")
    assert synced[0].id is not None
    p_id = synced[0].id

    # Sample with logprobs and default headers
    sample = RawSample(
        prompt_id=p_id,
        raw_text="42",
        latency_ms=100,
        logprobs={"42": -0.05, "7": -3.2},
    )
    assert sample.headers == {}
    assert sample.logprobs is not None

    db.save_baseline_samples(b_id, [sample])
    retrieved_base = db.get_baseline_samples(b_id)
    assert len(retrieved_base) == 1
    assert retrieved_base[0].logprobs == {"42": -0.05, "7": -3.2}

    # Run with logprobs
    run_id = db.create_run("t1", b_id, "v1")
    db.save_run_samples(run_id, [sample])
    retrieved_run = db.get_run_samples(run_id)
    assert len(retrieved_run) == 1
    assert retrieved_run[0].logprobs == {"42": -0.05, "7": -3.2}

    # Verify run is currently 'running'
    run_obj = db.get_run(run_id)
    assert run_obj.status == "running"

    # Simulate server crash/restart cleanup
    cleaned = db.cleanup_stale_runs()
    assert cleaned == 1

    run_obj_after = db.get_run(run_id)
    assert run_obj_after.status == "failed"
    assert run_obj_after.finished_at is not None


def test_cross_provider_baseline_resolution(tmp_path):
    db_file = tmp_path / "test_cross.db"
    db = Database(db_file)

    # Official target with model gpt-5.5
    official = Target(
        id="official-openai",
        base_url="https://api.openai.com/v1",
        model="gpt-5.5",
    )
    # Third party reseller with the same model gpt-5.5
    reseller = Target(
        id="reseller-gateway",
        base_url="https://api.gateway-example.com/v1",
        model="gpt-5.5",
    )
    # Another model target
    claude_target = Target(
        id="anthropic-claude",
        base_url="https://api.anthropic.com/v1",
        model="claude-fable-5-1",
    )
    db.save_target(official)
    db.save_target(reseller)
    db.save_target(claude_target)

    # 1. Before any baselines
    b, src = db.resolve_target_baseline("reseller-gateway")
    assert b is None
    assert src == "missing"

    # 2. Capture baseline on official-openai
    b_id = db.create_baseline("official-openai", "v1", notes="Official Gold Baseline")

    # 3. Reseller automatically resolves to the official baseline for gpt-5.5
    b_reseller, src_reseller = db.resolve_target_baseline("reseller-gateway")
    assert b_reseller is not None
    assert b_reseller.id == b_id
    assert "model 'gpt-5.5'" in src_reseller
    assert "official-openai" in src_reseller

    # 4. Explicit --against resolution
    b_explicit, _ = db.resolve_target_baseline(
        "reseller-gateway", against_target_or_model="official-openai"
    )
    assert b_explicit.id == b_id

    # 5. Claude target does not match gpt-5.5 baseline
    b_claude, src_claude = db.resolve_target_baseline("anthropic-claude")
    assert b_claude is None
    assert src_claude == "missing"

    # 6. Aggregator/proxy with namespaced model call e.g. OpenRouter ("openai/gpt-5.5")
    openrouter = Target(
        id="reseller-openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-5.5",
    )
    db.save_target(openrouter)

    # Automatically resolves to official-openai baseline for canonical "gpt-5.5"
    b_or, src_or = db.resolve_target_baseline("reseller-openrouter")
    assert b_or is not None
    assert b_or.id == b_id
    assert "official-openai" in src_or

    # Explicit resolution via namespaced model parameter also works
    b_or_exp, _ = db.resolve_target_baseline(
        "reseller-openrouter", against_target_or_model="openai/gpt-5.5"
    )
    assert b_or_exp is not None
    assert b_or_exp.id == b_id


def test_list_all_baselines_and_superseded_status(tmp_path):
    db_file = tmp_path / "test_history.db"
    db = Database(db_file)

    target = Target(
        id="official-gpt5", base_url="https://api.openai.com/v1", model="gpt-5.5"
    )
    db.save_target(target)

    # First baseline
    b1_id = db.create_baseline("official-gpt5", "v1", notes="Initial capture")
    b1 = db.get_baseline(b1_id)
    assert b1 is not None
    assert b1.status == "active"

    # Second baseline supersedes first
    b2_id = db.create_baseline("official-gpt5", "v1", notes="Updated weights")
    b1_after = db.get_baseline(b1_id)
    b2 = db.get_baseline(b2_id)
    assert b1_after.status == "superseded"
    assert b2.status == "active"

    # Query all baselines
    all_b = db.list_all_baselines()
    assert len(all_b) == 2
    assert all_b[0]["id"] == b2_id
    assert all_b[0]["status"] == "active"
    assert all_b[1]["id"] == b1_id
    assert all_b[1]["status"] == "superseded"

    # Filter by model
    model_b = db.list_all_baselines(model="gpt-5.5")
    assert len(model_b) == 2


def test_baseline_integrity_verification_and_anti_tampering(tmp_path):
    db_file = tmp_path / "test_integrity.db"
    db = Database(db_file)

    target = Target(
        id="tgt-integrity", base_url="https://api.openai.com/v1", model="gpt-5.5"
    )
    db.save_target(target)

    prompts = [
        PromptItem(
            id=None,
            category="cat1",
            text="q1",
            params={},
            samples_count=1,
            battery_version="v1",
        )
    ]
    synced = db.sync_prompts(prompts, "v1")
    p_id = synced[0].id

    b_id = db.create_baseline("tgt-integrity", "v1", notes="Integrity test")
    samples = [
        RawSample(
            prompt_id=p_id,
            raw_text="response 1",
            latency_ms=100,
            fingerprint="fp_abc",
            model_returned="gpt-5.5",
        ),
        RawSample(
            prompt_id=p_id,
            raw_text="response 2",
            latency_ms=120,
            fingerprint="fp_abc",
            model_returned="gpt-5.5",
        ),
    ]
    db.save_baseline_samples(b_id, samples)

    b = db.get_baseline(b_id)
    assert b is not None
    assert b.integrity_hash is not None
    assert b.integrity_hash.startswith("hmac-sha256:")
    assert len(b.integrity_hash) == len("hmac-sha256:") + 64

    # 1. Verification succeeds on valid untouched data
    is_valid, stored, computed = db.verify_baseline_integrity(b_id)
    assert is_valid is True
    assert stored == b.integrity_hash
    assert computed == b.integrity_hash

    # 2. Tamper with a sample row directly in SQLite
    with db.connection() as conn:
        conn.execute(
            "UPDATE baseline_samples SET raw_text = 'tampered spoofed text' WHERE baseline_id = ? AND raw_text = 'response 1'",
            (b_id,),
        )

    # 3. Verification must fail and report discrepancy
    is_valid_after, stored_after, comp_after = db.verify_baseline_integrity(b_id)
    assert is_valid_after is False
    assert stored_after == b.integrity_hash
    assert comp_after != stored_after


def test_target_wire_model_persistence(tmp_path):
    db_file = tmp_path / "test_wire.db"
    db = Database(db_file)

    # Target with explicit wire model
    target = Target(
        id="openrouter-candidate",
        base_url="https://openrouter.ai/api/v1",
        model="gpt-5.5",
        wire_model="openai/gpt-5.5",
        description="Reseller endpoint",
    )
    db.save_target(target)

    loaded = db.get_target("openrouter-candidate")
    assert loaded is not None
    assert loaded.model == "gpt-5.5"
    assert loaded.wire_model == "openai/gpt-5.5"

    targets = db.list_targets()
    assert any(
        t.id == "openrouter-candidate" and t.wire_model == "openai/gpt-5.5"
        for t in targets
    )


def test_count_consecutive_failures(tmp_path):
    db_file = tmp_path / "test_streak.db"
    db = Database(db_file)

    target = Target(
        id="streak-tgt", base_url="https://api.openai.com/v1", model="gpt-5.5"
    )
    db.save_target(target)

    b_id = db.create_baseline("streak-tgt", "v1")

    assert db.count_consecutive_failures("streak-tgt") == 0

    # Run 1: PASS
    r1 = db.create_run("streak-tgt", b_id, "v1")
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r1,
                method="jsd",
                scope="overall",
                value=0.01,
                threshold=0.15,
                verdict=Verdict.PASS,
            )
        ]
    )
    db.finish_run(r1, "completed")
    assert db.count_consecutive_failures("streak-tgt") == 0

    # Run 2: FAIL
    r2 = db.create_run("streak-tgt", b_id, "v1")
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r2,
                method="jsd",
                scope="overall",
                value=0.45,
                threshold=0.15,
                verdict=Verdict.FAIL,
            )
        ]
    )
    db.finish_run(r2, "completed")
    assert db.count_consecutive_failures("streak-tgt") == 1

    # Run 3: WARN
    r3 = db.create_run("streak-tgt", b_id, "v1")
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r3,
                method="jsd",
                scope="overall",
                value=0.25,
                threshold=0.15,
                verdict=Verdict.WARN,
            )
        ]
    )
    db.finish_run(r3, "completed")
    assert db.count_consecutive_failures("streak-tgt") == 2

    # Run 4: PASS breaks streak
    r4 = db.create_run("streak-tgt", b_id, "v1")
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r4,
                method="jsd",
                scope="overall",
                value=0.02,
                threshold=0.15,
                verdict=Verdict.PASS,
            )
        ]
    )
    db.finish_run(r4, "completed")
    assert db.count_consecutive_failures("streak-tgt") == 0


def test_count_consecutive_failures_realistic_scores(tmp_path: Path):
    """
    Verifies that count_consecutive_failures properly evaluates real production runs
    where scores have scopes like 'aggregate' and 'prompt' (no synthetic 'overall' scope).
    """
    db_file = tmp_path / "test_streak_real.db"
    db = Database(db_file)
    target = Target(id="real-tgt", base_url="https://api.openai.com/v1", model="gpt-4o")
    db.save_target(target)
    b_id = db.create_baseline("real-tgt", "v1")

    # Run 1: completed with aggregate PASS and prompt PASS
    r1 = db.create_run("real-tgt", b_id, "v1")
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r1,
                method="jsd",
                scope="aggregate",
                value=0.04,
                threshold=0.15,
                verdict=Verdict.PASS,
            ),
            Score(
                id=None,
                run_id=r1,
                method="latency_tps",
                scope="aggregate",
                value=0.10,
                threshold=1.0,
                verdict=Verdict.PASS,
            ),
        ]
    )
    db.finish_run(r1, "completed")
    assert db.count_consecutive_failures("real-tgt") == 0

    # Run 2: completed with one prompt failing -> run overall is FAIL
    r2 = db.create_run("real-tgt", b_id, "v1")
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r2,
                method="quick_model",
                scope="global",
                value=1.0,
                threshold=1.0,
                verdict=Verdict.PASS,
            ),
            Score(
                id=None,
                run_id=r2,
                method="jsd",
                scope="aggregate",
                value=0.42,
                threshold=0.15,
                verdict=Verdict.FAIL,
            ),
        ]
    )
    db.finish_run(r2, "completed")
    assert db.count_consecutive_failures("real-tgt") == 1

    # Run 3: completed with WARN -> streak increments to 2
    r3 = db.create_run("real-tgt", b_id, "v1")
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r3,
                method="jsd",
                scope="aggregate",
                value=0.05,
                threshold=0.15,
                verdict=Verdict.PASS,
            ),
            Score(
                id=None,
                run_id=r3,
                method="latency_drift",
                scope="aggregate",
                value=0.85,
                threshold=1.20,
                verdict=Verdict.WARN,
            ),
        ]
    )
    db.finish_run(r3, "completed")
    assert db.count_consecutive_failures("real-tgt") == 2


def test_schema_migrations_tracking(tmp_path: Path):
    db_file = tmp_path / "test_migrations.db"
    db = Database(db_file)

    with db.connection() as conn:
        rows = conn.execute(
            "SELECT version, description FROM schema_migrations ORDER BY version ASC"
        ).fetchall()
        versions = [r["version"] for r in rows]
        assert 1 in versions
        assert 2 in versions
        assert 3 in versions
        assert 4 in versions
        assert 5 in versions
        assert 6 in versions

    # Calling init_schema again should be completely idempotent
    db.init_schema()
    with db.connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert count == len(versions)


def test_migrations_module_exports(tmp_path: Path):
    from attest.migrations import (
        SCHEMA_SQL,
        apply_migrations,
        has_column,
        init_database,
    )

    assert "schema_migrations" in SCHEMA_SQL
    db_file = tmp_path / "test_module_migrations.db"
    import sqlite3

    conn = sqlite3.connect(str(db_file))
    try:
        init_database(conn)
        assert has_column(conn, "targets", "wire_model") is True
        assert has_column(conn, "targets", "non_existent_col") is False
        # Running apply_migrations again should be safe and idempotent
        apply_migrations(conn)
    finally:
        conn.close()


def _integrity_fixture(tmp_path):
    from attest.db import compute_samples_hash  # noqa: F401

    db = Database(tmp_path / "integrity2.db")
    db.save_target(Target(id="t", base_url="https://api.openai.com/v1", model="gpt-4o"))
    p_id = db.sync_prompts(
        [
            PromptItem(
                id=None,
                category="one_token",
                text="q",
                params={},
                samples_count=1,
                battery_version="v1",
            )
        ],
        "v1",
    )[0].id
    samples = [
        RawSample(
            prompt_id=p_id,
            raw_text="42",
            latency_ms=100,
            logprobs={"42": -0.1, "7": -2.4},
            usage={"completion_tokens": 1},
        )
    ]
    b_id = db.create_baseline_with_samples("t", "v1", samples)
    return db, b_id


def test_baseline_integrity_covers_logprobs(tmp_path):
    db, b_id = _integrity_fixture(tmp_path)
    assert db.verify_baseline_integrity(b_id)[0] is True

    with db.connection() as conn:
        conn.execute(
            "UPDATE baseline_samples SET logprobs = ? WHERE baseline_id = ?",
            ('{"99": -0.1, "7": -2.4}', b_id),
        )
    assert db.verify_baseline_integrity(b_id)[0] is False


def test_baseline_integrity_cannot_be_resealed_without_master_key(tmp_path):
    from attest.db import compute_samples_hash

    db, b_id = _integrity_fixture(tmp_path)
    with db.connection() as conn:
        conn.execute(
            "UPDATE baseline_samples SET raw_text = 'spoofed' WHERE baseline_id = ?",
            (b_id,),
        )
    tampered = db.get_baseline_samples(b_id)

    # Forging the HMAC format without the master key fails
    forged = "hmac-sha256:" + compute_samples_hash(tampered)
    # Downgrading to a recomputed legacy SHA-256, or dropping the seal, also fails
    for seal in (forged, compute_samples_hash(tampered), None):
        with db.connection() as conn:
            conn.execute(
                "UPDATE baselines SET integrity_hash = ? WHERE id = ?", (seal, b_id)
            )
        assert db.verify_baseline_integrity(b_id)[0] is False, seal


def test_legacy_baseline_seal_requires_explicit_reseal(tmp_path):
    from attest.db import compute_samples_hash

    db, b_id = _integrity_fixture(tmp_path)
    samples = db.get_baseline_samples(b_id)
    with db.connection() as conn:
        conn.execute(
            "UPDATE baselines SET integrity_hash = ? WHERE id = ?",
            (compute_samples_hash(samples), b_id),
        )

    # Legacy seals are not trusted implicitly, not even after reopening the DB
    reopened = Database(db.db_path)
    assert reopened.verify_baseline_integrity(b_id)[0] is False

    assert reopened.reseal_legacy_baselines() == 1
    assert reopened.get_baseline(b_id).integrity_hash.startswith("hmac-sha256:")
    assert reopened.verify_baseline_integrity(b_id)[0] is True


def test_ttft_roundtrip_and_integrity(tmp_path):
    from attest.db import compute_samples_hmac

    db, b_id = _integrity_fixture(tmp_path)
    # Baselines sealed before TTFT existed must keep verifying
    assert db.verify_baseline_integrity(b_id)[0] is True
    old = db.get_baseline_samples(b_id)
    assert old[0].ttft_ms is None

    with db.connection() as conn:
        conn.execute(
            "UPDATE baseline_samples SET ttft_ms = 250 WHERE baseline_id = ?", (b_id,)
        )
    # A TTFT added after sealing is tampering with timing data
    assert db.verify_baseline_integrity(b_id)[0] is False
    loaded = db.get_baseline_samples(b_id)
    assert loaded[0].ttft_ms == 250
    assert compute_samples_hmac(loaded) != compute_samples_hmac(old)
