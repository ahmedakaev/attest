"""
Internationalization (i18n) and diagnostic failure explanation module for Attest.
Provides Russian and English translations, method titles, and detailed failure diagnostics
via declarative localization catalogs and template rendering.
"""

from __future__ import annotations

from typing import Any

from attest.models import PromptItem, Score, Verdict

TIER_TITLES: dict[str, dict[str, str]] = {
    "ru": {
        "quick_model": "Соответствие заявленной модели",
        "quick_fingerprint": "Системный отпечаток (Fingerprint)",
        "quick_seed": "Детерминизм сида (Seed)",
        "routing_proof": "Маршрут по данным провайдера (Routing Metadata)",
        "tokenizer": "Дактилоскопия токенизатора (BPE Spectrum)",
        "infrastructure": "Инфраструктура и облачные шлюзы",
        "jsd": "Расхождение распределения токенов (JSD)",
        "latency_tps": "Скорость генерации токенов (TPS)",
        "latency_drift": "Задержка ответа (Latency Drift)",
        "latency_ttft": "Время до первого токена (TTFT)",
        "assertions": "Детерминированные правила (Ассерты)",
        "embedding_cosine": "Семантическое сходство эмбеддингов",
        "mmd_permutation": "Статистический тест MMD (Permutation)",
        "billing": "Честность биллинга токенов",
        "iris": "Отпечаток случайных строк (IRIS)",
        "gateway_limits": "Ограничения шлюза (max_tokens)",
        "baseline_coverage": "Покрытие эталоном",
    },
    "en": {
        "quick_model": "Claimed Model Claim Match",
        "quick_fingerprint": "System Fingerprint Consistency",
        "quick_seed": "Seed Determinism",
        "routing_proof": "Provider-Reported Routing Metadata",
        "tokenizer": "BPE Tokenizer Spectrum Fingerprint",
        "infrastructure": "Infrastructure & Cloud Gateways",
        "jsd": "One-Token JSD Divergence",
        "latency_tps": "TPS Generation Throughput",
        "latency_drift": "Latency Distribution Shift",
        "latency_ttft": "Time to First Token (TTFT)",
        "assertions": "Deterministic Prompt Assertions",
        "embedding_cosine": "Semantic Cosine Similarity",
        "mmd_permutation": "MMD Permutation Test",
        "billing": "Token Billing Integrity",
        "iris": "Random-String Fingerprint (IRIS)",
        "gateway_limits": "Gateway Limits (max_tokens)",
        "baseline_coverage": "Baseline Coverage",
    },
}

VERDICT_LABELS: dict[str, dict[Verdict, str]] = {
    "ru": {
        Verdict.PASS: "ПРОЙДЕНО",
        Verdict.WARN: "ВНИМАНИЕ",
        Verdict.FAIL: "ПРОВАЛЕНО",
        Verdict.SKIP: "ПРОПУЩЕНО",
    },
    "en": {
        Verdict.PASS: "PASSED",
        Verdict.WARN: "WARNING",
        Verdict.FAIL: "FAILED",
        Verdict.SKIP: "SKIPPED",
    },
}

DIAGNOSTIC_CATALOG: dict[str, dict[str, str]] = {
    "ru": {
        "quick_model_mismatch": "Заявлена модель '{claimed}', но API фактически вернул '{returned}' (подмена модели)",
        "routing_proof_mismatch": "Провайдер сам сообщает о подмене: заявлена модель '{claimed}', но его метаданные маршрутизации указывают на '{actual}' через {provider}",
        "quick_fingerprint_drift": "Системный отпечаток изменился: в эталоне '{baseline_fp}', при проверке '{run_fp}'",
        "quick_seed_divergence": "Нарушен детерминизм сида: {divergent} промптов вернули разные ответы при фиксированном seed",
        "assertion_prompt_prefix": "Промпт #{prompt_id}: ",
        "assertion_rule_failed": "{prefix}Провалено правило '{assertion}' — {message}",
        "assertion_summary_failed": "Пройдено только {passed}/{total} проверочных правил",
        "jsd_scope_cat": "Категория '{category}': ",
        "jsd_diff_hint": " (эталон: {baseline}, ран: {run})",
        "jsd_threshold_exceeded": "{scope_desc}Расхождение токенов JSD = {val:.4f} превысило порог {thresh:.2f}{diff_hint}",
        "direction_drop": "просадка",
        "direction_increase": "ускорение",
        "direction_slower": "замедление",
        "direction_faster": "ускорение",
        "latency_tps_drift": "Скорость генерации: {run_tps:.1f} ток/с против {baseline_tps:.1f} ток/с в эталоне ({direction} на {pct:.1f}%, порог: {thresh_pct:.0f}%)",
        "latency_drift_shift": "Задержка ответа: медиана {run_lat} мс против {baseline_lat} мс в эталоне (дрейф {pct:.1f}%, порог: {thresh_pct:.0f}%)",
        "latency_ttft_shift": "Время до первого токена: медиана {run_ms:.0f} мс против {baseline_ms:.0f} мс в эталоне ({direction} на {pct:.1f}%, порог: {thresh_pct:.0f}%)",
        "embedding_cosine_drop": "Семантическое сходство ответов упало до {val:.4f} (ниже порога {thresh:.2f})",
        "mmd_permutation_rejected": "Статистический MMD тест отверг гипотезу идентичности (p-value = {p_val:.4f} < {thresh:.2f})",
        "billing_prompt_scale": "Входные токены начисляются в {scale:.2f}× от эталона (переплата ~{pct:.0f}% за вход)",
        "billing_prompt_overhead": "К каждому запросу добавляется ~{tokens:.0f} входных токенов (скрытый системный промпт или накрутка)",
        "billing_completion": "За тот же объём текста ответа начислено на {pct:.0f}% больше выходных токенов, чем в эталоне",
        "billing_phantom_reasoning": "Начислено {tokens} reasoning-токенов в {samples} ответах, хотя эталонная модель не рассуждает",
        "billing_cap_ignored": "Провайдер игнорирует max_tokens: в {over} из {total} ответов начислено больше лимита (до {max_billed} токенов при лимите {cap}) — расход не ограничен",
        "iris_tells": "{tells}/{total} случайных строк нетипичны для эталонной модели (ожидалось ~{expected:.1f}, p = {p_val:.4f}); на другую модель уходит не менее {pct:.0f}% запросов",
        "generic_threshold_exceeded": "Превышен допустимый порог: значение {val:.4f} vs порог {threshold}",
        "summary_pass": "ПРОЙДЕНО — Целевой эндпоинт полностью соответствует эталонной сигнатуре (baseline) в пределах допусков.",
        "summary_skip": "ПРОПУЩЕНО — Недостаточно данных для подтверждения подлинности модели.",
        "summary_fail_prefix": "ПРОВАЛЕНО — Высокая вероятность подмены модели или деградации качества.",
        "summary_warn_prefix": "ВНИМАНИЕ — Обнаружен дрейф поведения или изменение инфраструктуры.",
        "summary_causes_lead": "Обнаружены отклонения: ",
        "summary_more_failures": " (+еще {count} сбоев)",
    },
    "en": {
        "quick_model_mismatch": "Claimed model '{claimed}', but API returned '{returned}' (model mismatch)",
        "routing_proof_mismatch": "Provider self-reports a swap: claimed '{claimed}', but its routing metadata names '{actual}' via {provider}",
        "quick_fingerprint_drift": "System fingerprint changed: baseline '{baseline_fp}' vs run '{run_fp}'",
        "quick_seed_divergence": "Seed determinism failed: {divergent} prompts diverged despite fixed seed",
        "assertion_prompt_prefix": "Prompt #{prompt_id}: ",
        "assertion_rule_failed": "{prefix}Rule '{assertion}' failed — {message}",
        "assertion_summary_failed": "Only {passed}/{total} verification assertions passed",
        "jsd_scope_cat": "Category '{category}': ",
        "jsd_diff_hint": " (baseline: {baseline}, run: {run})",
        "jsd_threshold_exceeded": "{scope_desc}JSD token divergence = {val:.4f} exceeded threshold {thresh:.2f}{diff_hint}",
        "direction_drop": "drop",
        "direction_increase": "increase",
        "direction_slower": "slower",
        "direction_faster": "faster",
        "latency_tps_drift": "Throughput: {run_tps:.1f} tok/s vs baseline {baseline_tps:.1f} tok/s ({direction} by {pct:.1f}%, threshold: {thresh_pct:.0f}%)",
        "latency_drift_shift": "Response latency: median {run_lat} ms vs baseline {baseline_lat} ms (shift {pct:.1f}%, threshold: {thresh_pct:.0f}%)",
        "latency_ttft_shift": "Time to first token: median {run_ms:.0f} ms vs baseline {baseline_ms:.0f} ms ({direction} by {pct:.1f}%, threshold: {thresh_pct:.0f}%)",
        "embedding_cosine_drop": "Semantic similarity dropped to {val:.4f} (below threshold {thresh:.2f})",
        "mmd_permutation_rejected": "MMD permutation test rejected distribution identity (p-value = {p_val:.4f} < {thresh:.2f})",
        "billing_prompt_scale": "Input tokens billed at {scale:.2f}x the baseline (~{pct:.0f}% input overcharge)",
        "billing_prompt_overhead": "~{tokens:.0f} extra input tokens billed on every request (hidden system prompt or padding)",
        "billing_completion": "The same amount of answer text is billed {pct:.0f}% more output tokens than the baseline",
        "billing_phantom_reasoning": "{tokens} reasoning tokens billed across {samples} responses although the baseline model does not reason",
        "billing_cap_ignored": "Provider ignores max_tokens: {over} of {total} replies billed past the cap (up to {max_billed} tokens for a cap of {cap}); spend is not bounded",
        "iris_tells": "{tells}/{total} random strings are atypical for the baseline model (expected ~{expected:.1f}, p = {p_val:.4f}); at least {pct:.0f}% of requests go to another model",
        "generic_threshold_exceeded": "Threshold exceeded: observed {val:.4f} vs threshold {threshold}",
        "summary_pass": "PASSED — Target endpoint matches baseline signature within expected tolerances.",
        "summary_skip": "SKIPPED — Insufficient data to determine model authenticity.",
        "summary_fail_prefix": "FAILED — High confidence of model substitution, quantization, or degradation.",
        "summary_warn_prefix": "WARNING — Behavioral drift or infrastructure changes detected.",
        "summary_causes_lead": "Discrepancies detected: ",
        "summary_more_failures": " (+{count} more failures)",
    },
}


def normalize_locale(locale: str | None) -> str:
    """
    Normalizes locale identifier to supported code ('ru' or 'en', default 'ru').
    """
    if not locale:
        return "ru"
    clean = locale.strip().lower()
    if clean.startswith("en"):
        return "en"
    return "ru"


def render_template(key: str, locale: str = "ru", **kwargs: Any) -> str:
    """
    Renders a localized template string by key from DIAGNOSTIC_CATALOG with kwargs formatting.
    Falls back to 'ru' catalog and then key if missing.
    """
    loc = normalize_locale(locale)
    catalog = DIAGNOSTIC_CATALOG.get(loc, DIAGNOSTIC_CATALOG["ru"])
    tpl = catalog.get(key)
    if tpl is None:
        tpl = DIAGNOSTIC_CATALOG["ru"].get(key, key)
    try:
        return tpl.format(**kwargs)
    except (KeyError, ValueError, IndexError):
        return tpl


def get_method_title(method: str, locale: str = "ru") -> str:
    loc = normalize_locale(locale)
    return TIER_TITLES.get(loc, TIER_TITLES["ru"]).get(method, method)


def get_verdict_label(v: Verdict, locale: str = "ru") -> str:
    loc = normalize_locale(locale)
    return VERDICT_LABELS.get(loc, VERDICT_LABELS["ru"]).get(v, v.value)


def format_failure_diagnostics(
    scores: list[Score],
    prompts_map: dict[int, PromptItem] | None = None,
    locale: str = "ru",
) -> list[dict[str, Any]]:
    """
    Extracts actionable diagnostics for any non-PASS scores, answering:
    1. On which test/probe did it fail?
    2. What exact discrepancy occurred (expected vs actual, numbers)?
    3. Which prompt was affected?
    """
    loc = normalize_locale(locale)
    diagnostics: list[dict[str, Any]] = []

    failing_scores = [s for s in scores if s.verdict in (Verdict.FAIL, Verdict.WARN)]
    for s in failing_scores:
        title = get_method_title(s.method, locale=loc)
        d = s.details or {}

        prompt_id = d.get("prompt_id")
        prompt_text = ""
        if prompt_id is not None and prompts_map and prompt_id in prompts_map:
            prompt_text = prompts_map[prompt_id].text

        reasons: list[str] = []

        if s.method == "quick_model":
            claimed = d.get("claimed", "—")
            returned = d.get("returned") or (
                d.get("returned_differing", ["—"])[0]
                if d.get("returned_differing")
                else "—"
            )
            reasons.append(
                render_template(
                    "quick_model_mismatch",
                    loc,
                    claimed=claimed,
                    returned=returned,
                )
            )

        elif s.method == "routing_proof":
            claimed = d.get("claimed_model", "—")
            actual = d.get("upstream_model", "—")
            provider = d.get("upstream_provider", "—")
            reasons.append(
                render_template(
                    "routing_proof_mismatch",
                    loc,
                    claimed=claimed,
                    actual=actual,
                    provider=provider,
                )
            )

        elif s.method == "tokenizer":
            reason = (
                d.get("reason")
                or d.get("message")
                or "Несоответствие словаря токенизатора"
            )
            reasons.append(str(reason))

        elif s.method == "quick_fingerprint":
            b_fp = d.get("baseline_fp") or "None"
            r_fp = d.get("run_fp") or "None"
            reasons.append(
                render_template(
                    "quick_fingerprint_drift",
                    loc,
                    baseline_fp=b_fp,
                    run_fp=r_fp,
                )
            )

        elif s.method == "quick_seed":
            divergent = d.get("divergent_prompts", d.get("divergent_samples", 1))
            reasons.append(
                render_template(
                    "quick_seed_divergence",
                    loc,
                    divergent=divergent,
                )
            )

        elif s.method == "assertions":
            failures = d.get("failures", [])
            total = d.get("total_assertions", 0)
            passed = d.get("passed_assertions", 0)
            if failures:
                for f in failures[:5]:
                    f_assert = f.get("assertion", "")
                    f_msg = f.get("message") or ""
                    f_pid = f.get("prompt_id")
                    prefix = (
                        render_template("assertion_prompt_prefix", loc, prompt_id=f_pid)
                        if f_pid
                        else ""
                    )
                    msg = render_template(
                        "assertion_rule_failed",
                        loc,
                        prefix=prefix,
                        assertion=f_assert,
                        message=f_msg,
                    )
                    f_text = ""
                    if f_pid and prompts_map and f_pid in prompts_map:
                        f_text = prompts_map[f_pid].text
                    diagnostics.append(
                        {
                            "method": s.method,
                            "title": title,
                            "verdict": s.verdict.value,
                            "prompt_id": f_pid,
                            "prompt_preview": (
                                f_text[:80] + ("..." if len(f_text) > 80 else "")
                                if f_text
                                else None
                            ),
                            "message": msg,
                        }
                    )
                continue
            else:
                reasons.append(
                    render_template(
                        "assertion_summary_failed",
                        loc,
                        passed=passed,
                        total=total,
                    )
                )

        elif s.method == "jsd":
            val = s.value
            thresh = s.threshold or 0.15
            cat = d.get("category", "")
            scope_desc = (
                render_template("jsd_scope_cat", loc, category=cat) if cat else ""
            )
            top_base = d.get("top_tokens_baseline")
            top_run = d.get("top_tokens_run")
            diff_hint = ""
            if top_base and top_run:
                diff_hint = render_template(
                    "jsd_diff_hint",
                    loc,
                    baseline=top_base,
                    run=top_run,
                )

            reasons.append(
                render_template(
                    "jsd_threshold_exceeded",
                    loc,
                    scope_desc=scope_desc,
                    val=val,
                    thresh=thresh,
                    diff_hint=diff_hint,
                )
            )

        elif s.method == "latency_tps":
            b_raw = d.get("baseline_tps", 0.0)
            r_raw = d.get("run_tps", 0.0)
            b_tps = (
                b_raw.get("median", 0.0)
                if isinstance(b_raw, dict)
                else float(b_raw or 0.0)
            )
            r_tps = (
                r_raw.get("median", 0.0)
                if isinstance(r_raw, dict)
                else float(r_raw or 0.0)
            )
            drift = d.get("tps_drift", s.value)
            pct = abs(drift) * 100
            direction = (
                render_template("direction_drop", loc)
                if r_tps < b_tps
                else render_template("direction_increase", loc)
            )
            thresh_pct = (s.threshold or 0.5) * 100
            reasons.append(
                render_template(
                    "latency_tps_drift",
                    loc,
                    run_tps=r_tps,
                    baseline_tps=b_tps,
                    direction=direction,
                    pct=pct,
                    thresh_pct=thresh_pct,
                )
            )

        elif s.method == "latency_drift":
            # Scores store {"baseline_latency_ms": {"median": ...}}; older ones a flat median
            b_lat = (d.get("baseline_latency_ms") or {}).get(
                "median", d.get("baseline_median_ms", 0)
            )
            r_lat = (d.get("run_latency_ms") or {}).get(
                "median", d.get("run_median_ms", 0)
            )
            drift = d.get("drift", s.value)
            pct = abs(drift) * 100
            thresh_pct = (s.threshold or 0.6) * 100
            reasons.append(
                render_template(
                    "latency_drift_shift",
                    loc,
                    run_lat=r_lat,
                    baseline_lat=b_lat,
                    pct=pct,
                    thresh_pct=thresh_pct,
                )
            )

        elif s.method == "latency_ttft":
            b_ms = float((d.get("baseline_ttft_ms") or {}).get("median", 0.0))
            r_ms = float((d.get("run_ttft_ms") or {}).get("median", 0.0))
            reasons.append(
                render_template(
                    "latency_ttft_shift",
                    loc,
                    run_ms=r_ms,
                    baseline_ms=b_ms,
                    # Higher TTFT means a slower first token
                    direction=render_template(
                        "direction_slower" if r_ms > b_ms else "direction_faster", loc
                    ),
                    pct=abs(float(d.get("relative_change", s.value))) * 100,
                    thresh_pct=(s.threshold or 0.6) * 100,
                )
            )

        elif s.method == "embedding_cosine":
            val = s.value
            # Name the threshold that was actually crossed
            thresh = (
                d.get("threshold_warn", s.threshold)
                if s.verdict == Verdict.WARN
                else s.threshold
            ) or 0.88
            reasons.append(
                render_template(
                    "embedding_cosine_drop",
                    loc,
                    val=val,
                    thresh=thresh,
                )
            )

        elif s.method == "mmd_permutation":
            p_val = d.get("p_value", s.value)
            thresh = s.threshold or 0.05
            reasons.append(
                render_template(
                    "mmd_permutation_rejected",
                    loc,
                    p_val=p_val,
                    thresh=thresh,
                )
            )

        elif s.method == "billing":
            for issue in d.get("issues", []):
                kind = issue.get("kind")
                if kind == "prompt_scale":
                    scale = float(issue.get("scale", 1.0))
                    reasons.append(
                        render_template(
                            "billing_prompt_scale",
                            loc,
                            scale=scale,
                            pct=(scale - 1.0) * 100,
                        )
                    )
                elif kind in (
                    "prompt_overhead",
                    "completion",
                    "phantom_reasoning",
                    "cap_ignored",
                ):
                    reasons.append(render_template(f"billing_{kind}", loc, **issue))

        elif s.method == "iris":
            reasons.append(
                render_template(
                    "iris_tells",
                    loc,
                    tells=d.get("tells", 0),
                    total=d.get("total", 0),
                    expected=float(d.get("expected_tells", 0.0)),
                    p_val=float(d.get("p_value", s.value)),
                    pct=float(d.get("dilution_lower_bound", 0.0)) * 100,
                )
            )

        if not reasons and d.get("message"):
            reasons.append(str(d["message"]))

        if not reasons:
            thresh_repr = str(s.threshold) if s.threshold is not None else "—"
            reasons.append(
                render_template(
                    "generic_threshold_exceeded",
                    loc,
                    val=s.value,
                    threshold=thresh_repr,
                )
            )

        for r in reasons:
            diagnostics.append(
                {
                    "method": s.method,
                    "title": title,
                    "verdict": s.verdict.value,
                    "prompt_id": prompt_id,
                    "prompt_preview": (
                        prompt_text[:80] + ("..." if len(prompt_text) > 80 else "")
                        if prompt_text
                        else None
                    ),
                    "message": r,
                }
            )

    return diagnostics


def build_pipeline_summary_message(
    overall: Verdict,
    diagnostics: list[dict[str, Any]],
    locale: str = "ru",
) -> str:
    """
    Builds a clear, diagnostic-rich summary message explaining the exact failures.
    """
    loc = normalize_locale(locale)

    if overall == Verdict.PASS:
        return render_template("summary_pass", loc)

    if overall == Verdict.SKIP:
        return render_template("summary_skip", loc)

    prefix_key = (
        "summary_fail_prefix" if overall == Verdict.FAIL else "summary_warn_prefix"
    )
    prefix = render_template(prefix_key, loc)

    if not diagnostics:
        return prefix

    # List the distinct failure causes
    unique_messages = []
    seen = set()
    for d in diagnostics:
        msg = f"[{d['title']}] {d['message']}"
        if msg not in seen:
            seen.add(msg)
            unique_messages.append(msg)

    causes_text = "; ".join(unique_messages[:3])
    if len(unique_messages) > 3:
        more_count = len(unique_messages) - 3
        causes_text += render_template("summary_more_failures", loc, count=more_count)

    lead = render_template("summary_causes_lead", loc)
    return f"{prefix} {lead}{causes_text}"


HTML_REPORT_STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "title": "Attest — Отчет о верификации и аудите на подмену нейросети",
        "subtitle": "Официальный пакет доказательств верификации для разрешения споров и контроля качества",
        "back_btn": "← Вернуться в Attest Studio",
        "print_btn": "🖨️ Печать / Сохранить в PDF",
        "target_id": "ID целевого эндпоинта",
        "claimed_model": "Заявленная модель",
        "base_url": "URL провайдера",
        "ground_truth": "Эталонная сигнатура (Ground Truth)",
        "audit_timestamp": "Время проверки",
        "discrepancies_found": "Выявлено расхождений",
        "fails_warnings": "{fails} сбоев, {warns} предупреждений",
        "no_discrepancies": "Все проверки пройдены (0 сбоев)",
        "statement_title": "Экспертное заключение аудита",
        "verdict_fail": (
            "КРИТИЧЕСКИ: Обнаружено эмпирическое расхождение в поведении модели. Статистическое распределение "
            "токенов проверяемого эндпоинта существенно отклоняется от верифицированного эталона (Ground Truth). "
            "Данные указывают на вероятную подмену модели, урезание параметров/квантование или несанкционированное проксирование."
        ),
        "verdict_warn": (
            "ВНИМАНИЕ: Зафиксирован повышенный дрейф задержек или умеренное расхождение распределений. Наблюдаемые "
            "метрики превышают пороги предупреждения. Рекомендуется техническая проверка у поставщика."
        ),
        "verdict_pass": (
            "ПОДТВЕРЖДЕНО: Поведенческие распределения и выходные характеристики проверяемого эндпоинта "
            "статистически полностью соответствуют эталонной сигнатуре (Ground Truth)."
        ),
        "verdict_skip": "АУДИТ НЕ ЗАВЕРШЕН: Недостаточно данных выборки для вынесения однозначного вердикта.",
        "diag_heading": "🚨 Детализированная диагностика сбоев",
        "diag_subheading": "Конкретные причины отклонений, затронутые промпты и расхождения ожидаемых значений.",
        "prompt_badge": "Промпт #{prompt_id}",
        "tests_title": "Статистические тесты и детализация расхождений",
        "tests_sub": "Дифференциальные метрики, рассчитанные относительно эталонных вероятностных распределений.",
        "th_test": "Метод проверки",
        "th_scope": "Область",
        "th_score": "Наблюдаемое значение",
        "th_threshold": "Допустимый порог",
        "th_verdict": "Вердикт",
        "th_details": "Диагностические детали",
        "assertions_passed": "Все {passed}/{total} правил пройдены",
        "assertions_failed": "{passed}/{total} пройдено, {fail_count} сбоев",
        "evidence_title": "Эмпирические доказательства аудита (превью {count} из {total} сэмплов)",
        "evidence_sub": "Фактические ответы, зафиксированные в ходе данной верификации.",
        "th_prompt": "Промпт",
        "th_latency": "Задержка",
        "th_tokens": "Токены",
        "th_fingerprint": "Отпечаток",
        "th_output_preview": "Превью сгенерированного ответа",
        "footer": "Сформировано автоматически системой <strong>Attest</strong> (LLM Verification & Anti-Spoofing Engine) • Запуск #{run_id}",
    },
    "en": {
        "title": "Attest Verification & Anti-Spoofing Audit Report",
        "subtitle": "Official Verification Evidence Packet for Dispute & Quality Assurance",
        "back_btn": "← Back to Attest Studio",
        "print_btn": "🖨️ Print / Save as PDF",
        "target_id": "Target Endpoint ID",
        "claimed_model": "Claimed Model",
        "base_url": "Provider Base URL",
        "ground_truth": "Ground Truth Baseline",
        "audit_timestamp": "Audit Timestamp",
        "discrepancies_found": "Discrepancies Found",
        "fails_warnings": "{fails} Failed, {warns} Warnings",
        "no_discrepancies": "All tests passed (0 discrepancies)",
        "statement_title": "Executive Evidence Statement",
        "verdict_fail": (
            "CRITICAL: Empirical behavioral divergence detected. The tested endpoint's statistical "
            "token distribution deviates significantly from the verified Ground Truth baseline. "
            "Evidence indicates probable model spoofing, parameter degradation, or unauthorized proxy substitution."
        ),
        "verdict_warn": (
            "WARNING: Elevated divergence or latency irregularity detected. Observed distribution "
            "crosses warning thresholds. Recommended for vendor investigation."
        ),
        "verdict_pass": (
            "VERIFIED: The candidate endpoint's behavioral distributions and output characteristics "
            "are statistically consistent with the verified reference Ground Truth baseline."
        ),
        "verdict_skip": "AUDIT INCOMPLETE: Insufficient sample data to determine a definitive verdict.",
        "diag_heading": "🚨 Root Cause Failure Diagnostics",
        "diag_subheading": "Specific causes of divergence, affected prompts, and threshold discrepancies.",
        "prompt_badge": "Prompt #{prompt_id}",
        "tests_title": "Statistical Tests & Discrepancy Breakdown",
        "tests_sub": "Differential metrics computed against baseline distributions.",
        "th_test": "Verification Test",
        "th_scope": "Scope",
        "th_score": "Observed Score",
        "th_threshold": "Tolerance Threshold",
        "th_verdict": "Verdict",
        "th_details": "Diagnostic Details",
        "assertions_passed": "All {passed}/{total} rules passed",
        "assertions_failed": "{passed}/{total} passed, {fail_count} failed",
        "evidence_title": "Sampling Audit Evidence (Preview of {count} of {total} Samples)",
        "evidence_sub": "Empirical responses captured during this verification run.",
        "th_prompt": "Prompt",
        "th_latency": "Latency",
        "th_tokens": "Tokens",
        "th_fingerprint": "Fingerprint",
        "th_output_preview": "Sampled Output Preview",
        "footer": "Generated autonomously by <strong>Attest</strong> (LLM Verification & Anti-Spoofing Engine) • Run ID #{run_id}",
    },
}


def get_html_report_strings(locale: str = "ru") -> dict[str, str]:
    """Returns localized dictionary for rendering HTML reports."""
    loc = normalize_locale(locale)
    return HTML_REPORT_STRINGS.get(loc, HTML_REPORT_STRINGS["ru"])
