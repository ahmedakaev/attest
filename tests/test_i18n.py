"""
Unit tests for Attest i18n and failure diagnostics module.
"""

from attest.comparator.pipeline import ComparatorPipeline
from attest.config import ThresholdsConfig
from attest.i18n import (
    build_pipeline_summary_message,
    format_failure_diagnostics,
    get_method_title,
    get_verdict_label,
    normalize_locale,
    render_template,
)
from attest.models import PromptAssertion, PromptItem, RawSample, Score, Target, Verdict


def test_normalize_locale():
    assert normalize_locale("ru") == "ru"
    assert normalize_locale("RU") == "ru"
    assert normalize_locale("ru-RU") == "ru"
    assert normalize_locale("en") == "en"
    assert normalize_locale("en-US") == "en"
    assert normalize_locale(None) == "ru"
    assert normalize_locale("") == "ru"


def test_render_template():
    assert (
        render_template("summary_pass", "ru")
        == "ПРОЙДЕНО — Целевой эндпоинт полностью соответствует эталонной сигнатуре (baseline) в пределах допусков."
    )
    assert (
        render_template("summary_pass", "en")
        == "PASSED — Target endpoint matches baseline signature within expected tolerances."
    )

    # Template with kwargs
    res = render_template("quick_model_mismatch", "ru", claimed="m1", returned="m2")
    assert "m1" in res and "m2" in res and "подмена модели" in res

    # Fallback to key if unknown
    assert render_template("non_existent_key", "ru") == "non_existent_key"


def test_get_method_title():
    assert get_method_title("quick_model", "ru") == "Соответствие заявленной модели"
    assert get_method_title("quick_model", "en") == "Claimed Model Claim Match"
    assert get_method_title("jsd", "ru") == "Расхождение распределения токенов (JSD)"
    assert get_method_title("assertions", "ru") == "Детерминированные правила (Ассерты)"
    assert get_method_title("unknown_method", "ru") == "unknown_method"


def test_get_verdict_label():
    assert get_verdict_label(Verdict.PASS, "ru") == "ПРОЙДЕНО"
    assert get_verdict_label(Verdict.FAIL, "ru") == "ПРОВАЛЕНО"
    assert get_verdict_label(Verdict.WARN, "ru") == "ВНИМАНИЕ"
    assert get_verdict_label(Verdict.PASS, "en") == "PASSED"
    assert get_verdict_label(Verdict.FAIL, "en") == "FAILED"


def test_diagnostics_quick_model_mismatch():
    score = Score(
        id=None,
        run_id=1,
        method="quick_model",
        scope="global",
        value=0.0,
        threshold=1.0,
        verdict=Verdict.FAIL,
        details={"claimed": "gpt-4o", "returned": "gpt-3.5-turbo"},
    )
    # Russian diagnostics
    diag_ru = format_failure_diagnostics([score], locale="ru")
    assert len(diag_ru) == 1
    assert diag_ru[0]["method"] == "quick_model"
    assert "gpt-4o" in diag_ru[0]["message"]
    assert "gpt-3.5-turbo" in diag_ru[0]["message"]
    assert "подмена модели" in diag_ru[0]["message"]

    # English diagnostics
    diag_en = format_failure_diagnostics([score], locale="en")
    assert len(diag_en) == 1
    assert "model mismatch" in diag_en[0]["message"]


def test_diagnostics_fingerprint_and_seed():
    scores = [
        Score(
            id=None,
            run_id=1,
            method="quick_fingerprint",
            scope="global",
            value=0.0,
            threshold=1.0,
            verdict=Verdict.WARN,
            details={"baseline_fp": "fp_abc123", "run_fp": "fp_xyz789"},
        ),
        Score(
            id=None,
            run_id=1,
            method="quick_seed",
            scope="global",
            value=0.0,
            threshold=1.0,
            verdict=Verdict.FAIL,
            details={"divergent_prompts": 2},
        ),
    ]
    diag = format_failure_diagnostics(scores, locale="ru")
    assert len(diag) == 2
    assert "fp_abc123" in diag[0]["message"]
    assert "fp_xyz789" in diag[0]["message"]
    assert "2 промптов вернули разные ответы" in diag[1]["message"]


def test_diagnostics_assertions():
    prompts_map = {
        10: PromptItem(
            id=10,
            category="json",
            text="Provide JSON payload",
            params={},
            samples_count=1,
            battery_version="v1",
            assertions=[PromptAssertion(type="is_json")],
        )
    }
    score = Score(
        id=None,
        run_id=1,
        method="assertions",
        scope="aggregate",
        value=0.5,
        threshold=1.0,
        verdict=Verdict.FAIL,
        details={
            "total_assertions": 2,
            "passed_assertions": 1,
            "failure_count": 1,
            "failures": [
                {
                    "prompt_id": 10,
                    "assertion": "is_json",
                    "message": "Expected JSON formatting",
                }
            ],
        },
    )
    diag = format_failure_diagnostics([score], prompts_map=prompts_map, locale="ru")
    assert len(diag) == 1
    assert diag[0]["prompt_id"] == 10
    assert "Provide JSON payload" in (diag[0]["prompt_preview"] or "")
    assert "is_json" in diag[0]["message"]
    assert "Expected JSON formatting" in diag[0]["message"]


def test_diagnostics_jsd_and_tps():
    scores = [
        Score(
            id=None,
            run_id=1,
            method="jsd",
            scope="category:reasoning",
            value=0.2450,
            threshold=0.15,
            verdict=Verdict.FAIL,
            details={
                "category": "reasoning",
                "top_tokens_baseline": " {A: 0.9}",
                "top_tokens_run": " {B: 0.8}",
            },
        ),
        Score(
            id=None,
            run_id=1,
            method="latency_tps",
            scope="global",
            value=0.75,
            threshold=0.50,
            verdict=Verdict.WARN,
            details={"baseline_tps": 80.0, "run_tps": 20.0, "tps_drift": 0.75},
        ),
    ]
    diag = format_failure_diagnostics(scores, locale="ru")
    assert len(diag) == 2
    assert "0.2450" in diag[0]["message"]
    assert "80.0" in diag[1]["message"]
    assert "20.0" in diag[1]["message"]
    assert "просадка на 75.0%" in diag[1]["message"]


def test_build_pipeline_summary_message():
    # Pass
    msg_pass = build_pipeline_summary_message(Verdict.PASS, [], locale="ru")
    assert "ПРОЙДЕНО" in msg_pass

    # Fail with causes
    diagnostics = [
        {
            "title": "Модель",
            "message": "Заявлена модель 'gpt-4o', но API фактически вернул 'gpt-3.5'",
        },
        {"title": "JSD", "message": "JSD = 0.25 превысило порог 0.15"},
    ]
    msg_fail = build_pipeline_summary_message(Verdict.FAIL, diagnostics, locale="ru")
    assert "ПРОВАЛЕНО" in msg_fail
    assert "Обнаружены отклонения" in msg_fail
    assert "[Модель]" in msg_fail
    assert "[JSD]" in msg_fail


def test_pipeline_integration_produces_failure_diagnostics():
    target = Target(id="test-provider", base_url="https://api.fake.com", model="gpt-4o")
    prompts = [
        PromptItem(
            id=1,
            category="general",
            text="Test 1",
            params={},
            samples_count=1,
            battery_version="v1",
        ),
        PromptItem(
            id=2,
            category="general",
            text="Test 2",
            params={},
            samples_count=1,
            battery_version="v1",
        ),
    ]
    base_samples = [
        RawSample(
            prompt_id=1,
            raw_text="Answer 1",
            latency_ms=100,
            model_returned="gpt-4o",
            fingerprint="fp_1",
        ),
        RawSample(
            prompt_id=2,
            raw_text="Answer 2",
            latency_ms=100,
            model_returned="gpt-4o",
            fingerprint="fp_1",
        ),
    ]
    # Spoofed run: returns gpt-3.5-turbo instead of claimed gpt-4o
    run_samples = [
        RawSample(
            prompt_id=1,
            raw_text="Substituted 1",
            latency_ms=100,
            model_returned="gpt-3.5-turbo",
            fingerprint="fp_other",
        ),
        RawSample(
            prompt_id=2,
            raw_text="Substituted 2",
            latency_ms=100,
            model_returned="gpt-3.5-turbo",
            fingerprint="fp_other",
        ),
    ]

    pipeline = ComparatorPipeline(thresholds=ThresholdsConfig())
    result = pipeline.execute(
        target=target,
        baseline_samples=base_samples,
        run_samples=run_samples,
        prompts=prompts,
        run_id=99,
        locale="ru",
    )

    assert result.overall_verdict == Verdict.FAIL
    assert len(result.failure_diagnostics) >= 1
    assert any(d["method"] == "quick_model" for d in result.failure_diagnostics)
    assert "ПРОВАЛЕНО" in result.summary_message
