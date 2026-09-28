"""
Web Dashboard launcher subcommand for Attest CLI.
"""

from __future__ import annotations

import threading
import time
import webbrowser

import click
import uvicorn
from rich.console import Console

from attest.config import load_config
from attest.web.app import create_app

console = Console()


@click.command("ui")
@click.option(
    "--port", "-p", default=5555, type=int, help="Port to run Web UI on (default: 5555)"
)
@click.option(
    "--host", default="127.0.0.1", help="Host interface to bind to (default: 127.0.0.1)"
)
@click.option("--config", "-c", default=None, help="Path to attest.yaml config")
@click.option("--no-browser", is_flag=True, help="Do not automatically open browser")
def cmd_ui(port: int, host: str, config: str | None, no_browser: bool):
    """Launch the Attest Web Dashboard on port 5555."""
    cfg = load_config(config)
    loopback = {"127.0.0.1", "localhost", "::1"}
    if host in ("0.0.0.0", "::"):
        console.print(
            "[yellow]⚠ The dashboard has no authentication. Binding to all interfaces "
            "exposes it (and your stored API keys' spending power) to the network. "
            "Add the hostname clients will use to ATTEST_ALLOWED_HOSTS.[/yellow]"
        )
    elif host not in loopback and host not in cfg.allowed_hosts:
        cfg.allowed_hosts.append(host)
    app = create_app(cfg)

    url = f"http://{host}:{port}"
    console.print(
        f"\n[bold green]✔ Starting Attest Web Dashboard[/bold green] at [bold cyan]{url}[/bold cyan]"
    )
    console.print(f"[dim]Binding on {host}:{port} • Press Ctrl+C to terminate.[/dim]\n")

    if not no_browser:

        def _open():
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")
