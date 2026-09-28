"""
Command-Line Interface for Attest (attest-ai).
Modularized Click root group and entrypoints.
"""

from __future__ import annotations

import click

from attest import __version__
from attest.cli.baselines import cmd_baseline
from attest.cli.compare import cmd_compare
from attest.cli.init_cmd import cmd_init
from attest.cli.reports import report_group
from attest.cli.runs import cmd_run
from attest.cli.schedules import schedule_group
from attest.cli.targets import cmd_estimate, target_group
from attest.cli.ui import cmd_ui


@click.group()
@click.version_option(version=__version__, prog_name="attest")
def cli():
    """Attest: Behavioral Verification & Anti-Spoofing Detector for LLM APIs."""


# Register all subcommands and groups
cli.add_command(cmd_init)
cli.add_command(target_group)
cli.add_command(cmd_estimate)
cli.add_command(cmd_baseline)
cli.add_command(cmd_run)
cli.add_command(cmd_run, "audit")
cli.add_command(report_group)
cli.add_command(schedule_group)
cli.add_command(cmd_compare)
cli.add_command(cmd_ui)


def main():
    cli()


__all__ = ["cli", "main"]


if __name__ == "__main__":
    main()
