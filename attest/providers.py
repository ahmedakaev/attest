"""
Known LLM API Provider Registry.

Defines known providers, their standard OpenAI-compatible base URLs,
model call prefix rules, and flagship model catalogues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from attest.utils import canonicalize_model_name


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    base_url: str
    description: str
    model_prefix: str = ""
    auth_header_format: str = "Bearer {key}"
    is_trusted_reference: bool = False
    popular_models: list[str] = field(default_factory=list)
    docs_url: str = ""

    def format_model_call(self, canonical_model: str) -> str:
        """Format the canonical model name into this provider's expected wire format."""
        if not self.model_prefix:
            return canonical_model
        if canonical_model.startswith(self.model_prefix):
            return canonical_model
        return f"{self.model_prefix}{canonical_model}"

    def clean_model_name(self, model_call: str) -> str:
        """Strip provider-specific prefixes to obtain canonical model name."""
        if self.model_prefix and model_call.startswith(self.model_prefix):
            return model_call[len(self.model_prefix) :]
        return model_call

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url,
            "description": self.description,
            "model_prefix": self.model_prefix,
            "is_trusted_reference": self.is_trusted_reference,
            "popular_models": self.popular_models,
            "docs_url": self.docs_url,
        }


KNOWN_PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        id="openai",
        name="Official OpenAI Direct",
        base_url="https://api.openai.com/v1",
        description="Official OpenAI API (Gold Standard Ground Truth)",
        is_trusted_reference=True,
        popular_models=[
            "gpt-6-astra",
            "gpt-6-sol",
            "gpt-6-luna",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
            "gpt-5.5",
            "o3",
            "gpt-4o",
            "gpt-4o-mini",
        ],
        docs_url="https://platform.openai.com/docs",
    ),
    "openrouter": ProviderSpec(
        id="openrouter",
        name="OpenRouter Gateway",
        base_url="https://openrouter.ai/api/v1",
        description="Multi-provider AI routing aggregator with provider namespaces",
        # No fixed prefix: every OpenRouter model id carries its own vendor
        # namespace (openai/..., anthropic/..., qwen/...)
        popular_models=[
            "anthropic/claude-opus-5.5",
            "anthropic/claude-sonnet-5",
            "anthropic/claude-fable-5.1",
            "openai/gpt-6-astra",
            "openai/gpt-5.5",
            "google/gemini-3.8-flash",
            "x-ai/grok-4.7",
            "deepseek/deepseek-v4.1-flash",
            "deepseek/deepseek-v4-pro",
            "qwen/qwen3.8-max",
            "meta-llama/llama-4-scout",
        ],
        docs_url="https://openrouter.ai/docs",
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        name="DeepSeek Direct",
        base_url="https://api.deepseek.com/v1",
        description="Official DeepSeek API endpoint",
        is_trusted_reference=True,
        popular_models=[
            "deepseek-flash",
            "deepseek-v4-pro",
        ],
        docs_url="https://platform.deepseek.com",
    ),
    "anthropic_proxy": ProviderSpec(
        id="anthropic_proxy",
        name="Anthropic OpenAI-Compatible Proxy",
        base_url="https://api.anthropic.com/v1",
        description="Anthropic Claude API via OpenAI compatibility gateway",
        is_trusted_reference=True,
        popular_models=[
            "claude-opus-5-5",
            "claude-fable-5-1",
            "claude-sonnet-5",
            "claude-opus-5",
            "claude-haiku-4-5",
        ],
        docs_url="https://docs.anthropic.com",
    ),
    "groq": ProviderSpec(
        id="groq",
        name="Groq Cloud LPU",
        base_url="https://api.groq.com/openai/v1",
        description="Ultra low-latency LPU inference for open models",
        popular_models=[
            "meta-llama/llama-4-scout",
            "meta-llama/llama-4-maverick",
            "qwen/qwen-3.8-flash",
            "deepseek-r1-distill-llama-70b",
        ],
        docs_url="https://groq.com",
    ),
    "together": ProviderSpec(
        id="together",
        name="Together AI",
        base_url="https://api.together.xyz/v1",
        description="Fast open-weights model inference platform",
        popular_models=[
            "meta-llama/llama-4-scout",
            "meta-llama/llama-4-maverick",
            "qwen/qwen-3.8-max",
            "deepseek-ai/deepseek-v4.1-flash",
        ],
        docs_url="https://together.ai",
    ),
    "vllm": ProviderSpec(
        id="vllm",
        name="Local vLLM / LiteLLM / SGLang",
        base_url="http://localhost:8000/v1",
        description="Self-hosted GPU inference cluster with OpenAI API emulation",
        popular_models=[
            "default",
            "llama-4-scout",
            "qwen-3.8-flash",
        ],
        docs_url="https://vllm.ai",
    ),
    "custom": ProviderSpec(
        id="custom",
        name="Custom OpenAI-Compatible API",
        base_url="https://api.example.com/v1",
        description="Any custom reseller, proxy gateway, or private endpoint",
        popular_models=[],
    ),
}


def get_provider(provider_id: str) -> ProviderSpec | None:
    return KNOWN_PROVIDERS.get(provider_id)


def list_providers() -> list[ProviderSpec]:
    return list(KNOWN_PROVIDERS.values())


def get_curated_models_by_vendor() -> dict[str, list[dict[str, str]]]:
    """Returns official 2026 curated flagship and workhorse models grouped by vendor."""
    return {
        "Anthropic": [
            {
                "id": "claude-opus-5-5",
                "name": "Claude Opus 5.5 (Flagship Frontier 2026)",
            },
            {"id": "claude-fable-5-1", "name": "Claude Fable 5.1 (Frontier Special)"},
            {"id": "claude-sonnet-5", "name": "Claude Sonnet 5"},
            {"id": "claude-opus-5", "name": "Claude Opus 5 (Legacy)"},
            {
                "id": "claude-haiku-4-5",
                "name": "Claude Haiku 4.5 (Retires after 2026-10-15)",
            },
        ],
        "OpenAI": [
            {"id": "gpt-6-astra", "name": "GPT-6 Astra (Frontier Flagship 2026)"},
            {"id": "gpt-6-sol", "name": "GPT-6 Sol (High-Efficiency Reasoning)"},
            {"id": "gpt-6-luna", "name": "GPT-6 Luna (High Volume Throughput)"},
            {"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra (Balanced)"},
            {"id": "gpt-5.6-luna", "name": "GPT-5.6 Luna"},
            {"id": "gpt-5.5", "name": "GPT-5.5 (General Frontier)"},
            {"id": "o3", "name": "o3 (Full Reasoning)"},
            {"id": "gpt-4o", "name": "GPT-4o (Standard Flagship 2024)"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
        ],
        "Google Gemini": [
            {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash (Frontier 2026)"},
            {"id": "gemini-3.8-live", "name": "Gemini 3.8 Live (Speech & Thinking)"},
            {"id": "gemini-3.7-flash", "name": "Gemini 3.7 Flash"},
            {"id": "gemini-3.5-pro", "name": "Gemini 3.5 Pro"},
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash"},
        ],
        "xAI Grok": [
            {"id": "grok-4.7", "name": "Grok 4.7 (Frontier Flagship)"},
            {"id": "grok-4.6", "name": "Grok 4.6"},
            {"id": "grok-4.5", "name": "Grok 4.5"},
        ],
        "DeepSeek": [
            {
                "id": "deepseek-flash",
                "name": "DeepSeek V4.1 Flash (Multimodal MoE)",
            },
            {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro 0813 (1M Context)"},
        ],
        "Open-Weights & Ecosystem": [
            {"id": "llama4-scout", "name": "Meta Llama 4 Scout (128k)"},
            {"id": "llama4-maverick", "name": "Meta Llama 4 Maverick (MoE)"},
            {"id": "qwen3.8-max", "name": "Qwen 3.8 Max (Flagship)"},
            {"id": "qwen3.8-max-0902", "name": "Qwen 3.8 Max 0902 (Pinned Snapshot)"},
            {"id": "qwen3.8-flash", "name": "Qwen 3.8 Flash"},
            {
                "id": "meta-llama/llama-3.3-70b-instruct",
                "name": "Llama 3.3 70B Instruct",
            },
        ],
    }


__all__ = [
    "KNOWN_PROVIDERS",
    "ProviderSpec",
    "canonicalize_model_name",
    "get_curated_models_by_vendor",
    "get_provider",
    "list_providers",
]
