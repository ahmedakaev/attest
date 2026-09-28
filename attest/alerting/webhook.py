"""
Webhook alert dispatcher for Attest.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from attest.i18n import get_verdict_label, normalize_locale
from attest.models import Run, Target, Verdict


async def dispatch_webhook_alert(
    webhook_url: str | None,
    target: Target,
    run: Run,
    overall_verdict: Verdict,
    summary_message: str,
    diagnostics: list[dict[str, Any]] | None = None,
    locale: str = "ru",
) -> bool:
    if not webhook_url:
        return False

    loc = normalize_locale(locale)
    is_ru = loc == "ru"

    v_label = get_verdict_label(overall_verdict, locale=loc)
    fields = [
        {"title": "Таргет" if is_ru else "Target", "value": target.id, "short": True},
        {"title": "Модель" if is_ru else "Model", "value": target.model, "short": True},
        {"title": "Вердикт" if is_ru else "Verdict", "value": v_label, "short": True},
        {
            "title": "ID запуска" if is_ru else "Run ID",
            "value": str(run.id),
            "short": True,
        },
        {
            "title": "Итог" if is_ru else "Summary",
            "value": summary_message,
            "short": False,
        },
    ]

    if diagnostics:
        diag_lines = []
        for d in diagnostics[:5]:
            p_prefix = "промпт" if is_ru else "prompt"
            p_hint = f" ({p_prefix} #{d['prompt_id']})" if d.get("prompt_id") else ""
            diag_lines.append(
                f"• *{d.get('title', d.get('method', ''))}*{p_hint}: {d['message']}"
            )
        fields.append(
            {
                "title": "🚨 Диагностика сбоев"
                if is_ru
                else "🚨 Root Cause Diagnostics",
                "value": "\n".join(diag_lines),
                "short": False,
            }
        )

    alert_text = (
        f"🛡️ *Оповещение Attest*: Верификация {v_label} для таргета `{target.id}`"
        if is_ru
        else f"🛡️ *Attest Alert*: Verification {overall_verdict.value} for target `{target.id}`"
    )

    payload = {
        "text": alert_text,
        "attachments": [
            {
                "color": "#10b981"
                if overall_verdict == Verdict.PASS
                else ("#f59e0b" if overall_verdict == Verdict.WARN else "#ef4444"),
                "fields": fields,
            }
        ],
    }

    try:
        retrying = AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            reraise=True,
        )
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0)
        ) as client:
            async for attempt in retrying:
                with attempt:
                    resp = await client.post(webhook_url, json=payload)
                    # Retry on server error or rate limiting; fail immediately on client 4xx
                    if resp.status_code in (429, 500, 502, 503, 504):
                        resp.raise_for_status()
                    return resp.is_success
    except (httpx.HTTPError, OSError):
        return False
    return False
