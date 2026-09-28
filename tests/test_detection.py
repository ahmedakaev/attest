"""Unit tests for proxy and infrastructure detection."""

from attest.detection.infrastructure import detect_infrastructure
from attest.models import RawSample


def test_detect_litellm_and_azure():
    # Emulate the exact signature we saw on LLM-Hub live test
    headers = {
        "server": "uvicorn",
        "openai-model": "azure/gpt-6-astra/test-azure200-de20fdc4",
        "cf-ray": "9e1c3f58ea47dcf9-FRA",
        "x-request-id": "f8a7e02b",
    }
    model_returned = "azure/gpt-6-astra/test-azure200-de20fdc4"
    fp = detect_infrastructure(headers=headers, model_returned=model_returned)

    assert fp.proxy_gateway == "litellm"
    assert fp.upstream_cloud == "azure"
    assert fp.deployment_id == "test-azure200-de20fdc4"
    assert fp.server_software == "uvicorn"
    assert fp.region == "FRA"
    assert "LiteLLM" in fp.summary("ru")
    assert "Azure" in fp.summary("ru")
    assert "LiteLLM" in fp.summary("en")
    assert "Azure" in fp.summary("en")


def test_detect_oneapi():
    headers = {
        "server": "gin",
        "x-oneapi-request-id": "req-12345",
        "x-channel-id": "42",
    }
    fp = detect_infrastructure(headers=headers)
    assert fp.proxy_gateway == "oneapi"
    assert "OneAPI" in fp.summary("ru")


def test_detect_cloudflare():
    headers = {
        "server": "cloudflare",
        "cf-aig-request-id": "aig-9988",
    }
    fp = detect_infrastructure(headers=headers)
    assert fp.proxy_gateway == "cloudflare"


def test_detect_from_raw_samples():
    samples = [
        RawSample(
            prompt_id=1,
            raw_text="hello",
            latency_ms=150,
            model_returned="bedrock/anthropic.claude-3-5-sonnet",
            headers={"server": "nginx", "x-amzn-requestid": "abc-123"},
        )
    ]
    fp = detect_infrastructure(raw_samples=samples)
    assert fp.upstream_cloud == "bedrock"
    assert fp.deployment_id == "anthropic.claude-3-5-sonnet"


def test_direct_connection():
    fp = detect_infrastructure(headers={"content-type": "application/json"})
    assert fp.proxy_gateway is None
    assert fp.upstream_cloud is None
    assert "Прямое подключение" in fp.summary("ru")
