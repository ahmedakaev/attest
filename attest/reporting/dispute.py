"""
Dispute Forensic Pack generator for Attest.
Creates audit-grade vendor evidence packages and formal dispute letters
when model substitution, silent degradation, or middleware tampering occurs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from attest import __version__
from attest.db import Database
from attest.i18n import get_method_title, get_verdict_label, normalize_locale
from attest.models import Baseline, RawSample, Run, Score, Target, Verdict


def generate_dispute_pack(
    db: Database, run_id: int, locale: str = "ru"
) -> dict[str, Any]:
    """
    Constructs a comprehensive, verifiable dispute evidence package for a given run.
    Pairs candidate run samples against baseline samples, checks baseline integrity,
    and identifies explicit divergence violations.
    """
    run_obj: Run | None = db.get_run(run_id)
    if not run_obj:
        raise ValueError(f"Run #{run_id} does not exist in database.")

    target: Target | None = db.get_target(run_obj.target_id)
    baseline: Baseline | None = db.get_baseline(run_obj.baseline_id)
    scores: list[Score] = db.get_scores(run_id)
    run_samples: list[RawSample] = db.get_run_samples(run_id)
    baseline_samples: list[RawSample] = (
        db.get_baseline_samples(run_obj.baseline_id) if run_obj.baseline_id else []
    )

    # Baseline cryptographic verification
    integrity_valid, stored_hash, computed_hash = (
        db.verify_baseline_integrity(run_obj.baseline_id)
        if run_obj.baseline_id
        else (False, None, None)
    )

    # Overall verdict via domain aggregate
    overall_verdict = Verdict.aggregate(scores)

    # Map baseline samples by prompt_id
    baseline_by_prompt: dict[int, list[RawSample]] = {}
    for bs in baseline_samples:
        baseline_by_prompt.setdefault(bs.prompt_id, []).append(bs)

    # Group run samples by prompt_id
    run_by_prompt: dict[int, list[RawSample]] = {}
    for rs in run_samples:
        run_by_prompt.setdefault(rs.prompt_id, []).append(rs)

    # Load prompt definitions
    prompts_map = {
        p.id: p for p in db.get_prompts(run_obj.battery_version) if p.id is not None
    }

    # Extract discrepancies
    violations: list[dict[str, Any]] = []
    for s in scores:
        if s.verdict in (Verdict.FAIL, Verdict.WARN) and isinstance(s.details, dict):
            failures = s.details.get("failures", [])
            if failures:
                for f in failures:
                    pid = f.get("prompt_id")
                    prompt_def = prompts_map.get(pid) if pid else None
                    c_samples = run_by_prompt.get(pid, [])
                    b_samples = baseline_by_prompt.get(pid, [])

                    candidate_text = (
                        c_samples[0].raw_text
                        if c_samples
                        else f.get("sample_preview", "")
                    )
                    candidate_latency = (
                        c_samples[0].latency_ms if c_samples else f.get("latency_ms")
                    )
                    candidate_reasoning = (
                        c_samples[0].reasoning_content if c_samples else None
                    )
                    candidate_r_tokens = (
                        c_samples[0].reasoning_tokens if c_samples else None
                    )
                    candidate_fp = c_samples[0].fingerprint if c_samples else None

                    baseline_text = b_samples[0].raw_text if b_samples else "N/A"
                    baseline_latency = b_samples[0].latency_ms if b_samples else None
                    baseline_reasoning = (
                        b_samples[0].reasoning_content if b_samples else None
                    )
                    baseline_r_tokens = (
                        b_samples[0].reasoning_tokens if b_samples else None
                    )
                    baseline_fp = b_samples[0].fingerprint if b_samples else None

                    violations.append(
                        {
                            "prompt_id": pid,
                            "category": prompt_def.category
                            if prompt_def
                            else "general",
                            "prompt_text": prompt_def.text if prompt_def else "",
                            "issue_type": s.method,
                            "assertion": f.get("assertion"),
                            "expected": f.get("expected"),
                            "details": f.get("message", "Violation detected"),
                            "candidate": {
                                "raw_text": candidate_text,
                                "latency_ms": candidate_latency,
                                "fingerprint": candidate_fp,
                                "reasoning_tokens": candidate_r_tokens,
                                "reasoning_content": candidate_reasoning,
                            },
                            "baseline": {
                                "raw_text": baseline_text,
                                "latency_ms": baseline_latency,
                                "fingerprint": baseline_fp,
                                "reasoning_tokens": baseline_r_tokens,
                                "reasoning_content": baseline_reasoning,
                            },
                        }
                    )
            else:
                detail_msg = (
                    s.details.get("message")
                    or f"{s.method} failed (measured {s.value}, threshold {s.threshold})"
                )
                violations.append(
                    {
                        "prompt_id": None,
                        "category": s.scope,
                        "prompt_text": f"Metric / Scope: {s.method} ({s.scope})",
                        "issue_type": s.method,
                        "assertion": None,
                        "expected": f"<= {s.threshold}"
                        if s.threshold is not None
                        else "Pass",
                        "details": detail_msg,
                        "candidate": {
                            "raw_text": f"Measured value: {s.value}",
                            "latency_ms": None,
                            "fingerprint": None,
                            "reasoning_tokens": None,
                            "reasoning_content": None,
                        },
                        "baseline": {
                            "raw_text": f"Target threshold: {s.threshold}",
                            "latency_ms": None,
                            "fingerprint": None,
                            "reasoning_tokens": None,
                            "reasoning_content": None,
                        },
                    }
                )

    # Summary metrics
    now_iso = datetime.now(UTC).isoformat()
    pack = {
        "attest_version": __version__,
        "pack_generated_at": now_iso,
        "run_id": run_id,
        "overall_verdict": overall_verdict.value,
        "is_disputed": overall_verdict in (Verdict.FAIL, Verdict.WARN),
        "target": {
            "id": target.id if target else run_obj.target_id,
            "configured_model": target.model if target else "Unknown",
            "wire_model": target.wire_model if target else None,
            "base_url": target.base_url if target else "Unknown",
            "description": target.description if target else None,
        },
        "baseline": {
            "id": baseline.id if baseline else run_obj.baseline_id,
            "target_id": baseline.target_id if baseline else None,
            "captured_at": baseline.captured_at if baseline else None,
            "battery_version": baseline.battery_version if baseline else None,
            "integrity_verified": integrity_valid,
            "integrity_hash": stored_hash,
            "computed_hash": computed_hash,
        },
        "infrastructure": (
            infra_s.details
            if (
                infra_s := next(
                    (s for s in scores if s.method == "infrastructure"), None
                )
            )
            else None
        ),
        "run": {
            "started_at": run_obj.started_at,
            "finished_at": run_obj.finished_at,
            "battery_version": run_obj.battery_version,
            "trigger": run_obj.trigger,
            "samples_count": len(run_samples),
        },
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
        "violations_count": len(violations),
        "violations": violations,
        "locale": normalize_locale(locale),
    }

    # Generate Markdown dispute letter
    pack["dispute_letter_markdown"] = format_dispute_markdown(pack, locale=locale)
    return pack


def format_dispute_markdown(pack: dict[str, Any], locale: str = "ru") -> str:
    """Formats the dispute evidence packet into a ready-to-file formal dispute letter."""
    loc = normalize_locale(locale or pack.get("locale"))
    is_ru = loc == "ru"

    t = pack["target"]
    b = pack["baseline"]
    r = pack["run"]
    v_count = pack["violations_count"]
    verdict = pack["overall_verdict"]
    verdict_label = (
        get_verdict_label(Verdict(verdict), locale=loc)
        if verdict in Verdict._value2member_map_
        else verdict
    )

    lines: list[str] = []
    if is_ru:
        lines.append(
            f"# 🛡️ Претензионный пакет доказательств верификации Attest #{pack['run_id']}"
        )
        lines.append("")
        lines.append(
            f"**Время формирования**: `{pack['pack_generated_at']}` | **Версия ядра**: `v{pack['attest_version']}`"
        )
        lines.append(
            f"**Итоговый вердикт аудита**: **`{verdict_label}`** (Зафиксировано нарушений: {v_count})"
        )
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(
            "## 1. Контекст аудита и криптографическая цепочка целостности (Chain of Custody)"
        )
        lines.append("")
        lines.append(f"- **Идентификатор цели**: `{t['id']}`")
        lines.append(f"- **Проверяемый эндпоинт**: `{t['base_url']}`")
        lines.append(
            f"- **Заявленная модель**: `{t['configured_model']}` (Модель в запросе: `{t['wire_model'] or 'та же'}`)"
        )
        lines.append(
            f"- **Аудиторский запуск**: Запуск #{pack['run_id']} | Батарея: `{r['battery_version']}` | Триггер: `{r['trigger']}`"
        )
        baseline_info = f"Эталон #{b['id']}" if b.get("id") else "Без эталона"
        captured_info = (
            f" (Снят: `{b.get('captured_at') or 'Н/Д'}` с `{b.get('target_id') or 'Н/Д'}`)"
            if b.get("id")
            else ""
        )
        lines.append(f"- **Сверенный эталон**: {baseline_info}{captured_info}")
        hash_status = (
            "✅ ЦЕЛОСТНОСТЬ ПОДТВЕРЖДЕНА"
            if b["integrity_verified"]
            else "⚠️ НЕСООТВЕТСТВИЕ ХЕША / БЕЗ ХЕША"
        )
        lines.append(
            f"- **Проверка криптографического хеша**: {hash_status} (`{b['integrity_hash'] or 'Н/Д'}`)"
        )
        if pack.get("infrastructure"):
            inf_txt = pack["infrastructure"].get("summary_ru") or pack[
                "infrastructure"
            ].get("summary_en")
            if inf_txt:
                lines.append(f"- **Инфраструктура провайдера**: {inf_txt}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 2. Количественные оценки верификации")
        lines.append("")
        lines.append(
            "| Метрика / Проверка | Измеренное значение | Порог | Вердикт | Статус |"
        )
        lines.append("| :--- | :--- | :--- | :---: | :--- |")
        for s in pack["scores"]:
            th = f"{s['threshold']:.2f}" if s["threshold"] is not None else "—"
            v_obj = (
                Verdict(s["verdict"])
                if s["verdict"] in Verdict._value2member_map_
                else s["verdict"]
            )
            v_name = (
                get_verdict_label(v_obj, locale=loc)
                if isinstance(v_obj, Verdict)
                else str(v_obj)
            )
            v_badge = f"**{v_name}**"
            method_title = get_method_title(s["method"], locale=loc)
            val_str = (
                f"{float(s['value']):.4f}"
                if isinstance(s["value"], (int, float))
                else str(s["value"])
            )
            lines.append(
                f"| `{method_title}` ({s['scope']}) | **{val_str}** | {th} | {v_badge} | {v_name} |"
            )
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 3. Журнал расхождений и зафиксированных нарушений")
        lines.append("")
        if not pack["violations"]:
            lines.append(
                "Нарушений не зафиксировано. Поведение кандидата полностью соответствует спецификациям эталона."
            )
        else:
            for idx, v in enumerate(pack["violations"], 1):
                assert_lbl = (
                    f" - Правило `{v['assertion']}`" if v.get("assertion") else ""
                )
                prompt_header = (
                    f" (Промпт #{v['prompt_id']} - `{v['category']}`)"
                    if v.get("prompt_id")
                    else f" (`{v['category']}`)"
                )
                method_name = get_method_title(v["issue_type"], locale=loc)
                lines.append(
                    f"### Нарушение #{idx}: {method_name.upper()}{assert_lbl}{prompt_header}"
                )
                lines.append(f'**Промпт / Метрика**: *"{v["prompt_text"]}"*')
                if v.get("assertion"):
                    lines.append(f"**Нарушенное правило**: `{v['assertion']}`")
                lines.append(
                    f"**Причина сбоя**: {v['details']} (Ожидалось: `{v['expected']}`)"
                )
                lines.append("")
                lines.append("#### Ответ проверяемого кандидата:")
                lines.append("```")
                lines.append(v["candidate"]["raw_text"] or "(пусто)")
                lines.append("```")
                if v["candidate"].get("reasoning_content"):
                    lines.append(
                        "##### Трассировка рассуждений (Reasoning Trace) кандидата:"
                    )
                    lines.append("```")
                    lines.append(v["candidate"]["reasoning_content"])
                    lines.append("```")
                lines.append(
                    f"*Задержка: {v['candidate']['latency_ms']}мс | "
                    f"Отпечаток: `{v['candidate']['fingerprint'] or 'нет'}` | "
                    f"Токены рассуждений: `{v['candidate']['reasoning_tokens'] or 0}`*"
                )
                lines.append("")
                lines.append("#### Ответ эталона (Ground Truth):")
                lines.append("```")
                lines.append(v["baseline"]["raw_text"] or "(пусто)")
                lines.append("```")
                if v["baseline"].get("reasoning_content"):
                    lines.append(
                        "##### Трассировка рассуждений (Reasoning Trace) эталона:"
                    )
                    lines.append("```")
                    lines.append(v["baseline"]["reasoning_content"])
                    lines.append("```")
                lines.append(
                    f"*Задержка: {v['baseline']['latency_ms']}мс | "
                    f"Отпечаток: `{v['baseline']['fingerprint'] or 'нет'}` | "
                    f"Токены рассуждений: `{v['baseline']['reasoning_tokens'] or 0}`*"
                )
                lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 4. Официальное претензионное уведомление поставщику API")
        lines.append("")
        lines.append("```text")
        lines.append(f"КОМУ: Служба поддержки и биллинг, {t['base_url']}")
        lines.append(
            f"ТЕМА: Официальная претензия по качеству и подлинности модели - {t['configured_model']}"
        )
        lines.append("")
        lines.append("Уважаемая служба технической поддержки,")
        lines.append("")
        lines.append(
            "Наша система автоматической верификации нейросетей (Attest) зафиксировала существенное поведенческое расхождение,"
        )
        lines.append(
            f"деградацию качества ответов либо несанкционированную подмену модели на вашем эндпоинте для модели '{t['configured_model']}'."
        )
        lines.append("")
        lines.append(
            f"Аудиторский запуск: Attest Run #{pack['run_id']} ({pack['pack_generated_at']})"
        )
        lines.append(
            f"Итоговый вердикт: {verdict_label} (зафиксировано {v_count} нарушений)."
        )
        lines.append(
            f"Сверенный эталон: #{b['id']} (Криптографический хеш: {b['integrity_hash']})"
        )
        lines.append("")
        lines.append("Ключевые зафиксированные нарушения:")
        for v in pack["violations"][:5]:
            lines.append(
                f" - [{v['issue_type']}] Промпт '{v['prompt_text'][:60]}...': {v['details']}"
            )
        if len(pack["violations"]) > 5:
            lines.append(
                f" - ... плюс еще {len(pack['violations']) - 5} нарушений, зафиксированных в полном отчете."
            )
        lines.append("")
        lines.append(
            "Просим провести внутреннее расследование маршрутизации, конфигураций вышестоящих провайдеров и прокси-модулей."
        )
        lines.append(
            "Мы требуем перерасчёта стоимости скомпрометированного объёма запросов и подтверждения маршрутизации на оригинальные веса модели."
        )
        lines.append("")
        lines.append("С уважением,")
        lines.append("Команда разработки и контроля качества ИИ")
        lines.append("```")
        lines.append("")
    else:
        lines.append(f"# 🛡️ Attest Verification Dispute Evidence Pack #{pack['run_id']}")
        lines.append("")
        lines.append(
            f"**Generated at**: `{pack['pack_generated_at']}` | **Attest Engine**: `v{pack['attest_version']}`"
        )
        lines.append(
            f"**Overall Audit Verdict**: **`{verdict}`** (Violations identified: {v_count})"
        )
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 1. Audit Context & Cryptographic Chain of Custody")
        lines.append("")
        lines.append(f"- **Target Identity**: `{t['id']}`")
        lines.append(f"- **Candidate Endpoint**: `{t['base_url']}`")
        lines.append(
            f"- **Configured Model**: `{t['configured_model']}` (Wire Model: `{t['wire_model'] or 'same'}`)"
        )
        lines.append(
            f"- **Audit Run**: Run #{pack['run_id']} | Battery: `{r['battery_version']}` | Trigger: `{r['trigger']}`"
        )
        baseline_info = (
            f"Baseline #{b['id']}" if b.get("id") else "No Reference Baseline"
        )
        captured_info = (
            f" (Captured: `{b.get('captured_at') or 'N/A'}` from `{b.get('target_id') or 'N/A'}`)"
            if b.get("id")
            else ""
        )
        lines.append(f"- **Reference Baseline**: {baseline_info}{captured_info}")
        hash_status = (
            "✅ VERIFIED MATCH" if b["integrity_verified"] else "⚠️ MISMATCH / UNHASHED"
        )
        lines.append(
            f"- **Baseline Integrity Check**: {hash_status} (`{b['integrity_hash'] or 'N/A'}`)"
        )
        if pack.get("infrastructure"):
            inf_txt = pack["infrastructure"].get("summary_en") or pack[
                "infrastructure"
            ].get("summary_ru")
            if inf_txt:
                lines.append(f"- **Provider Infrastructure**: {inf_txt}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 2. Quantitative Verification Scores")
        lines.append("")
        lines.append(
            "| Metric / Evaluator | Measured Value | Threshold | Verdict | Result Status |"
        )
        lines.append("| :--- | :--- | :--- | :---: | :--- |")
        for s in pack["scores"]:
            th = f"{s['threshold']:.2f}" if s["threshold"] is not None else "—"
            v_badge = f"**{s['verdict']}**"
            val_str = (
                f"{float(s['value']):.4f}"
                if isinstance(s["value"], (int, float))
                else str(s["value"])
            )
            lines.append(
                f"| `{s['method']}` ({s['scope']}) | **{val_str}** | {th} | {v_badge} | {s['verdict']} |"
            )
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 3. Discrepancies & Violations Log")
        lines.append("")
        if not pack["violations"]:
            lines.append(
                "No active violations detected. Candidate matches baseline specifications."
            )
        else:
            for idx, v in enumerate(pack["violations"], 1):
                assert_lbl = (
                    f" - Assertion `{v['assertion']}`" if v.get("assertion") else ""
                )
                prompt_header = (
                    f" (Prompt #{v['prompt_id']} - `{v['category']}`)"
                    if v.get("prompt_id")
                    else f" (`{v['category']}`)"
                )
                lines.append(
                    f"### Violation #{idx}: {v['issue_type'].upper()}{assert_lbl}{prompt_header}"
                )
                lines.append(f'**Prompt / Metric**: *"{v["prompt_text"]}"*')
                if v.get("assertion"):
                    lines.append(f"**Assertion Violated**: `{v['assertion']}`")
                lines.append(
                    f"**Failure Reason**: {v['details']} (Expected: `{v['expected']}`)"
                )
                lines.append("")
                lines.append("#### Candidate Response:")
                lines.append("```")
                lines.append(v["candidate"]["raw_text"] or "(empty)")
                lines.append("```")
                if v["candidate"].get("reasoning_content"):
                    lines.append("##### Candidate Reasoning Trace:")
                    lines.append("```")
                    lines.append(v["candidate"]["reasoning_content"])
                    lines.append("```")
                lines.append(
                    f"*Latency: {v['candidate']['latency_ms']}ms | "
                    f"Fingerprint: `{v['candidate']['fingerprint'] or 'none'}` | "
                    f"Reasoning Tokens: `{v['candidate']['reasoning_tokens'] or 0}`*"
                )
                lines.append("")
                lines.append("#### Reference Baseline Response:")
                lines.append("```")
                lines.append(v["baseline"]["raw_text"] or "(empty)")
                lines.append("```")
                if v["baseline"].get("reasoning_content"):
                    lines.append("##### Reference Baseline Reasoning Trace:")
                    lines.append("```")
                    lines.append(v["baseline"]["reasoning_content"])
                    lines.append("```")
                lines.append(
                    f"*Latency: {v['baseline']['latency_ms']}ms | "
                    f"Fingerprint: `{v['baseline']['fingerprint'] or 'none'}` | "
                    f"Reasoning Tokens: `{v['baseline']['reasoning_tokens'] or 0}`*"
                )
                lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 4. Formal Provider Dispute Notice")
        lines.append("")
        lines.append("```text")
        lines.append(f"TO: Support & Billing Team, {t['base_url']}")
        lines.append(
            f"SUBJECT: Formal Quality & Model Integrity Dispute - {t['configured_model']}"
        )
        lines.append("")
        lines.append("Dear Provider Support Team,")
        lines.append("")
        lines.append(
            "Our automated model verification harness (Attest) has detected significant behavioral divergence,"
        )
        lines.append(
            f"quality degradation, or unauthorized model substitution on your endpoint for model '{t['configured_model']}'."
        )
        lines.append("")
        lines.append(
            f"Audit Reference: Attest Run #{pack['run_id']} ({pack['pack_generated_at']})"
        )
        lines.append(f"Overall Result: {verdict} with {v_count} non-conformities.")
        lines.append(
            f"Reference Baseline: #{b['id']} (Cryptographic Hash: {b['integrity_hash']})"
        )
        lines.append("")
        lines.append("Key Violations Observed:")
        for v in pack["violations"][:5]:
            lines.append(
                f" - [{v['issue_type']}] Prompt '{v['prompt_text'][:60]}...': {v['details']}"
            )
        if len(pack["violations"]) > 5:
            lines.append(
                f" - ... plus {len(pack['violations']) - 5} additional violations documented in forensic pack."
            )
        lines.append("")
        lines.append(
            "Please investigate your routing rules, upstream provider configurations, and any proxy middlewares."
        )
        lines.append(
            "We request a credit for compromised request volumes and confirmation that genuine weights are routed."
        )
        lines.append("")
        lines.append("Sincerely,")
        lines.append("AI Engineering & Quality Assurance Team")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)
