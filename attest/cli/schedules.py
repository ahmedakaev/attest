"""
Schedule management subcommands for Attest CLI.
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.table import Table

from attest.config import load_config
from attest.db import Database

console = Console()


@click.group("schedule")
def schedule_group():
    """Manage recurring drift audits and automated monitoring."""


@schedule_group.command("list")
@click.option("--config", "-c", default=None, help="Config path")
def cmd_schedule_list(config: str | None):
    """List all configured recurring drift monitoring schedules."""
    cfg = load_config(config)
    db = Database(cfg.database)
    schedules = db.list_schedules()

    if not schedules:
        console.print(
            "[yellow]No scheduled monitors configured. Add one with: attest schedule add <target_id>[/yellow]"
        )
        return

    table = Table(title="Recurring Drift Schedules")
    table.add_column("ID", style="dim")
    table.add_column("Target ID", style="cyan bold")
    table.add_column("Interval", style="green")
    table.add_column("Battery", style="magenta")
    table.add_column("Status", style="bold")
    table.add_column("Last Run", style="dim")
    table.add_column("Next Run", style="yellow")

    for s in schedules:
        status_str = "[green]ENABLED[/green]" if s.enabled else "[dim]DISABLED[/dim]"
        last_r = s.last_run_at[:19] if s.last_run_at else "Never"
        next_r = s.next_run_at[:19] if s.next_run_at else "Pending"
        table.add_row(
            str(s.id),
            s.target_id,
            f"Every {s.interval_hours}h",
            s.battery,
            status_str,
            last_r,
            next_r,
        )
    console.print(table)


@schedule_group.command("add")
@click.argument("target_id")
@click.option(
    "--interval-hours",
    "-i",
    default=24,
    type=int,
    help="Interval in hours (default: 24)",
)
@click.option(
    "--battery",
    "-b",
    default="quick",
    type=click.Choice(["quick", "anti_spoof", "reasoning", "v1"]),
    help="Battery mode",
)
@click.option("--disabled", is_flag=True, help="Create schedule in disabled state")
@click.option("--config", "-c", default=None, help="Config path")
def cmd_schedule_add(
    target_id: str,
    interval_hours: int,
    battery: str,
    disabled: bool,
    config: str | None,
):
    """Add or update an automated drift schedule for a target."""
    cfg = load_config(config)
    db = Database(cfg.database)

    target = db.get_target(target_id)
    if not target:
        console.print(f"[red]Error:[/red] Target '{target_id}' not found.")
        sys.exit(1)

    baseline, _ = db.resolve_target_baseline(target.id)
    if not baseline:
        console.print(
            f"[yellow]⚠ Warning:[/yellow] Target '{target_id}' has no active baseline. Be sure to capture a snapshot."
        )

    sched_id = db.create_or_update_schedule(
        target_id=target.id,
        interval_hours=interval_hours,
        battery=battery,
        enabled=not disabled,
    )
    console.print(
        f"[green]✔[/green] Schedule [bold]#{sched_id}[/bold] for [cyan]{target_id}[/cyan] set to every [bold]{interval_hours} hours[/bold] ({battery} battery)."
    )


@schedule_group.command("delete")
@click.argument("schedule_id", type=int)
@click.option("--config", "-c", default=None, help="Config path")
def cmd_schedule_delete(schedule_id: int, config: str | None):
    """Delete a recurring schedule by ID."""
    cfg = load_config(config)
    db = Database(cfg.database)
    if db.delete_schedule(schedule_id):
        console.print(f"[green]✔[/green] Schedule #{schedule_id} deleted.")
    else:
        console.print(f"[red]Error:[/red] Schedule #{schedule_id} not found.")
