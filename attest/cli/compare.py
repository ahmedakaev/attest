"""
Comparative analysis (Provider Battle) subcommand for Attest CLI.
"""

from __future__ import annotations

import click
from rich.console import Console

from attest.comparator.compare import compare_runs
from attest.config import load_config
from attest.db import Database
from attest.reporting.console import print_comparison_report

console = Console()


@click.command("compare")
@click.argument("run_a", required=False, type=int)
@click.argument("run_b", required=False, type=int)
@click.option(
    "--target-a",
    default=None,
    help="Target A identifier (uses its latest completed run)",
)
@click.option(
    "--target-b",
    default=None,
    help="Target B identifier (uses its latest completed run)",
)
@click.option("--config", "-c", default=None, help="Path to attest.yaml config")
@click.option("--locale", "-l", default=None, help="Language: 'ru' or 'en'")
def cmd_compare(
    run_a: int | None,
    run_b: int | None,
    target_a: str | None,
    target_b: str | None,
    config: str | None,
    locale: str | None,
):
    """Side-by-side comparative analysis (Provider Battle) between two runs or targets."""
    cfg = load_config(config)
    db = Database(cfg.database)
    loc = locale or cfg.locale

    run_id_a = run_a
    run_id_b = run_b

    if target_a:
        runs_a = db.list_runs(target_id=target_a, limit=50)
        completed_a = [
            r
            for r in runs_a
            if getattr(r.status, "value", str(r.status)).lower() == "completed"
            or str(r.status).lower().endswith("completed")
        ]
        if not completed_a:
            console.print(
                f"[red]Error:[/red] No completed runs found for target '{target_a}'."
            )
            return
        run_id_a = completed_a[0].id

    if target_b:
        runs_b = db.list_runs(target_id=target_b, limit=50)
        completed_b = [
            r
            for r in runs_b
            if getattr(r.status, "value", str(r.status)).lower() == "completed"
            or str(r.status).lower().endswith("completed")
        ]
        if not completed_b:
            console.print(
                f"[red]Error:[/red] No completed runs found for target '{target_b}'."
            )
            return
        run_id_b = completed_b[0].id

    if run_id_a is None or run_id_b is None:
        console.print(
            "[red]Error:[/red] Provide either two run IDs (`attest compare <run_a> <run_b>`) "
            "or targets (`attest compare --target-a <t1> --target-b <t2>`)."
        )
        return

    try:
        result = compare_runs(db, run_id_a, run_id_b)
    except (ValueError, RuntimeError, KeyError) as e:
        console.print(f"[red]Comparison error:[/red] {e}")
        return

    print_comparison_report(result, locale=loc)
