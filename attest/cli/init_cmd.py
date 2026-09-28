"""
Init subcommand for Attest CLI.
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from attest.config import create_default_config_file
from attest.db import Database
from attest.security import get_or_create_master_key

console = Console()


@click.command("init")
@click.option(
    "--config", "-c", default="attest.yaml", help="Path for generated attest.yaml"
)
@click.option("--db", "-d", default="attest.db", help="Path for SQLite database")
def cmd_init(config: str, db: str):
    """Initialize Attest workspace: config file, SQLite schema, master encryption key."""
    cfg_path = Path(config)
    if not cfg_path.exists():
        create_default_config_file(cfg_path, database_path=db)
        console.print(
            f"[green]✔[/green] Created configuration file: [bold]{cfg_path}[/bold]"
        )
    else:
        console.print(
            f"[yellow]ℹ[/yellow] Configuration file already exists: [bold]{cfg_path}[/bold]"
        )

    get_or_create_master_key()
    console.print("[green]✔[/green] Encryption master key active.")

    database = Database(db)
    console.print(
        f"[green]✔[/green] Database initialized at: [bold]{database.db_path}[/bold]"
    )

    # Ensure default battery exists locally
    battery_path = Path("batteries/v1.yaml")
    if not battery_path.exists():
        battery_path.parent.mkdir(parents=True, exist_ok=True)
        bundled = (
            Path(__file__).resolve().parent.parent / "battery" / "default_battery.yaml"
        )
        if bundled.exists():
            with (
                open(bundled, "r", encoding="utf-8") as src,
                open(battery_path, "w", encoding="utf-8") as dst,
            ):
                dst.write(src.read())
        console.print(
            f"[green]✔[/green] Created prompt battery: [bold]{battery_path}[/bold]"
        )
    else:
        console.print(
            f"[green]✔[/green] Default prompt battery ready: [bold]{battery_path}[/bold]"
        )

    console.print("\n[bold green]Attest is ready![/bold green] Next steps:")
    console.print(
        "  1. Add a target: [cyan]attest target add --id gpt4o --url https://api.openai.com/v1 --model gpt-4o[/cyan]"
    )
    console.print("  2. Capture baseline: [cyan]attest baseline capture gpt4o[/cyan]")
    console.print("  3. Run verification: [cyan]attest run gpt4o[/cyan]\n")
