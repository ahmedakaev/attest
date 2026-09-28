"""
HTML and Printable PDF Report generator for Attest verification runs.
Self-contained, portable, zero external CDN dependencies, fully print-optimized.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from attest.i18n import (
    format_failure_diagnostics,
    get_html_report_strings,
    get_method_title,
    normalize_locale,
)
from attest.models import Baseline, RawSample, Run, Score, Target, Verdict


def build_html_report(
    target: Target,
    baseline: Baseline,
    run: Run,
    scores: list[Score],
    overall_verdict: Verdict,
    samples: list[RawSample] | None = None,
    failure_diagnostics: list[dict[str, Any]] | None = None,
    locale: str = "ru",
) -> str:
    """Build a standalone, responsive, print-optimized HTML dispute report."""
    loc = normalize_locale(locale)
    strings = get_html_report_strings(loc)

    verdict_colors = {
        Verdict.PASS: "#10b981",
        Verdict.WARN: "#f59e0b",
        Verdict.FAIL: "#ef4444",
        Verdict.SKIP: "#6b7280",
    }
    main_color = verdict_colors.get(overall_verdict, "#3b82f6")

    verdict_badge_bg = {
        Verdict.PASS: "rgba(16, 185, 129, 0.15)",
        Verdict.WARN: "rgba(245, 158, 11, 0.15)",
        Verdict.FAIL: "rgba(239, 68, 68, 0.15)",
        Verdict.SKIP: "rgba(107, 114, 128, 0.15)",
    }.get(overall_verdict, "rgba(59, 130, 246, 0.15)")

    verdict_messages = {
        Verdict.FAIL: strings["verdict_fail"],
        Verdict.WARN: strings["verdict_warn"],
        Verdict.PASS: strings["verdict_pass"],
        Verdict.SKIP: strings["verdict_skip"],
    }

    # Format Score Table Rows
    rows_html = []
    fail_count = 0
    warn_count = 0
    for s in scores:
        if s.verdict == Verdict.FAIL:
            fail_count += 1
        elif s.verdict == Verdict.WARN:
            warn_count += 1

        v_color = verdict_colors.get(s.verdict, "#6b7280")
        method_label = get_method_title(s.method, locale=loc)

        if s.method == "assertions":
            total = s.details.get("total_assertions", 0)
            passed = s.details.get("passed_assertions", 0)
            assert_fail_count = s.details.get("failure_count", 0)
            if assert_fail_count > 0:
                first_fail = s.details.get("failures", [{}])[0]
                fail_desc = (
                    first_fail.get("message")
                    or f"{first_fail.get('assertion')}: {first_fail.get('expected')}"
                )
                fail_label = strings["assertions_failed"].format(
                    passed=passed, total=total, fail_count=assert_fail_count
                )
                details_str = f"<span style='color:#f87171;'>{fail_label}</span>: {html.escape(fail_desc)}"
            else:
                pass_label = strings["assertions_passed"].format(
                    passed=passed, total=total
                )
                details_str = f"<span style='color:#34d399;'>{pass_label}</span>"
        elif s.method == "infrastructure":
            summary_txt = (
                s.details.get(f"summary_{loc}")
                or s.details.get("summary_ru")
                or "Direct connection"
            )
            proxy_g = s.details.get("proxy_gateway")
            upstream_c = s.details.get("upstream_cloud")
            dep_id = s.details.get("deployment_id")
            badge_items = []
            if proxy_g:
                badge_items.append(
                    f"<span style='background:#374151;color:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:0.75rem;font-weight:600;'>Proxy: {html.escape(proxy_g.upper())}</span>"
                )
            if upstream_c:
                badge_items.append(
                    f"<span style='background:#1e3a8a;color:#93c5fd;padding:2px 6px;border-radius:4px;font-size:0.75rem;font-weight:600;'>Cloud: {html.escape(upstream_c.upper())}</span>"
                )
            if dep_id:
                badge_items.append(
                    f"<span style='background:#312e81;color:#c7d2fe;padding:2px 6px;border-radius:4px;font-size:0.75rem;font-weight:600;'>Deploy: {html.escape(dep_id)}</span>"
                )
            badges_html = (
                f"<div style='margin-top:4px;display:flex;gap:6px;flex-wrap:wrap;'>{' '.join(badge_items)}</div>"
                if badge_items
                else ""
            )
            details_str = f"<div>{html.escape(summary_txt)}</div>{badges_html}"
        elif "message" in s.details:
            details_str = html.escape(str(s.details["message"]))
        else:
            details_parts = []
            for k, v in s.details.items():
                if k == "cells":
                    continue
                if isinstance(v, dict):
                    inner = ", ".join(
                        f"{ik}={iv}"
                        for ik, iv in v.items()
                        if ik in ("median", "mean", "p95")
                    )
                    details_parts.append(
                        f"<strong>{html.escape(str(k))}</strong>: ({inner})"
                    )
                else:
                    details_parts.append(
                        f"<strong>{html.escape(str(k))}</strong>: {html.escape(str(v))}"
                    )
            details_str = "; ".join(details_parts)

        val_str = f"{s.value:.4f}" if isinstance(s.value, float) else str(s.value)
        thresh_str = f"{s.threshold:.2f}" if s.threshold is not None else "—"
        rows_html.append(
            f"""
            <tr>
                <td><strong>{html.escape(method_label)}</strong></td>
                <td><span class="scope-tag">{html.escape(s.scope)}</span></td>
                <td class="font-mono">{val_str}</td>
                <td class="font-mono">{thresh_str}</td>
                <td><span class="badge" style="background-color: {v_color};">{s.verdict.value}</span></td>
                <td class="details">{details_str or "—"}</td>
            </tr>
            """
        )

    infra_score = next((s for s in scores if s.method == "infrastructure"), None)
    infra_meta_html = ""
    if infra_score and infra_score.details:
        inf_txt = (
            infra_score.details.get(f"summary_{loc}")
            or infra_score.details.get("summary_ru")
            or ""
        )
        inf_label = "Инфраструктура" if loc == "ru" else "Infrastructure"
        infra_meta_html = f"""
                <div>
                    <div class="meta-label">{inf_label}</div>
                    <div class="meta-value font-mono" style="font-size:0.8rem; color:#a78bfa;">{html.escape(inf_txt)}</div>
                </div>
        """

    # Format Samples Discrepancy Preview if samples are provided
    samples_block = ""
    if samples:
        sample_rows = []
        for smp in samples[:15]:  # Show up to 15 key representative samples
            usage_str = (
                f"{smp.usage.get('total_tokens', '—')} tok" if smp.usage else "—"
            )
            raw_preview = smp.raw_text.strip().replace("\n", " ")[:140]
            if len(smp.raw_text.strip()) > 140:
                raw_preview += "..."
            sample_rows.append(
                f"""
                <tr>
                    <td class="font-mono">#{smp.prompt_id}</td>
                    <td class="font-mono">{smp.latency_ms} ms</td>
                    <td>{usage_str}</td>
                    <td class="font-mono" style="font-size:0.75rem;">{html.escape(smp.fingerprint or "—")}</td>
                    <td style="font-size:0.8rem; color:#cbd5e1;">{html.escape(raw_preview)}</td>
                </tr>
                """
            )

        samples_block = f"""
        <div class="card" style="margin-top: 2rem;">
            <h2>{strings["evidence_title"].format(count=min(len(samples), 15), total=len(samples))}</h2>
            <p class="section-sub">{strings["evidence_sub"]}</p>
            <table>
                <thead>
                    <tr>
                        <th style="width: 80px;">{strings["th_prompt"]}</th>
                        <th style="width: 100px;">{strings["th_latency"]}</th>
                        <th style="width: 90px;">{strings["th_tokens"]}</th>
                        <th style="width: 120px;">{strings["th_fingerprint"]}</th>
                        <th>{strings["th_output_preview"]}</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(sample_rows)}
                </tbody>
            </table>
        </div>
        """

    active_diagnostics = failure_diagnostics
    if active_diagnostics is None and overall_verdict in (Verdict.WARN, Verdict.FAIL):
        active_diagnostics = format_failure_diagnostics(scores, locale=loc)

    diagnostics_html = ""
    if active_diagnostics:
        heading = strings["diag_heading"]
        subheading = strings["diag_subheading"]
        diag_items = []
        for d in active_diagnostics:
            p_badge_text = (
                strings["prompt_badge"].format(prompt_id=d["prompt_id"])
                if d.get("prompt_id")
                else ""
            )
            p_badge = (
                f"<span class='scope-tag' style='background:rgba(59,130,246,0.2);color:#93c5fd;font-size:0.75rem;margin-left:0.5rem;'>{p_badge_text}</span>"
                if p_badge_text
                else ""
            )
            preview_html = (
                f"<div style='font-size:0.8rem;color:var(--text-muted);font-style:italic;margin-top:0.2rem;'>\"{html.escape(d['prompt_preview'])}\"</div>"
                if d.get("prompt_preview")
                else ""
            )
            diag_items.append(
                f"""<div style='background:var(--surface-elevated);border-left:3px solid #ef4444;padding:0.75rem 1rem;border-radius:0 4px 4px 0;'>
                    <div style='font-weight:700;color:#f87171;'>{html.escape(d["title"])}{p_badge}</div>
                    <div style='margin-top:0.25rem;font-size:0.9rem;'>{html.escape(d["message"])}</div>
                    {preview_html}
                </div>"""
            )
        diagnostics_html = f"""
        <div class="card" style="border-left: 4px solid #ef4444; background: rgba(239, 68, 68, 0.04);">
            <h2 style="color: #ef4444; margin-top: 0;">{heading}</h2>
            <p class="section-sub">{subheading}</p>
            <div style="display: flex; flex-direction: column; gap: 0.75rem; margin-top: 1rem;">
                {"".join(diag_items)}
            </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="{loc}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Attest Verification Audit — {html.escape(target.id)} (Run #{run.id})</title>
    <style>
        :root {{
            --bg: #141413;
            --surface: #1c1c1a;
            --surface-elevated: #242421;
            --border: #2d2c28;
            --text: #f5f3ed;
            --text-muted: #a3a096;
            --primary: {main_color};
            --accent-brand: #ff653b;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 2rem;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        .no-print {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.6rem 1.2rem;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            border: 1px solid #4b5563;
            background: #1f2937;
            color: #ffffff;
            text-decoration: none;
            transition: all 0.15s;
        }}
        .btn:hover {{
            background: #374151;
            border-color: #6b7280;
        }}
        .btn-primary {{
            background: #10b981;
            border-color: #059669;
            color: #022c22;
        }}
        .btn-primary:hover {{
            background: #34d399;
        }}
        .header {{
            background: var(--surface);
            border-top: 6px solid var(--primary);
            border-radius: 8px;
            padding: 1.75rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.4);
        }}
        .header-top {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
        }}
        .header h1 {{
            margin: 0 0 0.25rem 0;
            font-size: 1.75rem;
            letter-spacing: -0.02em;
        }}
        .subtitle {{
            color: var(--text-muted);
            font-size: 0.95rem;
            margin: 0;
        }}
        .overall-verdict-badge {{
            display: inline-block;
            padding: 0.5rem 1.25rem;
            border-radius: 6px;
            font-size: 1.1rem;
            font-weight: 800;
            letter-spacing: 0.05em;
            color: {main_color};
            background: {verdict_badge_bg};
            border: 2px solid {main_color};
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1rem;
            margin-top: 1.5rem;
            padding-top: 1.25rem;
            border-top: 1px solid var(--border);
            font-size: 0.88rem;
        }}
        .meta-label {{
            color: var(--text-muted);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.2rem;
        }}
        .meta-value {{
            font-weight: 600;
            word-break: break-all;
        }}
        .dispute-statement {{
            background: var(--surface-elevated);
            border-left: 4px solid var(--primary);
            padding: 1rem 1.25rem;
            border-radius: 0 6px 6px 0;
            margin-bottom: 1.5rem;
            font-size: 0.95rem;
        }}
        .dispute-title {{
            font-weight: 700;
            margin-bottom: 0.35rem;
            color: var(--primary);
        }}
        .card {{
            background: var(--surface);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);
        }}
        .card h2 {{
            margin: 0 0 0.25rem 0;
            font-size: 1.25rem;
        }}
        .section-sub {{
            color: var(--text-muted);
            font-size: 0.85rem;
            margin: 0 0 1rem 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 0.5rem;
        }}
        th, td {{
            padding: 10px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background: #182234;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            font-size: 0.72rem;
            letter-spacing: 0.05em;
        }}
        .scope-tag {{
            font-size: 0.8rem;
            color: #93c5fd;
            background: rgba(59, 130, 246, 0.1);
            padding: 2px 6px;
            border-radius: 4px;
        }}
        .font-mono {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.85rem;
        }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            color: #ffffff;
            font-size: 0.72rem;
            font-weight: 700;
        }}
        .details {{
            font-size: 0.82rem;
            color: var(--text-muted);
        }}
        .footer {{
            text-align: center;
            margin-top: 3rem;
            color: var(--text-muted);
            font-size: 0.8rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border);
        }}

        /* PRINT STYLESHEET (Cmd+P / Ctrl+P / Save as PDF) */
        @media print {{
            :root {{
                --bg: #ffffff;
                --surface: #ffffff;
                --surface-elevated: #f8fafc;
                --border: #cbd5e1;
                --text: #0f172a;
                --text-muted: #64748b;
            }}
            body {{
                background: #ffffff !important;
                color: #0f172a !important;
                padding: 0 !important;
                font-size: 10pt;
            }}
            .container {{
                max-width: 100% !important;
                margin: 0 !important;
            }}
            .no-print {{
                display: none !important;
            }}
            .header, .card {{
                box-shadow: none !important;
                border: 1px solid #cbd5e1 !important;
                page-break-inside: avoid;
                margin-bottom: 1.25rem !important;
            }}
            .dispute-statement {{
                background: #f1f5f9 !important;
                border-left: 4px solid #0f172a !important;
                color: #0f172a !important;
            }}
            th {{
                background: #f1f5f9 !important;
                color: #334155 !important;
            }}
            td {{
                border-bottom: 1px solid #e2e8f0 !important;
            }}
            .scope-tag {{
                background: #f1f5f9 !important;
                color: #1e293b !important;
                border: 1px solid #cbd5e1;
            }}
            .badge {{
                border: 1px solid #334155;
            }}
            table {{
                page-break-inside: auto;
            }}
            tr {{
                page-break-inside: avoid;
                page-break-after: auto;
            }}
            .footer {{
                color: #64748b !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="no-print">
            <a href="/" class="btn">{strings["back_btn"]}</a>
            <div style="display: flex; gap: 0.75rem;">
                <button type="button" class="btn btn-primary" onclick="window.print()">
                    {strings["print_btn"]}
                </button>
            </div>
        </div>

        <div class="header">
            <div class="header-top">
                <div>
                    <h1>{strings["title"]}</h1>
                    <p class="subtitle">{strings["subtitle"]}</p>
                </div>
                <div class="overall-verdict-badge">
                    {overall_verdict.value}
                </div>
            </div>

            <div class="meta-grid">
                <div>
                    <div class="meta-label">{strings["target_id"]}</div>
                    <div class="meta-value font-mono">{html.escape(target.id)}</div>
                </div>
                <div>
                    <div class="meta-label">{strings["claimed_model"]}</div>
                    <div class="meta-value font-mono" style="color: #60a5fa;">{html.escape(target.model)}</div>
                </div>
                <div>
                    <div class="meta-label">{strings["base_url"]}</div>
                    <div class="meta-value font-mono" style="font-size:0.8rem;">{html.escape(target.base_url)}</div>
                </div>
                <div>
                    <div class="meta-label">{strings["ground_truth"]}</div>
                    <div class="meta-value">#{baseline.id} ({baseline.battery_version})</div>
                </div>
                <div>
                    <div class="meta-label">{strings["audit_timestamp"]}</div>
                    <div class="meta-value font-mono">{html.escape(run.started_at[:19])}</div>
                </div>
                <div>
                    <div class="meta-label">{strings["discrepancies_found"]}</div>
                    <div class="meta-value" style="color: {"#ef4444" if fail_count > 0 else ("#f59e0b" if warn_count > 0 else "#10b981")};">
                        {strings["fails_warnings"].format(fails=fail_count, warns=warn_count) if (fail_count > 0 or warn_count > 0) else strings["no_discrepancies"]}
                    </div>
                </div>
                {infra_meta_html}
            </div>
        </div>

        <div class="dispute-statement">
            <div class="dispute-title">{strings["statement_title"]}</div>
            <div>{verdict_messages[overall_verdict]}</div>
        </div>

        {diagnostics_html}

        <div class="card">
            <h2>{strings["tests_title"]}</h2>
            <p class="section-sub">{strings["tests_sub"]}</p>
            <table>
                <thead>
                    <tr>
                        <th>{strings["th_test"]}</th>
                        <th>{strings["th_scope"]}</th>
                        <th>{strings["th_score"]}</th>
                        <th>{strings["th_threshold"]}</th>
                        <th>{strings["th_verdict"]}</th>
                        <th>{strings["th_details"]}</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
        </div>

        {samples_block}

        <div class="footer">
            {strings["footer"].format(run_id=run.id)}
        </div>
    </div>
</body>
</html>
"""


def generate_html_report(
    target: Target,
    baseline: Baseline,
    run: Run,
    scores: list[Score],
    overall_verdict: Verdict,
    output_path: str | Path,
    samples: list[RawSample] | None = None,
    failure_diagnostics: list[dict[str, Any]] | None = None,
    locale: str = "ru",
) -> Path:
    """Writes the full HTML dispute report to the specified file path."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    content = build_html_report(
        target=target,
        baseline=baseline,
        run=run,
        scores=scores,
        overall_verdict=overall_verdict,
        samples=samples,
        failure_diagnostics=failure_diagnostics,
        locale=locale,
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    return out
