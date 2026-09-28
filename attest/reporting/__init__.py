"""
Reporting module for Attest.
"""

from attest.reporting.console import (
    print_comparison_report,
    print_run_report,
    print_targets_table,
)
from attest.reporting.dispute import format_dispute_markdown, generate_dispute_pack
from attest.reporting.html import build_html_report, generate_html_report

__all__ = [
    "build_html_report",
    "format_dispute_markdown",
    "generate_dispute_pack",
    "generate_html_report",
    "print_comparison_report",
    "print_run_report",
    "print_targets_table",
]
