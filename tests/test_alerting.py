"""
Unit tests for Attest webhook alert dispatching.
"""

import httpx
import pytest
import respx

from attest.alerting.webhook import dispatch_webhook_alert
from attest.models import Run, Target, Verdict


@pytest.mark.asyncio
async def test_dispatch_webhook_alert_success():
    target = Target(id="test-tgt", base_url="https://api.test/v1", model="gpt-4o")
    run = Run(
        id=123,
        target_id="test-tgt",
        baseline_id=1,
        battery_version="v1",
        started_at="2026-09-20T10:00:00Z",
    )

    with respx.mock(base_url="https://hooks.slack.com") as respx_mock:
        route = respx_mock.post("/services/test-webhook").mock(
            return_value=httpx.Response(200, text="ok")
        )

        ok = await dispatch_webhook_alert(
            webhook_url="https://hooks.slack.com/services/test-webhook",
            target=target,
            run=run,
            overall_verdict=Verdict.FAIL,
            summary_message="Model substitution detected",
        )
        assert ok is True
        assert route.called
        sent_payload = route.calls[0].request.content
        assert "ПРОВАЛЕНО".encode() in sent_payload
        assert "Таргет".encode() in sent_payload
        assert b"test-tgt" in sent_payload

    # Also test English locale dispatch
    with respx.mock(base_url="https://hooks.slack.com") as respx_mock:
        route = respx_mock.post("/services/test-webhook").mock(
            return_value=httpx.Response(200, text="ok")
        )
        ok_en = await dispatch_webhook_alert(
            webhook_url="https://hooks.slack.com/services/test-webhook",
            target=target,
            run=run,
            overall_verdict=Verdict.FAIL,
            summary_message="Model substitution detected",
            locale="en",
        )
        assert ok_en is True
        sent_en = route.calls[0].request.content
        assert b"FAILED" in sent_en
        assert b"Target" in sent_en


@pytest.mark.asyncio
async def test_dispatch_webhook_alert_no_url():
    target = Target(id="test-tgt", base_url="https://api.test/v1", model="gpt-4o")
    run = Run(
        id=1,
        target_id="test-tgt",
        baseline_id=1,
        battery_version="v1",
        started_at="2026-09-20T10:00:00Z",
    )

    ok = await dispatch_webhook_alert(
        webhook_url=None,
        target=target,
        run=run,
        overall_verdict=Verdict.WARN,
        summary_message="Warning",
    )
    assert ok is False


@pytest.mark.asyncio
async def test_dispatch_webhook_alert_network_failure():
    target = Target(id="test-tgt", base_url="https://api.test/v1", model="gpt-4o")
    run = Run(
        id=1,
        target_id="test-tgt",
        baseline_id=1,
        battery_version="v1",
        started_at="2026-09-20T10:00:00Z",
    )

    with respx.mock(base_url="https://hooks.slack.com") as respx_mock:
        respx_mock.post("/services/broken").mock(
            return_value=httpx.Response(500, text="internal server error")
        )

        ok = await dispatch_webhook_alert(
            webhook_url="https://hooks.slack.com/services/broken",
            target=target,
            run=run,
            overall_verdict=Verdict.FAIL,
            summary_message="Fail",
        )
        assert ok is False
