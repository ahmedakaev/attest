"""
Unit tests for Attest dispute reporting and evidence pack export.
"""

from pathlib import Path

from attest.models import Baseline, RawSample, Run, Score, Target, Verdict
from attest.reporting.html import build_html_report, generate_html_report


def test_build_and_generate_html_report(tmp_path: Path):
    target = Target(
        id="test-provider",
        base_url="https://api.example.com/v1",
        model="gpt-5.6-luna",
        description="Candidate reseller endpoint",
    )
    baseline = Baseline(
        id=10,
        target_id="test-official",
        battery_version="v1",
        captured_at="2026-09-18T12:00:00Z",
    )
    run = Run(
        id=42,
        target_id=target.id,
        baseline_id=baseline.id,
        battery_version="v1",
        started_at="2026-09-19T10:00:00Z",
        finished_at="2026-09-19T10:00:45Z",
        status="completed",
        trigger="studio",
    )
    scores = [
        Score(
            id=1,
            run_id=run.id,
            method="jsd",
            scope="category:math",
            value=0.45,
            threshold=0.15,
            verdict=Verdict.FAIL,
            details={"discrepancy": "distribution divergent"},
        ),
        Score(
            id=2,
            run_id=run.id,
            method="quick_model",
            scope="global",
            value=1.0,
            threshold=1.0,
            verdict=Verdict.PASS,
            details={"claimed": "gpt-5.6-luna"},
        ),
        Score(
            id=3,
            run_id=run.id,
            method="assertions",
            scope="aggregate",
            value=0.8,
            threshold=1.0,
            verdict=Verdict.WARN,
            details={
                "total_assertions": 5,
                "passed_assertions": 4,
                "failure_count": 1,
                "failures": [
                    {
                        "prompt_id": 1,
                        "assertion": "is_json",
                        "expected": None,
                        "message": "Invalid JSON",
                    }
                ],
            },
        ),
    ]
    samples = [
        RawSample(
            prompt_id=1,
            raw_text="Solve 2+2: Result is 4.",
            latency_ms=250,
            fingerprint="fp_test_123",
            model_returned="gpt-5.6-luna",
            usage={"total_tokens": 15},
        )
    ]

    # Test Russian (default)
    html_ru = build_html_report(
        target=target,
        baseline=baseline,
        run=run,
        scores=scores,
        overall_verdict=Verdict.FAIL,
        samples=samples,
        locale="ru",
    )
    assert "<!DOCTYPE html>" in html_ru
    assert 'lang="ru"' in html_ru
    assert "Отчет о верификации и аудите на подмену" in html_ru
    assert "@media print" in html_ru
    assert "test-provider" in html_ru
    assert "gpt-5.6-luna" in html_ru
    assert "FAIL" in html_ru
    assert "Детерминированные правила" in html_ru
    assert "4/5 пройдено, 1 сбоев" in html_ru

    # Test English
    html_en = build_html_report(
        target=target,
        baseline=baseline,
        run=run,
        scores=scores,
        overall_verdict=Verdict.FAIL,
        samples=samples,
        locale="en",
    )
    assert "<!DOCTYPE html>" in html_en
    assert 'lang="en"' in html_en
    assert "Attest Verification & Anti-Spoofing Audit Report" in html_en
    assert "FAIL" in html_en
    assert "Deterministic Prompt Assertions" in html_en
    assert "4/5 passed, 1 failed" in html_en

    out_file = tmp_path / "report.html"
    saved_path = generate_html_report(
        target=target,
        baseline=baseline,
        run=run,
        scores=scores,
        overall_verdict=Verdict.FAIL,
        output_path=out_file,
        samples=samples,
        locale="ru",
    )
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") == html_ru


def test_print_run_report_with_assertions(capsys):
    from attest.reporting.console import print_run_report

    target = Target(
        id="test-target", base_url="https://api.example.com", model="gpt-5.5"
    )
    baseline = Baseline(
        id=1, target_id="ref", battery_version="v1", captured_at="2026-09-20"
    )
    run = Run(
        id=1,
        target_id="test-target",
        baseline_id=1,
        battery_version="v1",
        started_at="2026-09-20",
    )

    scores = [
        Score(
            id=1,
            run_id=1,
            method="assertions",
            scope="aggregate",
            value=0.75,
            threshold=1.0,
            verdict=Verdict.FAIL,
            details={
                "total_assertions": 4,
                "passed_assertions": 3,
                "failure_count": 1,
                "failures": [
                    {
                        "prompt_id": 1,
                        "assertion": "contains",
                        "expected": "xyz",
                        "message": "Expected text to contain 'xyz'",
                    }
                ],
            },
        )
    ]

    # Test Russian (default)
    print_run_report(
        target=target,
        baseline=baseline,
        run=run,
        scores=scores,
        overall_verdict=Verdict.FAIL,
        total_samples=10,
        duration_s=1.5,
        total_tokens=150,
        est_cost_usd=0.001,
        locale="ru",
    )
    captured = capsys.readouterr()
    assert "Детерминированные правила" in captured.out
    assert "3/4 пройдено, 1 сбоев" in captured.out

    # Test English
    print_run_report(
        target=target,
        baseline=baseline,
        run=run,
        scores=scores,
        overall_verdict=Verdict.FAIL,
        total_samples=10,
        duration_s=1.5,
        total_tokens=150,
        est_cost_usd=0.001,
        locale="en",
    )
    captured_en = capsys.readouterr()
    assert "Deterministic Prompt Assertions" in captured_en.out
    assert "3/4 passed, 1 failed" in captured_en.out


def test_generate_dispute_pack(tmp_path: Path):
    from attest.db import Database
    from attest.models import PromptAssertion, PromptItem
    from attest.reporting.dispute import generate_dispute_pack

    db = Database(tmp_path / "test_dispute.db")
    target = Target(
        id="spoofed-vendor",
        base_url="https://api.suspicious-proxy.io/v1",
        model="deepseek-reasoner",
        description="Vendor claiming DeepSeek R1",
    )
    db.save_target(target)

    prompts = db.sync_prompts(
        [
            PromptItem(
                id=None,
                category="reasoning",
                text="Solve step by step: 23 * 47",
                params={"temperature": 0.0},
                samples_count=1,
                battery_version="v1",
                assertions=[PromptAssertion(type="has_reasoning")],
            )
        ],
        "v1",
    )
    p_id = prompts[0].id

    b_id = db.create_baseline(target.id, "v1", notes="Ground truth baseline")
    db.save_baseline_samples(
        b_id,
        [
            RawSample(
                prompt_id=p_id,
                raw_text="The answer is 1081.",
                latency_ms=2100,
                fingerprint="fp_genuine_r1",
                reasoning_content="First 20 * 47 = 940, then 3 * 47 = 141. 940 + 141 = 1081.",
                reasoning_tokens=520,
            )
        ],
    )

    r_id = db.create_run(target.id, b_id, "v1")
    db.save_run_samples(
        r_id,
        [
            RawSample(
                prompt_id=p_id,
                raw_text="Answer: 1081",
                latency_ms=150,
                fingerprint="fp_fast_distilled",
                reasoning_content=None,
                reasoning_tokens=0,
            )
        ],
    )
    db.save_scores(
        [
            Score(
                id=None,
                run_id=r_id,
                method="assertions",
                scope="aggregate",
                value=0.0,
                threshold=1.0,
                verdict=Verdict.FAIL,
                details={
                    "failures": [
                        {
                            "prompt_id": p_id,
                            "assertion": "has_reasoning",
                            "expected": None,
                            "message": "Response must contain reasoning/thinking trace or reasoning tokens",
                            "latency_ms": 150,
                            "sample_preview": "Answer: 1081",
                        }
                    ]
                },
            )
        ]
    )
    db.finish_run(r_id, "completed")

    # Test Russian (default)
    pack_ru = generate_dispute_pack(db, r_id, locale="ru")
    assert pack_ru["run_id"] == r_id
    assert pack_ru["overall_verdict"] == "FAIL"
    assert pack_ru["is_disputed"] is True
    assert pack_ru["violations_count"] == 1
    assert pack_ru["target"]["id"] == "spoofed-vendor"
    assert pack_ru["baseline"]["integrity_verified"] is True
    assert "dispute_letter_markdown" in pack_ru

    md_ru = pack_ru["dispute_letter_markdown"]
    assert "Претензионный пакет доказательств верификации Attest" in md_ru
    assert "Официальное претензионное уведомление поставщику API" in md_ru
    assert "has_reasoning" in md_ru
    assert "First 20 * 47" in md_ru

    # Test English
    pack_en = generate_dispute_pack(db, r_id, locale="en")
    md_en = pack_en["dispute_letter_markdown"]
    assert "Attest Verification Dispute Evidence Pack" in md_en
    assert "Formal Provider Dispute Notice" in md_en
    assert "has_reasoning" in md_en
    assert "First 20 * 47" in md_en
