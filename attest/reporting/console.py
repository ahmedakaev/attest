"""
Rich terminal visualization for Attest CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from attest.comparator.compare import ComparisonResult

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from attest.i18n import (
    format_failure_diagnostics,
    get_method_title,
    get_verdict_label,
    normalize_locale,
)
from attest.models import Baseline, Run, Score, Target, Verdict
from attest.security import mask_key, resolve_api_key

console = Console()


def format_verdict_badge(v: Verdict, locale: str = "ru") -> Text:
    loc = normalize_locale(locale)
    is_ru = loc == "ru"
    if v == Verdict.PASS:
        label = " ПРОЙДЕНО " if is_ru else " PASS "
        return Text(label, style="bold black on green")
    if v == Verdict.WARN:
        label = " ВНИМАНИЕ " if is_ru else " WARN "
        return Text(label, style="bold black on yellow")
    if v == Verdict.FAIL:
        label = " ПРОВАЛЕНО " if is_ru else " FAIL "
        return Text(label, style="bold white on red")
    label = " ПРОПУЩЕНО " if is_ru else " SKIP "
    return Text(label, style="dim")


def print_targets_table(targets: list[Target], locale: str = "ru") -> None:
    loc = normalize_locale(locale)
    is_ru = loc == "ru"

    if not targets:
        empty_msg = (
            "[yellow]Цели не настроены. Добавьте цель с помощью:[/yellow] attest target add --help"
            if is_ru
            else "[yellow]No targets configured. Add one with:[/yellow] attest target add --help"
        )
        console.print(empty_msg)
        return

    title = (
        "Настроенные цели верификации" if is_ru else "Configured Verification Targets"
    )
    table = Table(title=title, box=ROUNDED, header_style="bold cyan")
    table.add_column("ID цели" if is_ru else "Target ID", style="bold white")
    table.add_column("Заявленная модель" if is_ru else "Claimed Model", style="green")
    table.add_column("Базовый URL" if is_ru else "Base URL", style="blue")
    table.add_column("Источник ключа" if is_ru else "API Key Source", style="magenta")
    table.add_column("Маска ключа" if is_ru else "Key Preview", style="dim")

    for t in targets:
        key, source = resolve_api_key(t.id, t.encrypted_key, base_url=t.base_url)
        masked = mask_key(key)
        table.add_row(t.id, t.model, t.base_url, source, masked)

    console.print(table)


def print_run_report(
    target: Target,
    baseline: Baseline,
    run: Run,
    scores: list[Score],
    overall_verdict: Verdict,
    total_samples: int,
    duration_s: float,
    total_tokens: int,
    est_cost_usd: float,
    failure_diagnostics: list[dict[str, Any]] | None = None,
    locale: str = "ru",
) -> None:
    loc = normalize_locale(locale)
    is_ru = loc == "ru"

    # Header Panel
    run_label = "Запуск верификации Attest" if is_ru else "Attest Verification Run"
    title = f"{run_label} #{run.id} — [bold cyan]{target.id}[/bold cyan]"

    infra_s = next((s for s in scores if s.method == "infrastructure"), None)
    infra_line = ""
    if infra_s and infra_s.details:
        inf_txt = (
            infra_s.details.get(f"summary_{loc}")
            or infra_s.details.get("summary_ru")
            or ""
        )
        if inf_txt:
            inf_label = "Инфраструктура:" if is_ru else "Infrastructure:"
            infra_line = f"\n[bold]{inf_label}[/bold] [magenta]{inf_txt}[/magenta]"

    if is_ru:
        meta_text = (
            f"[bold]Заявленная модель:[/bold] {target.model}  |  "
            f"[bold]Эндпоинт:[/bold] {target.base_url}\n"
            f"[bold]Эталон:[/bold] #{baseline.id} (снят {baseline.captured_at[:19]})  |  "
            f"[bold]Батарея:[/bold] {run.battery_version}\n"
            f"[bold]Собрано сэмплов:[/bold] {total_samples}  |  "
            f"[bold]Длительность:[/bold] {duration_s:.1f}с  |  "
            f"[bold]Всего токенов:[/bold] {total_tokens:,} (~${est_cost_usd:.4f})"
            f"{infra_line}"
        )
    else:
        meta_text = (
            f"[bold]Claimed Model:[/bold] {target.model}  |  "
            f"[bold]Endpoint:[/bold] {target.base_url}\n"
            f"[bold]Baseline:[/bold] #{baseline.id} (captured {baseline.captured_at[:19]})  |  "
            f"[bold]Battery:[/bold] {run.battery_version}\n"
            f"[bold]Samples Collected:[/bold] {total_samples}  |  "
            f"[bold]Duration:[/bold] {duration_s:.1f}s  |  "
            f"[bold]Total Tokens:[/bold] {total_tokens:,} (~${est_cost_usd:.4f})"
            f"{infra_line}"
        )

    border_style = (
        "green"
        if overall_verdict == Verdict.PASS
        else ("yellow" if overall_verdict == Verdict.WARN else "red")
    )
    console.print(Panel(meta_text, title=title, border_style=border_style, box=ROUNDED))

    # Detailed Scores Table
    table = Table(box=ROUNDED, header_style="bold white", expand=True)
    table.add_column(
        "Уровень проверки" if is_ru else "Tier / Verification Level", ratio=3
    )
    table.add_column(
        "Значение" if is_ru else "Observed Metric", justify="right", ratio=2
    )
    table.add_column("Порог" if is_ru else "Threshold", justify="right", ratio=2)
    table.add_column("Вердикт" if is_ru else "Verdict", justify="center", ratio=2)
    table.add_column("Диагностика" if is_ru else "Diagnostic Details", ratio=5)

    for s in scores:
        name = get_method_title(s.method, locale=loc)
        metric_str = f"{s.value:.4f}" if isinstance(s.value, float) else str(s.value)
        thresh_str = f"{s.threshold:.2f}" if s.threshold is not None else "—"

        detail_parts = []
        if s.method == "infrastructure":
            inf_txt = s.details.get(f"summary_{loc}") or s.details.get("summary_ru")
            if inf_txt:
                detail_parts.append(inf_txt)
        if s.method == "assertions":
            total = s.details.get("total_assertions", 0)
            passed = s.details.get("passed_assertions", 0)
            fail_count = s.details.get("failure_count", 0)
            if fail_count > 0:
                first_fail = s.details.get("failures", [{}])[0]
                fail_desc = (
                    first_fail.get("message")
                    or f"{first_fail.get('assertion')}: {first_fail.get('expected')}"
                )
                if is_ru:
                    detail_parts.append(
                        f"{passed}/{total} пройдено, {fail_count} сбоев ({fail_desc})"
                    )
                else:
                    detail_parts.append(
                        f"{passed}/{total} passed, {fail_count} failed ({fail_desc})"
                    )
            else:
                detail_parts.append(
                    f"все {passed}/{total} правил пройдены"
                    if is_ru
                    else f"all {passed}/{total} rules passed"
                )
        if s.details.get("message"):
            detail_parts.append(str(s.details["message"]))
        if "mean_jsd" in s.details:
            detail_parts.append(
                f"cells: {s.details.get('num_probe_cells', 0)}, max JSD: {s.details.get('max_jsd', 0)}"
            )
        if "by_category" in s.details:
            detail_parts.append(
                "categories: "
                + ", ".join(f"{k}={v}" for k, v in s.details["by_category"].items())
            )
        if "p_value" in s.details:
            detail_parts.append(
                f"p-val: {s.details['p_value']}, MMD: {s.details.get('observed_mmd')}"
            )

        ok_label = "НОРМА" if is_ru else "OK"
        v_name = get_verdict_label(s.verdict, locale=loc)
        detail_text = "; ".join(detail_parts) or (
            ok_label if s.verdict == Verdict.PASS else v_name
        )
        badge = format_verdict_badge(s.verdict, locale=loc)
        table.add_row(name, metric_str, thresh_str, badge, detail_text)

    console.print(table)

    # Failure Diagnostics Panel (Explaining what failed and why)
    active_diagnostics = failure_diagnostics
    if active_diagnostics is None and overall_verdict in (Verdict.WARN, Verdict.FAIL):
        active_diagnostics = format_failure_diagnostics(scores, locale=loc)

    if active_diagnostics:
        panel_title = (
            "🚨 Диагностика сбоев (Что пошло не так)"
            if is_ru
            else "🚨 Failure Diagnostics (Root Cause)"
        )
        diag_blocks = []
        for i, d in enumerate(active_diagnostics, 1):
            prompt_label = "Промпт" if is_ru else "Prompt"
            p_text = (
                f" [bold cyan][{prompt_label} #{d['prompt_id']}][/bold cyan]"
                if d.get("prompt_id")
                else ""
            )
            if d.get("prompt_preview"):
                p_text += f' [dim]("{d["prompt_preview"]}")[/dim]'
            diag_blocks.append(
                f"[bold red]{i}.[/bold red] [bold yellow]{d['title']}[/bold yellow]{p_text}\n   ↳ {d['message']}"
            )
        console.print()
        console.print(
            Panel(
                "\n\n".join(diag_blocks),
                title=panel_title,
                border_style="red",
                box=ROUNDED,
            )
        )

    # Final Verdict Footer
    if overall_verdict == Verdict.PASS:
        footer_style = "bold white on green"
        msg = (
            " ✔ ИТОГОВЫЙ ВЕРДИКТ: ПРОЙДЕНО — Сигнатура целевого эндпоинта полностью соответствует эталону в пределах допусков. "
            if is_ru
            else " ✔ OVERALL VERDICT: PASSED — Target endpoint matches baseline signature within normal tolerances. "
        )
    elif overall_verdict == Verdict.WARN:
        footer_style = "bold black on yellow"
        msg = (
            " ⚠ ИТОГОВЫЙ ВЕРДИКТ: ВНИМАНИЕ — Зафиксирован дрейф распределений или изменение инфраструктуры. "
            if is_ru
            else " ⚠ OVERALL VERDICT: WARNING — Infrastructure changes or minor distribution drift detected. "
        )
    else:
        footer_style = "bold white on red"
        msg = (
            " ✖ ИТОГОВЫЙ ВЕРДИКТ: ПРОВАЛЕНО — Целевой эндпоинт существенно отклоняется от эталона! Вероятна подмена модели. "
            if is_ru
            else " ✖ OVERALL VERDICT: FAILED — Target endpoint deviates significantly from baseline! Possible model substitution. "
        )

    console.print()
    console.print(Text(msg, style=footer_style, justify="center"))
    console.print()


def print_comparison_report(result: ComparisonResult, locale: str = "ru") -> None:
    """Print side-by-side provider battle comparison table and recommendation."""

    loc = normalize_locale(locale)
    is_ru = loc == "ru"

    ra = result.run_a
    rb = result.run_b

    title = (
        f"⚔️ [bold white]Битва провайдеров (Provider Battle):[/bold white] "
        f"[cyan]{ra.target_id}[/cyan] vs [magenta]{rb.target_id}[/magenta]"
        if is_ru
        else f"⚔️ [bold white]Provider Battle:[/bold white] [cyan]{ra.target_id}[/cyan] vs [magenta]{rb.target_id}[/magenta]"
    )

    table = Table(title=title, box=ROUNDED, header_style="bold white", expand=True)
    table.add_column(
        "Метрика / Параметр" if is_ru else "Metric / Parameter",
        style="bold white",
        ratio=3,
    )
    table.add_column(
        f"Провайдер A (#{ra.run_id})\n[cyan]{ra.target_id}[/cyan]",
        justify="center",
        ratio=3,
    )
    table.add_column(
        f"Провайдер B (#{rb.run_id})\n[magenta]{rb.target_id}[/magenta]",
        justify="center",
        ratio=3,
    )
    table.add_column(
        "Сравнение / Дельта" if is_ru else "Delta / Comparison",
        justify="center",
        ratio=3,
    )

    # Basic metadata
    table.add_row(
        "Заявленная модель" if is_ru else "Claimed Model",
        ra.claimed_model,
        rb.claimed_model,
        "Идентичны" if ra.claimed_model == rb.claimed_model else "Разные",
    )
    table.add_row(
        "Фактическая модель" if is_ru else "Returned Wire Model",
        ra.model_returned or "—",
        rb.model_returned or "—",
        "Идентичны"
        if ra.model_returned == rb.model_returned
        else "[yellow]Различаются[/yellow]",
    )

    # Infrastructure
    infra_a = ra.infrastructure.summary(loc)
    infra_b = rb.infrastructure.summary(loc)
    table.add_row(
        "Инфраструктура / Шлюз" if is_ru else "Infrastructure / Gateway",
        infra_a,
        infra_b,
        "—",
    )

    # Throughput (TPS)
    tps_a = ra.median_tps
    tps_b = rb.median_tps
    mult = result.deltas.get("tps_multiplier_b_vs_a", 1.0)
    if tps_b > tps_a:
        delta_tps = (
            f"[green]Провайдер B в {mult}x быстрее[/green]"
            if is_ru
            else f"[green]Provider B is {mult}x faster[/green]"
        )
    elif tps_a > tps_b:
        inv_mult = round(tps_a / tps_b, 2) if tps_b > 0 else 1.0
        delta_tps = (
            f"[green]Провайдер A в {inv_mult}x быстрее[/green]"
            if is_ru
            else f"[green]Provider A is {inv_mult}x faster[/green]"
        )
    else:
        delta_tps = "Одинаково" if is_ru else "Equal"

    table.add_row(
        "Скорость генерации (TPS median)" if is_ru else "Throughput (TPS median)",
        f"{tps_a:.1f} tok/s",
        f"{tps_b:.1f} tok/s",
        delta_tps,
    )

    # Latency
    lat_a = ra.median_latency_ms
    lat_b = rb.median_latency_ms
    diff_lat = round(lat_b - lat_a, 1)
    if diff_lat < 0:
        delta_lat = (
            f"[green]B быстрее на {abs(diff_lat):.0f}мс[/green]"
            if is_ru
            else f"[green]B is {abs(diff_lat):.0f}ms faster[/green]"
        )
    elif diff_lat > 0:
        delta_lat = (
            f"[green]A быстрее на {diff_lat:.0f}мс[/green]"
            if is_ru
            else f"[green]A is {diff_lat:.0f}ms faster[/green]"
        )
    else:
        delta_lat = "Одинаково" if is_ru else "Equal"

    table.add_row(
        "Задержка ответа (Latency median)" if is_ru else "Latency (Median TTFT)",
        f"{lat_a:.0f} ms",
        f"{lat_b:.0f} ms",
        delta_lat,
    )

    table.add_row(
        "P95 задержка" if is_ru else "P95 Latency",
        f"{ra.p95_latency_ms:.0f} ms",
        f"{rb.p95_latency_ms:.0f} ms",
        "—",
    )

    # Assertions
    table.add_row(
        "Логические ассерты (% pass)" if is_ru else "Logic Assertions (% pass)",
        f"{ra.assertion_passed}/{ra.assertion_total} ({ra.assertion_pass_rate:.0f}%)",
        f"{rb.assertion_passed}/{rb.assertion_total} ({rb.assertion_pass_rate:.0f}%)",
        "100% совпадение"
        if ra.assertion_pass_rate == rb.assertion_pass_rate == 100.0
        else "Расхождение",
    )

    # JSD
    jsd_a_str = f"{ra.jsd_score:.4f}" if ra.jsd_score is not None else "—"
    jsd_b_str = f"{rb.jsd_score:.4f}" if rb.jsd_score is not None else "—"
    table.add_row(
        "JSD к эталону (One-Token)" if is_ru else "JSD to Baseline (One-Token)",
        jsd_a_str,
        jsd_b_str,
        "—",
    )

    # Overall Verdict
    badge_a = format_verdict_badge(ra.overall_verdict, locale=loc)
    badge_b = format_verdict_badge(rb.overall_verdict, locale=loc)
    table.add_row(
        "Итоговый вердикт" if is_ru else "Overall Verdict",
        badge_a,
        badge_b,
        "—",
    )

    console.print(table)

    # Winner / Recommendation Panel
    rec_text = result.recommendation_ru if is_ru else result.recommendation_en
    panel_title = "🏆 Рекомендация Attest" if is_ru else "🏆 Attest Recommendation"
    border = "green" if result.winner in ("a", "b") else "cyan"
    console.print()
    console.print(
        Panel(
            f"[bold]{rec_text}[/bold]",
            title=panel_title,
            border_style=border,
            box=ROUNDED,
        )
    )
    console.print()
