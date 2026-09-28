import httpx
import pytest
import respx
from click.testing import CliRunner

from attest.cli import cli


@pytest.mark.asyncio
async def test_end_to_end_verification_lifecycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    db_file = str(tmp_path / "e2e_attest.db")
    config_file = str(tmp_path / "e2e_attest.yaml")

    # 1. Initialize
    res = runner.invoke(cli, ["init", "--db", db_file, "--config", config_file])
    assert res.exit_code == 0

    # 2. Add Target
    res = runner.invoke(
        cli,
        [
            "target",
            "add",
            "--id",
            "mock-provider",
            "--url",
            "https://mock.api/v1",
            "--model",
            "gpt-4o",
            "--key",
            "test-mock-key-12345",
            "--config",
            config_file,
        ],
    )
    assert res.exit_code == 0

    # Prepare small test battery with 2 prompts
    test_battery_path = tmp_path / "test_battery.yaml"
    test_battery_content = """version: "test-v1"
prompts:
  - category: one_token
    text: "Pick a number 1-100"
    params: { max_tokens: 5, temperature: 1.0 }
    samples: 4
  - category: code
    text: "Write palindrome function"
    params: { max_tokens: 50, temperature: 0.0 }
    samples: 1
"""
    test_battery_path.write_text(test_battery_content, encoding="utf-8")

    # 3. Mock API responses for baseline
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chatcmpl-mock",
                    "model": "gpt-4o",
                    "system_fingerprint": "fp_original",
                    "choices": [{"message": {"role": "assistant", "content": "42"}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                },
            )
        )

        # Capture baseline
        res = runner.invoke(
            cli,
            [
                "baseline",
                "capture",
                "mock-provider",
                "--battery",
                str(test_battery_path),
                "--config",
                config_file,
                "--yes",
            ],
        )
        assert res.exit_code == 0
        assert "captured successfully!" in res.output

    # 4. Run verification where provider returns same authentic distribution (PASS)
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chatcmpl-mock-pass",
                    "model": "gpt-4o",
                    "system_fingerprint": "fp_original",
                    "choices": [{"message": {"role": "assistant", "content": "42"}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                },
            )
        )

        report_html = str(tmp_path / "report_pass.html")
        res = runner.invoke(
            cli,
            [
                "run",
                "mock-provider",
                "--battery",
                str(test_battery_path),
                "--config",
                config_file,
                "--html",
                report_html,
            ],
        )
        assert res.exit_code == 0
        assert (
            "ИТОГОВЫЙ ВЕРДИКТ: ПРОЙДЕНО" in res.output
            or "OVERALL VERDICT: PASSED" in res.output
        )

    # 5. Run verification where provider silently swapped model (returns different token & wrong model) (FAIL)
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chatcmpl-mock-fail",
                    "model": "qwen-2.5-7b",  # Model name differs!
                    "system_fingerprint": "fp_tampered",
                    "choices": [
                        {"message": {"role": "assistant", "content": "999"}}
                    ],  # Different token!
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                },
            )
        )

        report_fail_html = str(tmp_path / "report_fail.html")
        res = runner.invoke(
            cli,
            [
                "run",
                "mock-provider",
                "--battery",
                str(test_battery_path),
                "--config",
                config_file,
                "--html",
                report_fail_html,
            ],
        )
        # Should exit with code 2 on FAIL
        assert res.exit_code == 2
        assert (
            "ИТОГОВЫЙ ВЕРДИКТ: ПРОВАЛЕНО" in res.output
            or "OVERALL VERDICT: FAILED" in res.output
        )


@pytest.mark.asyncio
async def test_openai_compat_adapter_logprobs_and_fallback():
    from attest.sampling.openai_compat import OpenAICompatAdapter

    adapter = OpenAICompatAdapter(
        base_url="https://mock.api/v1",
        model="gpt-4o",
        api_key="test-auth-token",
    )

    # 1. Successful response with logprobs
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chatcmpl-1",
                    "model": "gpt-4o-2024-08-06",
                    "system_fingerprint": "fp_test",
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "42"},
                            "logprobs": {
                                "content": [
                                    {
                                        "token": "42",
                                        "logprob": -0.15,
                                        "top_logprobs": [
                                            {"token": "42", "logprob": -0.15},
                                            {"token": "7", "logprob": -2.10},
                                        ],
                                    }
                                ]
                            },
                        }
                    ],
                },
            )
        )

        sample = await adapter.sample(
            prompt_id=1,
            prompt_text="Pick a number",
            params={"max_tokens": 1, "temperature": 1.0},
        )
        assert sample.raw_text == "42"
        assert sample.logprobs == {"42": -0.15, "7": -2.10}
        assert sample.model_returned == "gpt-4o-2024-08-06"
        # Verify request sent logprobs: True
        sent_req = route.calls.last.request
        import json

        sent_body = json.loads(sent_req.content)
        assert sent_body.get("logprobs") is True
        assert sent_body.get("top_logprobs") == 5

    # 2. Provider rejecting logprobs with 400 -> fallback without logprobs
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        # First call fails with 400 complaining about logprobs
        # Second call succeeds without logprobs
        respx_mock.post("/chat/completions").mock(
            side_effect=[
                httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": "logprobs parameter is not supported by this model"
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "id": "chatcmpl-fallback",
                        "model": "gpt-4o",
                        "choices": [
                            {"message": {"role": "assistant", "content": "42"}}
                        ],
                    },
                ),
            ]
        )

        sample_fallback = await adapter.sample(
            prompt_id=2,
            prompt_text="Pick a number",
            params={"max_tokens": 1, "temperature": 1.0},
        )
        assert sample_fallback.raw_text == "42"
        assert sample_fallback.logprobs is None  # Gracefully None on fallback

    await adapter.close()


@pytest.mark.asyncio
async def test_openai_compat_adapter_error_handling():
    from attest.sampling.openai_compat import OpenAICompatAdapter

    adapter = OpenAICompatAdapter(
        base_url="https://mock.api/v1",
        model="gpt-4o",
        api_key="test-auth-token",
        retry_max=2,
        retry_backoff=0.1,
    )

    # 1. 401 Unauthorized -> raises immediately without retrying
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                401, json={"error": {"message": "Invalid API key"}}
            )
        )
        with pytest.raises(RuntimeError, match="HTTP 401 Error"):
            await adapter.sample(1, "hello", {})
        # Should NOT retry on permanent 401 error
        assert route.call_count == 1

    # 2. 429 Rate Limit -> retries and succeeds on 2nd attempt
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            side_effect=[
                httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}}),
                httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"message": {"role": "assistant", "content": "recovered"}}
                        ]
                    },
                ),
            ]
        )
        sample = await adapter.sample(2, "hello", {})
        assert sample.raw_text == "recovered"

    await adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "expected_cap"),
    [
        ("claude-opus-5-5", 2048),
        ("anthropic/claude-fable-5.1", 2048),
        ("deepseek-v4-pro", 2048),
        ("qwen3.8-max", 2048),
        ("gpt-4o", 5),
        ("claude-sonnet-5", 5),
    ],
)
async def test_thinking_models_get_output_headroom(model: str, expected_cap: int):
    import json

    from attest.sampling.openai_compat import OpenAICompatAdapter

    adapter = OpenAICompatAdapter(
        base_url="https://mock.api/v1", model=model, api_key="test-auth-token"
    )
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "3"}}]},
            )
        )
        await adapter.sample(
            prompt_id=1, prompt_text="Reply with one digit", params={"max_tokens": 5}
        )
        body = json.loads(route.calls.last.request.content)
        assert body.get("max_tokens", body.get("max_completion_tokens")) == expected_cap


def _sse(*chunks: dict | str) -> httpx.Response:
    import json

    lines = [f"data: {c if isinstance(c, str) else json.dumps(c)}\n\n" for c in chunks]
    return httpx.Response(
        200,
        content="".join(lines).encode(),
        headers={"content-type": "text/event-stream", "x-request-id": "req-1"},
    )


@pytest.mark.asyncio
async def test_streaming_reassembles_response_and_measures_ttft():
    import json

    from attest.sampling.openai_compat import OpenAICompatAdapter

    adapter = OpenAICompatAdapter(
        base_url="https://mock.api/v1", model="gpt-4o", api_key="test-auth-token"
    )
    tok = {
        "token": "4",
        "logprob": -0.2,
        "top_logprobs": [{"token": "4", "logprob": -0.2}],
    }
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=_sse(
                {
                    "model": "gpt-4o-2024-08-06",
                    "system_fingerprint": "fp_1",
                    "choices": [{"index": 0, "delta": {"role": "assistant"}}],
                },
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": "4"},
                            "logprobs": {"content": [tok]},
                        }
                    ]
                },
                {
                    "choices": [
                        {"index": 0, "delta": {"content": "2"}, "finish_reason": "stop"}
                    ]
                },
                {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 2}},
                "[DONE]",
            )
        )
        sample = await adapter.sample(
            prompt_id=1, prompt_text="Pick", params={"max_tokens": 5, "logprobs": True}
        )
        body = json.loads(route.calls.last.request.content)

    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}
    assert sample.raw_text == "42"
    assert sample.model_returned == "gpt-4o-2024-08-06"
    assert sample.fingerprint == "fp_1"
    assert sample.usage == {"prompt_tokens": 9, "completion_tokens": 2}
    assert sample.logprobs == {"4": -0.2}
    assert sample.ttft_ms is not None and sample.ttft_ms <= sample.latency_ms
    assert sample.headers.get("x-request-id") == "req-1"


@pytest.mark.asyncio
async def test_streaming_collects_reasoning_deltas():
    from attest.sampling.openai_compat import OpenAICompatAdapter

    adapter = OpenAICompatAdapter(
        base_url="https://mock.api/v1",
        model="deepseek-flash",
        api_key="test-auth-token",
    )
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=_sse(
                {"choices": [{"index": 0, "delta": {"reasoning_content": "think "}}]},
                {"choices": [{"index": 0, "delta": {"reasoning_content": "more"}}]},
                {"choices": [{"index": 0, "delta": {"content": "3"}}]},
                "[DONE]",
            )
        )
        sample = await adapter.sample(prompt_id=1, prompt_text="q", params={})
    assert sample.reasoning_content == "think more"
    assert sample.raw_text == "3"
    # No usage in the stream -> later requests go unstreamed to keep billing data
    assert adapter.stream is False


@pytest.mark.asyncio
async def test_stream_rejections_fall_back():
    import json

    from attest.sampling.openai_compat import OpenAICompatAdapter

    ok = httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
    )

    # 1. stream_options unsupported -> keep streaming, drop the option
    adapter = OpenAICompatAdapter(
        base_url="https://mock.api/v1", model="gpt-4o", api_key="test-auth-token"
    )
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            side_effect=[
                httpx.Response(
                    400, json={"error": {"message": "Unknown field stream_options"}}
                ),
                ok,
            ]
        )
        sample = await adapter.sample(prompt_id=1, prompt_text="q", params={})
        body = json.loads(route.calls.last.request.content)
    assert sample.raw_text == "ok"
    assert body["stream"] is True and "stream_options" not in body

    # 2. streaming unsupported -> plain request, remembered for later calls
    adapter = OpenAICompatAdapter(
        base_url="https://mock.api/v1", model="gpt-4o", api_key="test-auth-token"
    )
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            side_effect=[
                httpx.Response(
                    400, json={"error": {"message": "stream is not supported"}}
                ),
                ok,
                ok,
            ]
        )
        await adapter.sample(prompt_id=1, prompt_text="q", params={})
        await adapter.sample(prompt_id=1, prompt_text="q", params={})
        body = json.loads(route.calls.last.request.content)
    assert "stream" not in body
    assert adapter.stream is False


@pytest.mark.asyncio
async def test_unknown_thinking_model_is_learned_and_retried():
    """A model the name list does not know spends a small cap on reasoning and
    returns nothing; the adapter retries with headroom and keeps it."""
    import json

    from attest.sampling.openai_compat import OpenAICompatAdapter

    adapter = OpenAICompatAdapter(
        base_url="https://mock.api/v1",
        model="some-new-thinker",
        api_key="test-auth-token",
    )
    empty = httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"role": "assistant", "content": "", "reasoning": "hmm"},
                    "finish_reason": "length",
                }
            ],
            "usage": {"completion_tokens": 20},
        },
    )
    full = httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": "73928416"}}]},
    )
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            side_effect=[empty, full, full]
        )
        sample = await adapter.sample(
            prompt_id=1, prompt_text="q", params={"max_tokens": 20}
        )
        assert sample.raw_text == "73928416"
        assert sample.max_tokens_sent == 2048
        caps = [json.loads(c.request.content)["max_tokens"] for c in route.calls]
        assert caps == [20, 2048]

        # Learned: the next request goes out with headroom straight away
        await adapter.sample(prompt_id=2, prompt_text="q", params={"max_tokens": 20})
        assert json.loads(route.calls.last.request.content)["max_tokens"] == 2048
