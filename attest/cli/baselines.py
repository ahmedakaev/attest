"""
Baseline management subcommand for Attest CLI.
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from attest.config import load_config
from attest.db import Database
from attest.models import BaselineStatus
from attest.security import resolve_api_key
from attest.service import AttestService

console = Console()


@click.command("baseline")
@click.argument("action", type=click.Choice(["capture", "list", "reseal"]))
@click.argument("target_id", required=False)
@click.option(
    "--note", "-n", default=None, help="Reason/context for capturing baseline"
)
@click.option("--battery", "-b", default=None, help="Battery file path")
@click.option("--config", "-c", default=None, help="Config path")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def cmd_baseline(
    action: str,
    target_id: str | None,
    note: str | None,
    battery: str | None,
    config: str | None,
    yes: bool,
):
    """
    Manage reference baselines.

    'capture <target_id>' freezes a reference snapshot at moment T0 (requires confirmation).
    'list [target_id]' displays historical baselines.
    'reseal' upgrades baselines from older Attest versions to the keyed HMAC seal.
    """
    cfg = load_config(config)
    db = Database(cfg.database)

    if action == "reseal":
        console.print(
            "[yellow]Resealing marks the current contents of legacy baselines as trusted.[/yellow]"
        )
        if not yes and not click.confirm("Proceed?", default=False):
            return
        count = db.reseal_legacy_baselines()
        console.print(f"[green]✔[/green] Resealed {count} baseline(s) with HMAC-SHA256.")
        return

    if action == "list":
        if target_id:
            targets = [db.get_target(target_id)]
            if not targets[0]:
                console.print(
                    f"[red]Error:[/red] Target [bold]{target_id}[/bold] not found."
                )
                sys.exit(1)
        else:
            targets = db.list_targets()

        if not targets:
            console.print("[yellow]No targets found.[/yellow]")
            return

        for t in targets:
            if t is None:
                continue
            baselines = db.list_baselines(t.id)
            if not baselines:
                console.print(f"[dim]No baselines for {t.id}[/dim]")
                continue
            console.print(f"\n[bold cyan]Baselines for {t.id} ({t.model}):[/bold cyan]")
            for b in baselines:
                is_active = (
                    b.status == BaselineStatus.ACTIVE
                    or b.status == BaselineStatus.ACTIVE.value
                    or str(b.status).lower() == "active"
                )
                status_str = (
                    b.status.value
                    if isinstance(b.status, BaselineStatus)
                    else str(b.status)
                )
                status_style = "bold green" if is_active else "dim"
                console.print(
                    f"  #{b.id} [{status_style}]{status_str.upper()}[/{status_style}] "
                    f"captured: {b.captured_at[:19]} (Battery: {b.battery_version}) — {b.notes or 'No notes'}"
                )
        console.print()
        return

    # Capture Action requires target_id
    if not target_id:
        console.print(
            "[red]Error:[/red] target_id is required for baseline capture: attest baseline capture <target_id>"
        )
        sys.exit(1)

    target = db.get_target(target_id)
    if not target:
        console.print(f"[red]Error:[/red] Target [bold]{target_id}[/bold] not found.")
        sys.exit(1)

    # Capture Action
    service = AttestService(db=db, config=cfg)
    battery_file = battery or cfg.battery

    try:
        est = service.estimate_battery(battery_file)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error loading battery:[/red] {e}")
        sys.exit(1)

    api_key, _key_source = resolve_api_key(
        target.id, target.encrypted_key, base_url=target.base_url
    )
    if not api_key:
        console.print(
            f"[red]Error:[/red] No API key available for target '{target_id}'."
        )
        sys.exit(1)

    if not yes:
        console.print(
            f"\n[bold yellow]Capturing Baseline for {target.id} ({target.model})[/bold yellow]"
        )
        console.print(
            f"This will execute [bold]{est['total_requests']}[/bold] requests (~{est['est_total_tokens']:,} tokens, ~${est['est_cost_usd']:.4f})."
        )
        console.print(
            "[dim]A baseline freezes trusted ground truth behavior for all future drift comparisons.[/dim]"
        )
        if not click.confirm("Proceed with capturing baseline?", default=True):
            console.print("[yellow]Baseline capture cancelled.[/yellow]")
            return

    total_reqs = est["total_requests"]
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Sampling {target.id}...", total=total_reqs)
        try:
            res = service.capture_baseline(
                target=target,
                battery_path=battery_file,
                note=note,
                on_sample_done=lambda s: progress.advance(task),
            )
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Error during baseline capture:[/red] {e}")
            sys.exit(1)

    console.print(
        f"\n[bold green]✔ Baseline #{res.baseline_id} captured successfully![/bold green] "
        f"({len(res.samples)} samples saved into database)\n"
    )
