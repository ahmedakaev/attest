"""
Verification and auditing subcommands for Attest CLI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from attest.config import AttestConfig, load_config
from attest.db import Database
from attest.models import RunTrigger, Target, Verdict
from attest.reporting.console import print_run_report
from attest.reporting.html import generate_html_report
from attest.service import (
    AttestService,
    BaselineIntegrityError,
    BaselineNotFoundError,
)

console = Console()


def _audit_single_target(
    target: Target,
    cfg: AttestConfig,
    db: Database,
    battery_file: str,
    mmd: bool,
    html: str | None,
    against: str | None = None,
) -> int:
    service = AttestService(db=db, config=cfg)
    try:
        est = service.estimate_battery(battery_file)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error loading battery:[/red] {e}")
        return 1

    total_reqs = est["total_requests"]

    # Pre-check baseline resolution for helpful CLI warnings
    baseline, source_desc = db.resolve_target_baseline(
        target.id, against_target_or_model=against
    )
    if not baseline or baseline.id is None:
        console.print(
            f"[yellow]Skipping '{target.id}':[/yellow] No active baseline found for target or model '{target.model}'.\n"
            f"Run [bold cyan]attest baseline capture <target>[/bold cyan] or pass [bold cyan]--against <reference_target>[/bold cyan] first."
        )
        return 0

    if baseline.target_id != target.id:
        console.print(
            f"[bold cyan]Cross-Provider Reference:[/bold cyan] Auditing against reference baseline #{baseline.id} "
            f"({source_desc})"
        )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Auditing {target.id}...", total=total_reqs)
        try:
            res = service.audit_target(
                target=target,
                battery_path=battery_file,
                mmd=mmd,
                against=against,
                trigger=RunTrigger.MANUAL,
                on_sample_done=lambda s: progress.advance(task),
            )
        except BaselineIntegrityError as e:
            console.print(
                f"[bold red]Integrity Error:[/bold red] {e}\n"
                "[yellow]Baseline tampering or database corruption detected. Audit aborted.[/yellow]"
            )
            return 1
        except BaselineNotFoundError as e:
            console.print(f"[yellow]Skipping '{target.id}':[/yellow] {e}")
            return 0
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Error:[/red] {e}")
            return 1

    print_run_report(
        target=target,
        baseline=res.baseline,
        run=res.run,
        scores=res.scores,
        overall_verdict=res.overall_verdict,
        total_samples=len(res.run_samples),
        duration_s=res.duration_s,
        total_tokens=res.total_tokens,
        est_cost_usd=res.est_cost_usd,
        failure_diagnostics=res.failure_diagnostics,
        locale=cfg.locale,
    )

    if html:
        out_html = generate_html_report(
            target=target,
            baseline=res.baseline,
            run=res.run,
            scores=res.scores,
            overall_verdict=res.overall_verdict,
            output_path=html,
            failure_diagnostics=res.failure_diagnostics,
            locale=cfg.locale,
        )
        console.print(
            f"[green]✔[/green] HTML report saved to: [bold]{out_html}[/bold]\n"
        )

    if (
        cfg.alerting.webhook_url
        and res.overall_verdict in (Verdict.WARN, Verdict.FAIL)
        and not res.alert_dispatched
    ):
        console.print(
            f"[dim]Webhook alert suppressed: consecutive failures ({res.streak}) < threshold ({cfg.alerting.consecutive_fails_before_alert})[/dim]"
        )

    if res.overall_verdict == Verdict.FAIL:
        return 2
    if res.overall_verdict == Verdict.WARN:
        return 1
    return 0


@click.command("run")
@click.argument("target_id", required=False)
@click.option(
    "--all",
    "run_all",
    is_flag=True,
    help="Run verification across all configured targets",
)
@click.option(
    "--against",
    default=None,
    help="Reference target ID, model name, or baseline #ID to audit against",
)
@click.option("--battery", "-b", default=None, help="Battery file path")
@click.option("--config", "-c", default=None, help="Config path")
@click.option(
    "--locale",
    "-l",
    type=click.Choice(["ru", "en"], case_sensitive=False),
    default=None,
    help="Language for output and reports ('ru' or 'en')",
)
@click.option("--mmd", is_flag=True, help="Force Level 3 MMD permutation test")
@click.option("--html", default=None, help="Save report to HTML file")
def cmd_run(
    target_id: str | None,
    run_all: bool,
    against: str | None,
    battery: str | None,
    config: str | None,
    locale: str | None,
    mmd: bool,
    html: str | None,
):
    """
    Run behavioral verification audit against target's active baseline (or reference baseline).
    Exits with code 0 (PASS), 1 (WARN), or 2 (FAIL).
    """
    cfg = load_config(config)
    if locale:
        cfg = cfg.model_copy(update={"locale": locale.lower()})
    db = Database(cfg.database)

    targets_to_run: list[Target] = []
    if run_all:
        targets_to_run = db.list_targets()
        if not targets_to_run:
            console.print("[yellow]No targets configured to run.[/yellow]")
            sys.exit(0)
    elif target_id:
        target = db.get_target(target_id)
        if not target:
            console.print(
                f"[red]Error:[/red] Target [bold]{target_id}[/bold] not found."
            )
            sys.exit(1)
        targets_to_run = [target]
    else:
        console.print(
            "[red]Error:[/red] Specify a target ID or use --all: attest run <target_id> or attest run --all"
        )
        sys.exit(1)

    worst_exit_code = 0
    battery_file = battery or cfg.battery

    for target in targets_to_run:
        target_html = html
        if html and len(targets_to_run) > 1:
            target_html = f"{Path(html).stem}_{target.id}{Path(html).suffix}"

        code = _audit_single_target(
            target=target,
            cfg=cfg,
            db=db,
            battery_file=battery_file,
            mmd=mmd,
            html=target_html,
            against=against,
        )
        worst_exit_code = max(worst_exit_code, code)

    sys.exit(worst_exit_code)
