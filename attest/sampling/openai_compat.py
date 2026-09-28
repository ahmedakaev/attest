"""
OpenAI-compatible HTTP provider adapter.
Supports any compliant gateway (OpenAI, OpenRouter, Together, Groq, DeepSeek, LiteLLM, vLLM, Ollama).
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from attest.detection.routing_proof import extract_routing_proof
from attest.models import RawSample
from attest.sampling.base import ProviderAdapter
from attest.security import url_hostname
from attest.utils import (
    THINKING_MIN_OUTPUT_TOKENS,
    is_reasoning_model_name,
    needs_thinking_headroom,
    rejects_custom_temperature,
)


class OpenAICompatAdapter(ProviderAdapter):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        retry_max: int = 3,
        retry_backoff: float = 2.0,
        stream: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.retry_max = retry_max
        self.retry_backoff = retry_backoff
        # Streaming is the only way to see time-to-first-token; the response is
        # reassembled into the regular shape, so parsing below is unchanged.
        self.stream = stream

        # Audit traffic must be indistinguishable from an ordinary client: an identifying
        # User-Agent would let a dishonest provider route verifier requests to the genuine
        # model. httpx's stock User-Agent is used instead.
        headers = {"Content-Type": "application/json"}
        if url_hostname(self.base_url) in ("openrouter.ai", "www.openrouter.ai"):
            # Ask OpenRouter for routing metadata (upstream provider/model)
            headers["X-OpenRouter-Metadata"] = "true"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra_headers:
            headers.update(extra_headers)

        self.client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            follow_redirects=True,
        )

        # Proactive quirk detection & caching per adapter instance
        self._requires_max_completion_tokens: bool = is_reasoning_model_name(model)
        self._rejects_custom_temperature: bool = rejects_custom_temperature(model)
        self._needs_thinking_headroom: bool = needs_thinking_headroom(model)
        self._rejects_logprobs: bool = False
        self._rejects_stream_options: bool = False

    async def _post(
        self, url: str, payload: dict[str, Any]
    ) -> tuple[httpx.Response, int, int | None]:
        """POST the request; returns (response, elapsed_ms, ttft_ms).

        Streamed replies are reassembled into a regular chat.completion response, so
        callers see the same shape either way. A provider that ignores `stream` and
        answers with plain JSON is handled too (ttft_ms is then None).
        """
        start_ns = time.perf_counter_ns()

        def since_start() -> int:
            return int((time.perf_counter_ns() - start_ns) / 1_000_000)

        if not payload.get("stream"):
            response = await self.client.post(url, json=payload)
            return response, since_start(), None

        async with self.client.stream("POST", url, json=payload) as response:
            is_sse = "text/event-stream" in response.headers.get("content-type", "")
            if response.is_error or not is_sse:
                body = await response.aread()
                plain = httpx.Response(
                    response.status_code,
                    content=body,
                    headers=response.headers,
                    request=response.request,
                )
                return plain, since_start(), None

            ttft_ms: int | None = None
            chunks: list[dict[str, Any]] = []
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                if ttft_ms is None and _chunk_has_token(chunk):
                    ttft_ms = since_start()
                chunks.append(chunk)
            elapsed_ms = since_start()

        body = _merge_stream_chunks(chunks)
        if "usage" not in body:
            # Provider streams without token usage: billing checks need it more than
            # TTFT, so the remaining requests go unstreamed.
            self.stream = False
        merged = httpx.Response(
            response.status_code,
            json=body,
            headers={
                k: v
                for k, v in response.headers.items()
                if k.lower()
                not in ("content-type", "content-length", "transfer-encoding")
            },
            request=response.request,
        )
        return merged, elapsed_ms, ttft_ms

    def _resolve_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    async def sample(
        self,
        prompt_id: int,
        prompt_text: str,
        params: dict[str, Any],
        messages: list[dict[str, Any]] | None = None,
    ) -> RawSample:
        sample = await self._sample_once(prompt_id, prompt_text, params, messages)
        # A model that spent a small cap entirely on reasoning returns nothing
        # visible. The model list cannot know every thinking model, so learn it
        # here: retry once with headroom and keep it for the following requests.
        spent_on_reasoning = (
            bool(sample.reasoning_content) or (sample.reasoning_tokens or 0) > 0
        )
        if (
            not sample.raw_text
            and spent_on_reasoning
            and not self._needs_thinking_headroom
            and "max_tokens" in params
        ):
            self._needs_thinking_headroom = True
            sample = await self._sample_once(prompt_id, prompt_text, params, messages)
        return sample

    async def _sample_once(
        self,
        prompt_id: int,
        prompt_text: str,
        params: dict[str, Any],
        messages: list[dict[str, Any]] | None = None,
    ) -> RawSample:
        url = self._resolve_url()
        if messages:
            msg_payload = messages
        elif params.get("system_prompt"):
            msg_payload = [
                {"role": "system", "content": str(params["system_prompt"])},
                {"role": "user", "content": prompt_text},
            ]
        else:
            msg_payload = [{"role": "user", "content": prompt_text}]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": msg_payload,
        }

        # Apply parameters
        if "temperature" in params:
            payload["temperature"] = float(params["temperature"])
        if "max_tokens" in params:
            max_tokens = int(params["max_tokens"])
            if self._needs_thinking_headroom:
                max_tokens = max(max_tokens, THINKING_MIN_OUTPUT_TOKENS)
            payload["max_tokens"] = max_tokens
        if "top_p" in params:
            payload["top_p"] = float(params["top_p"])
        if "seed" in params:
            payload["seed"] = int(params["seed"])
        if "reasoning_effort" in params:
            payload["reasoning_effort"] = str(params["reasoning_effort"])
        if "max_thinking_tokens" in params:
            payload["max_thinking_tokens"] = int(params["max_thinking_tokens"])

        # Request logprobs for single-token probes or when explicitly asked
        want_logprobs = bool(params.get("logprobs") or params.get("max_tokens") == 1)
        if want_logprobs and not self._rejects_logprobs:
            payload["logprobs"] = True
            payload["top_logprobs"] = int(params.get("top_logprobs", 5))

        if self.stream:
            payload["stream"] = True
            if not self._rejects_stream_options:
                # Streamed replies carry `usage` only when asked; billing needs it
                payload["stream_options"] = {"include_usage": True}

        # Proactively normalize parameters based on model family or previously learned target quirks
        if self._requires_max_completion_tokens and "max_tokens" in payload:
            payload["max_completion_tokens"] = payload.pop("max_tokens")
        if self._rejects_custom_temperature:
            payload.pop("temperature", None)
        if self._rejects_logprobs:
            payload.pop("logprobs", None)
            payload.pop("top_logprobs", None)
            want_logprobs = False

        retrying = AsyncRetrying(
            # retry_max counts retries, so the first attempt comes on top of it
            stop=stop_after_attempt(max(0, self.retry_max) + 1),
            wait=wait_exponential(multiplier=1, min=1, max=self.retry_backoff * 5),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            reraise=True,
        )

        async for attempt in retrying:
            with attempt:
                response, elapsed_ms, ttft_ms = await self._post(url, payload)

                # Fallback: if provider rejects max_tokens, logprobs, or temperature with 400 or 422, adapt payload in a loop (up to 3 times)
                for _ in range(3):
                    if response.status_code not in (400, 422):
                        break
                    err_text = response.text.lower()
                    modified = False
                    if "stream_options" in err_text and "stream_options" in payload:
                        payload.pop("stream_options")
                        self._rejects_stream_options = True
                        modified = True
                    elif "stream" in err_text and payload.get("stream"):
                        payload.pop("stream")
                        payload.pop("stream_options", None)
                        self.stream = False
                        modified = True
                    if "max_completion_tokens" in err_text and "max_tokens" in payload:
                        payload["max_completion_tokens"] = payload.pop("max_tokens")
                        self._requires_max_completion_tokens = True
                        modified = True
                    if want_logprobs and "logprob" in err_text:
                        payload.pop("logprobs", None)
                        payload.pop("top_logprobs", None)
                        self._rejects_logprobs = True
                        want_logprobs = False
                        modified = True
                    if "temperature" in err_text and (
                        "does not support" in err_text
                        or "unsupported" in err_text
                        or "only" in err_text
                        or "default (1)" in err_text
                    ):
                        payload.pop("temperature", None)
                        self._rejects_custom_temperature = True
                        modified = True
                    if not modified:
                        break
                    response, elapsed_ms, ttft_ms = await self._post(url, payload)

                # If rate limited (429) or 5xx server error, raising triggers tenacity retry.
                # If 4xx client error (e.g. 401 unauthorized, 400 bad request), raise immediately without wasteful retries.
                if response.status_code in (429, 500, 502, 503, 504):
                    response.raise_for_status()
                elif response.is_error:
                    # Permanent error: format clear message and do not retry
                    try:
                        err_json = response.json()
                        err_msg = err_json.get("error", {}).get(
                            "message", response.text
                        )
                    except (ValueError, KeyError):
                        err_msg = response.text
                    raise RuntimeError(
                        f"HTTP {response.status_code} Error from provider: {err_msg}"
                    )

                data = response.json()
                choices = data.get("choices", [])
                if not choices or not isinstance(choices, list):
                    raise RuntimeError(
                        f"Provider returned invalid/empty choices: {data}"
                    )

                first = choices[0]
                message = first.get("message", {})
                raw_text = message.get("content", "") or ""

                # Extract top_logprobs if returned
                extracted_logprobs: dict[str, float] | None = None
                logprobs_data = first.get("logprobs")
                if isinstance(logprobs_data, dict):
                    # Chat completions format: logprobs.content[0].top_logprobs
                    content_logprobs = logprobs_data.get("content")
                    if isinstance(content_logprobs, list) and content_logprobs:
                        first_pos = content_logprobs[0]
                        if isinstance(first_pos, dict):
                            top_list = first_pos.get("top_logprobs")
                            if isinstance(top_list, list):
                                parsed: dict[str, float] = {}
                                for item in top_list:
                                    if (
                                        isinstance(item, dict)
                                        and "token" in item
                                        and "logprob" in item
                                    ):
                                        try:
                                            parsed[str(item["token"])] = float(
                                                item["logprob"]
                                            )
                                        except (ValueError, TypeError):
                                            pass
                                if parsed:
                                    extracted_logprobs = parsed
                    # Legacy or alternative gateway format: logprobs.top_logprobs[0]
                    if not extracted_logprobs:
                        top_list = logprobs_data.get("top_logprobs")
                        if isinstance(top_list, list) and top_list:
                            first_top = (
                                top_list[0] if isinstance(top_list[0], dict) else {}
                            )
                            if first_top:
                                extracted_logprobs = {
                                    str(k): float(v)
                                    for k, v in first_top.items()
                                    if isinstance(v, (int, float))
                                }

                # Extract metadata
                fingerprint = data.get("system_fingerprint")
                model_returned = data.get("model")
                usage = data.get("usage")

                # Extract reasoning content & reasoning tokens (OpenAI o-series, DeepSeek Reasoner, OpenRouter)
                reasoning_content = message.get("reasoning_content") or message.get(
                    "reasoning"
                )
                reasoning_tokens = None
                if isinstance(usage, dict):
                    comp_details = usage.get("completion_tokens_details")
                    if isinstance(comp_details, dict):
                        reasoning_tokens = comp_details.get("reasoning_tokens")
                    if reasoning_tokens is None:
                        reasoning_tokens = usage.get("reasoning_tokens") or usage.get(
                            "thinking_tokens"
                        )

                # Clean headers to keep useful debugging and infrastructure fingerprinting info
                header_whitelist = {
                    "x-ratelimit-remaining-requests",
                    "x-ratelimit-remaining-tokens",
                    "cf-ray",
                    "cf-aig-request-id",
                    "server",
                    "x-request-id",
                    "openai-model",
                    "openai-processing-ms",
                    "openai-organization",
                    "openai-version",
                    "x-ms-request-id",
                    "x-ms-client-request-id",
                    "x-ms-region",
                    "x-ms-served-model",
                    "azureml-model-group",
                    "x-litellm-model-call-id",
                    "x-litellm-version",
                    "x-oneapi-request-id",
                    "x-channel-id",
                    "via",
                }
                filtered_headers = {
                    k.lower(): v
                    for k, v in response.headers.items()
                    if k.lower() in header_whitelist
                    or k.lower().startswith("x-")
                    or k.lower().startswith("cf-")
                }

                # Extract cryptographic proof-of-routing if present
                proof = extract_routing_proof(data, dict(response.headers))
                routing_proof_dict = proof.to_dict() if proof else None

                return RawSample(
                    prompt_id=prompt_id,
                    raw_text=raw_text.strip(),
                    latency_ms=elapsed_ms,
                    fingerprint=str(fingerprint) if fingerprint else None,
                    model_returned=str(model_returned) if model_returned else None,
                    usage=usage,
                    headers=filtered_headers,
                    logprobs=extracted_logprobs,
                    reasoning_content=str(reasoning_content).strip()
                    if reasoning_content
                    else None,
                    reasoning_tokens=int(reasoning_tokens)
                    if reasoning_tokens is not None
                    else None,
                    routing_proof=routing_proof_dict,
                    ttft_ms=ttft_ms,
                    max_tokens_sent=payload.get(
                        "max_tokens", payload.get("max_completion_tokens")
                    ),
                )

        raise RuntimeError(
            f"Sampling failed after {self.retry_max} retries for prompt {prompt_id}"
        )

    async def close(self) -> None:
        await self.client.aclose()


def _chunk_has_token(chunk: dict[str, Any]) -> bool:
    """True once a chunk carries generated text or streamed reasoning."""
    for choice in chunk.get("choices") or []:
        delta = choice.get("delta") or {}
        if (
            delta.get("content")
            or delta.get("reasoning_content")
            or delta.get("reasoning")
        ):
            return True
    return False


def _merge_stream_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild a non-streamed chat.completion body from its SSE chunks."""
    merged: dict[str, Any] = {}
    content: list[str] = []
    reasoning: list[str] = []
    logprob_tokens: list[Any] = []
    finish_reason = None
    for chunk in chunks:
        # Top-level metadata (model, system_fingerprint, usage, OpenRouter's
        # provider, ...): keep the latest non-empty value
        for key, value in chunk.items():
            if key != "choices" and value is not None:
                merged[key] = value
        for choice in chunk.get("choices") or []:
            if choice.get("index", 0) != 0:
                continue
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content.append(delta["content"])
            thought = delta.get("reasoning_content") or delta.get("reasoning")
            if isinstance(thought, str) and thought:
                reasoning.append(thought)
            lp = choice.get("logprobs")
            if isinstance(lp, dict) and isinstance(lp.get("content"), list):
                logprob_tokens.extend(lp["content"])
            finish_reason = choice.get("finish_reason") or finish_reason

    message: dict[str, Any] = {"role": "assistant", "content": "".join(content)}
    if reasoning:
        message["reasoning_content"] = "".join(reasoning)
    choice_out: dict[str, Any] = {
        "index": 0,
        "message": message,
        "finish_reason": finish_reason,
    }
    if logprob_tokens:
        choice_out["logprobs"] = {"content": logprob_tokens}
    merged["object"] = "chat.completion"
    merged["choices"] = [choice_out]
    return merged
