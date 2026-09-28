"""
Target and estimation subcommands for Attest CLI.
"""

from __future__ import annotations

import click
from rich.console import Console

from attest.battery.loader import estimate_battery_cost, load_battery
from attest.config import load_config
from attest.db import Database
from attest.models import Target
from attest.reporting.console import print_targets_table
from attest.security import encrypt_api_key, mask_key, resolve_api_key

console = Console()


@click.group("target")
def target_group():
    """Manage target endpoints to monitor."""


@target_group.command("add")
@click.option(
    "--id", "target_id", required=True, help="Unique identifier, e.g. openrouter-gpt4o"
)
@click.option(
    "--url",
    required=True,
    help="OpenAI-compatible base URL, e.g. https://openrouter.ai/api/v1",
)
@click.option(
    "--model", required=True, help="Claimed canonical model identifier, e.g. gpt-4o"
)
@click.option(
    "--wire-model",
    default=None,
    help="Optional wire model name for API calls (e.g. openai/gpt-4o)",
)
@click.option(
    "--key",
    default=None,
    help="API key (will be encrypted at rest). Or use environment variables.",
)
@click.option("--desc", default=None, help="Optional description")
@click.option("--config", "-c", default=None, help="Config path")
def cmd_target_add(
    target_id: str,
    url: str,
    model: str,
    wire_model: str | None,
    key: str | None,
    desc: str | None,
    config: str | None,
):
    """Register a new API target."""
    cfg = load_config(config)
    db = Database(cfg.database)

    encrypted_key = encrypt_api_key(key) if key else None

    target = Target(
        id=target_id.strip(),
        base_url=url.strip(),
        model=model.strip(),
        wire_model=wire_model.strip() if wire_model else None,
        encrypted_key=encrypted_key,
        description=desc,
    )
    db.save_target(target)

    console.print(f"[bold green]✔[/bold green] Target [cyan]{target_id}[/cyan] saved.")
    resolved_key, source = resolve_api_key(
        target_id, encrypted_key, base_url=target.base_url
    )
    console.print(f"  Model: [green]{model}[/green]")
    console.print(f"  URL: [blue]{url}[/blue]")
    console.print(
        f"  API Key Source: [magenta]{source}[/magenta] ({mask_key(resolved_key)})"
    )
    if not resolved_key:
        console.print(
            f"  [yellow]⚠ Warning:[/yellow] No key set. Set environment variable: "
            f"[bold]ATTEST_API_KEY_{target_id.upper().replace('-', '_')}[/bold] or pass --key"
        )


@target_group.command("list")
@click.option("--config", "-c", default=None, help="Config path")
def cmd_target_list(config: str | None):
    """List all configured targets."""
    cfg = load_config(config)
    db = Database(cfg.database)
    targets = db.list_targets()
    print_targets_table(targets, locale=cfg.locale)


@target_group.command("delete")
@click.argument("target_id")
@click.option("--config", "-c", default=None, help="Config path")
def cmd_target_delete(target_id: str, config: str | None):
    """Delete a target and its associated data."""
    cfg = load_config(config)
    db = Database(cfg.database)
    if db.delete_target(target_id):
        console.print(f"[green]✔[/green] Target [cyan]{target_id}[/cyan] deleted.")
    else:
        console.print(f"[yellow]⚠[/yellow] Target [cyan]{target_id}[/cyan] not found.")


@click.command("estimate")
@click.argument("target_id", required=False)
@click.option("--battery", "-b", default=None, help="Battery file path")
@click.option("--config", "-c", default=None, help="Config path")
def cmd_estimate(target_id: str | None, battery: str | None, config: str | None):
    """Estimate request volume, tokens, and approximate cost for a battery run."""
    cfg = load_config(config)
    battery_file = battery or cfg.battery
    version, prompts = load_battery(battery_file)
    est = estimate_battery_cost(prompts)

    target_str = f" for target '{target_id}'" if target_id else ""
    console.print(
        f"\n[bold cyan]Run Budget Estimation{target_str}[/bold cyan] (Battery: {version}):"
    )
    console.print(f"  Total Prompts:      [bold]{est['total_prompts']}[/bold]")
    console.print(f"  Total HTTP Queries: [bold]{est['total_requests']}[/bold]")
    console.print(f"  Est. Prompt Tokens: {est['est_prompt_tokens']:,}")
    console.print(f"  Est. Output Tokens: {est['est_completion_tokens']:,}")
    console.print(
        f"  Est. Total Tokens:  [bold green]{est['est_total_tokens']:,}[/bold green]"
    )
    console.print(
        f"  Est. Dollar Cost:   [bold yellow]~${est['est_cost_usd']:.4f}[/bold yellow] (at standard rates)\n"
    )

    console.print("[dim]Category Breakdown:[/dim]")
    for cat, data in est["by_category"].items():
        console.print(
            f"  • {cat:<12} : {data['requests']:>3} requests, ~{data['tokens']:>6,} tokens"
        )
    console.print()
