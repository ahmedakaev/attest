"""
Reporting and dispute export subcommands for Attest CLI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from attest.config import load_config
from attest.db import Database
from attest.models import Baseline, Target, Verdict
from attest.reporting.console import print_run_report
from attest.reporting.dispute import generate_dispute_pack
from attest.reporting.history import build_target_history
from attest.reporting.html import generate_html_report
from attest.utils import calculate_token_cost

console = Console()


@click.group("report")
def report_group():
    """View verification reports and history."""


@report_group.command("latest")
@click.argument("target_id")
@click.option("--config", "-c", default=None, help="Config path")
@click.option(
    "--locale",
    "-l",
    type=click.Choice(["ru", "en"], case_sensitive=False),
    default=None,
    help="Report language ('ru' or 'en')",
)
@click.option("--html", default=None, help="Generate HTML report file")
def cmd_report_latest(
    target_id: str, config: str | None, locale: str | None, html: str | None
):
    """View the report for the latest run of a target."""
    cfg = load_config(config)
    if locale:
        cfg = cfg.model_copy(update={"locale": locale.lower()})
    db = Database(cfg.database)
    target = db.get_target(target_id)
    if not target:
        console.print(f"[red]Error:[/red] Target [bold]{target_id}[/bold] not found.")
        sys.exit(1)

    latest_run = db.get_latest_run(target_id)
    if not latest_run or latest_run.id is None:
        console.print(f"[yellow]No runs found for target '{target_id}'.[/yellow]")
        return

    baseline = db.get_baseline(latest_run.baseline_id)
    if not baseline:
        console.print(
            f"[red]Error:[/red] Baseline #{latest_run.baseline_id} not found."
        )
        sys.exit(1)

    scores = db.get_scores(latest_run.id)
    run_samples = db.get_run_samples(latest_run.id)

    # Compute overall verdict from stored scores via domain aggregate
    overall = Verdict.aggregate(scores)

    total_tokens = sum(
        (s.usage.get("total_tokens", 0) if s.usage else (len(s.raw_text) // 3))
        for s in run_samples
    )
    est_cost = calculate_token_cost(total_tokens, cfg.cost.cost_per_million_tokens)

    print_run_report(
        target=target,
        baseline=baseline,
        run=latest_run,
        scores=scores,
        overall_verdict=overall,
        total_samples=len(run_samples),
        duration_s=0.0,
        total_tokens=total_tokens,
        est_cost_usd=est_cost,
        locale=cfg.locale,
    )

    if html:
        out_html = generate_html_report(
            target=target,
            baseline=baseline,
            run=latest_run,
            scores=scores,
            overall_verdict=overall,
            output_path=html,
            samples=run_samples,
            locale=cfg.locale,
        )
        console.print(
            f"[green]✔[/green] HTML report saved to: [bold]{out_html}[/bold]\n"
        )


@report_group.command("history")
@click.argument("target_id")
@click.option("--limit", "-n", default=30, show_default=True, help="Last N runs")
@click.option("--json", "as_json", is_flag=True, help="Print raw JSON")
@click.option("--config", "-c", default=None, help="Config path")
def cmd_report_history(target_id: str, limit: int, as_json: bool, config: str | None):
    """Show how TTFT, speed and billing of a target moved across runs."""
    cfg = load_config(config)
    db = Database(cfg.database)
    if not db.get_target(target_id):
        console.print(f"[red]Error:[/red] Target [bold]{target_id}[/bold] not found.")
        sys.exit(1)

    history = build_target_history(db, target_id, limit=limit)
    if as_json:
        click.echo(json.dumps(history, ensure_ascii=False, indent=2))
        return
    if not history:
        console.print(f"[yellow]No runs found for target '{target_id}'.[/yellow]")
        return

    def num(value: float | None, fmt: str = "{:.0f}") -> str:
        return "—" if value is None else fmt.format(value)

    def pct(value: float | None) -> str:
        return "—" if value is None else f"{value * 100:+.0f}%"

    colors = {"PASS": "green", "WARN": "yellow", "FAIL": "red", "SKIP": "dim"}
    table = Table(title=f"History: {target_id} (oldest first)")
    for col, justify in (
        ("Run", "right"),
        ("Date", "left"),
        ("Verdict", "left"),
        ("TTFT, ms", "right"),
        ("Tok/s", "right"),
        ("Latency, ms", "right"),
        ("Overcharge", "right"),
        ("IRIS rerouted ≥", "right"),
    ):
        table.add_column(col, justify=justify)
    for h in history:
        color = colors.get(h["verdict"], "white")
        table.add_row(
            f"#{h['run_id']}",
            (h["started_at"] or "")[:16].replace("T", " "),
            f"[{color}]{h['verdict']}[/{color}]",
            num(h["ttft_ms"]),
            num(h["tps"], "{:.1f}") + ("" if h["tps_decode_only"] else "*"),
            num(h["latency_ms"]),
            pct(h["overcharge"]),
            "—" if h["iris_dilution"] is None else f"{h['iris_dilution'] * 100:.0f}%",
        )
    console.print(table)
    console.print(
        "[dim]* end-to-end speed (run was not streamed, no TTFT); "
        "other rows are decode speed after the first token.[/dim]"
    )


@report_group.command("export")
@click.argument("run_id", type=int)
@click.option(
    "--json",
    "json_path",
    default=None,
    help="Export forensic evidence packet to JSON file",
)
@click.option(
    "--html",
    "html_path",
    default=None,
    help="Export printable dispute report to HTML file",
)
@click.option(
    "--markdown",
    "-m",
    "md_path",
    default=None,
    help="Export formal vendor dispute notice to Markdown file",
)
@click.option(
    "--locale",
    "-l",
    type=click.Choice(["ru", "en"], case_sensitive=False),
    default=None,
    help="Report language ('ru' or 'en')",
)
@click.option("--config", "-c", default=None, help="Config path")
def cmd_report_export(
    run_id: int,
    json_path: str | None,
    html_path: str | None,
    md_path: str | None,
    locale: str | None,
    config: str | None,
):
    """Export verification run as JSON evidence pack, dispute HTML, or formal Markdown letter."""
    cfg = load_config(config)
    if locale:
        cfg = cfg.model_copy(update={"locale": locale.lower()})
    db = Database(cfg.database)

    run_obj = db.get_run(run_id)
    if not run_obj:
        console.print(f"[red]Error:[/red] Run #{run_id} not found.")
        sys.exit(1)

    target = db.get_target(run_obj.target_id)
    baseline = db.get_baseline(run_obj.baseline_id)
    scores = db.get_scores(run_id)
    samples = db.get_run_samples(run_id)

    overall = Verdict.aggregate(scores)

    if not json_path and not html_path and not md_path:
        console.print(
            "[yellow]Specify at least one output format: --json <path>, --html <path>, or --markdown <path>[/yellow]"
        )
        return

    if html_path:
        out_html = generate_html_report(
            target=target or Target(id=run_obj.target_id, base_url="—", model="—"),
            baseline=baseline
            or Baseline(
                id=run_obj.baseline_id,
                target_id=run_obj.target_id,
                battery_version="—",
                captured_at="—",
            ),
            run=run_obj,
            scores=scores,
            overall_verdict=overall,
            output_path=html_path,
            samples=samples,
            locale=cfg.locale,
        )
        console.print(
            f"[green]✔[/green] Printable HTML dispute report saved to: [bold]{out_html}[/bold]"
        )

    if md_path:
        pack = generate_dispute_pack(db, run_id, locale=cfg.locale)
        out_md = Path(md_path)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(pack["dispute_letter_markdown"], encoding="utf-8")
        console.print(
            f"[green]✔[/green] Formal dispute letter saved to: [bold]{out_md}[/bold]"
        )

    if json_path:
        pack = generate_dispute_pack(db, run_id, locale=cfg.locale)
        out_p = Path(json_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(pack, f, indent=2, ensure_ascii=False)
        console.print(
            f"[green]✔[/green] Forensic JSON evidence pack saved to: [bold]{out_p}[/bold]"
        )
