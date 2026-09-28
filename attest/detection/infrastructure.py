"""
Infrastructure and Proxy Detection Module.

Dissects HTTP response headers, system fingerprints, wire models, and server software
to identify:
  1. Proxy Gateways (LiteLLM, OneAPI/NewAPI, Cloudflare AI Gateway, OpenRouter, vLLM)
  2. Upstream Cloud Providers (Microsoft Azure OpenAI, AWS Bedrock, Google Cloud Vertex AI, OpenAI Official, Groq)
  3. Cloud Deployment IDs (e.g. test-azure200-de20fdc4)
  4. Server Software (uvicorn, gin, envoy, nginx)
  5. Deployment Region
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from attest.models import RawSample


@dataclass
class InfrastructureFingerprint:
    proxy_gateway: str | None = None
    upstream_cloud: str | None = None
    deployment_id: str | None = None
    server_software: str | None = None
    region: str | None = None
    confidence: float = 0.0
    raw_signatures: dict[str, str] = field(default_factory=dict)
    routing_proof: dict[str, Any] | None = None

    def summary(self, locale: str = "ru") -> str:
        """Human-readable description of the identified infrastructure."""
        loc = (locale or "ru").lower()
        if not self.proxy_gateway and not self.upstream_cloud:
            return (
                "Прямое подключение к эндпоинту (прокси и облачные шлюзы не обнаружены)"
                if loc == "ru"
                else "Direct endpoint connection (no proxy or cloud gateway signatures detected)"
            )

        # Proxy gateway description
        proxy_names = {
            "litellm": "LiteLLM Proxy",
            "oneapi": "OneAPI / NewAPI Gateway",
            "cloudflare": "Cloudflare AI Gateway",
            "openrouter": "OpenRouter Proxy",
            "vllm": "vLLM Inference Server",
        }
        cloud_names = {
            "azure": "Microsoft Azure OpenAI",
            "bedrock": "Amazon Web Services (AWS Bedrock)",
            "vertex": "Google Cloud (Vertex AI)",
            "openai": "OpenAI Official Cloud",
            "groq": "Groq LPU Cloud",
            "together": "Together AI",
            "fireworks": "Fireworks AI",
        }

        p_name = proxy_names.get(self.proxy_gateway or "", self.proxy_gateway or "")
        c_name = cloud_names.get(self.upstream_cloud or "", self.upstream_cloud or "")

        if loc == "ru":
            if p_name and c_name:
                base = f"Обнаружен шлюз {p_name} с маршрутизацией в {c_name}"
            elif p_name:
                base = f"Обнаружен прокси-шлюз {p_name}"
            else:
                base = f"Обнаружена облачная инфраструктура {c_name}"

            if self.deployment_id:
                base += f" (деплоймент: {self.deployment_id})"
            if self.region:
                base += f", регион: {self.region}"
            if self.server_software:
                base += f", сервер: {self.server_software}"
            if self.routing_proof and self.routing_proof.get("endpoint_slug"):
                base += f" [маршрут по данным провайдера: {self.routing_proof['endpoint_slug']}]"
        else:
            if p_name and c_name:
                base = f"Detected {p_name} routing to {c_name}"
            elif p_name:
                base = f"Detected {p_name}"
            else:
                base = f"Detected cloud backend {c_name}"

            if self.deployment_id:
                base += f" (deployment: {self.deployment_id})"
            if self.region:
                base += f", region: {self.region}"
            if self.server_software:
                base += f", server: {self.server_software}"
            if self.routing_proof and self.routing_proof.get("endpoint_slug"):
                base += f" [🛡️ Verified routing proof: {self.routing_proof['endpoint_slug']}]"

        return base

    def to_dict(self) -> dict[str, Any]:
        return {
            "proxy_gateway": self.proxy_gateway,
            "upstream_cloud": self.upstream_cloud,
            "deployment_id": self.deployment_id,
            "server_software": self.server_software,
            "region": self.region,
            "confidence": round(self.confidence, 2),
            "raw_signatures": self.raw_signatures,
            "routing_proof": self.routing_proof,
            "summary_ru": self.summary("ru"),
            "summary_en": self.summary("en"),
        }


def detect_infrastructure(
    headers: dict[str, str] | None = None,
    model_returned: str | None = None,
    system_fingerprint: str | None = None,
    raw_samples: list[RawSample] | None = None,
) -> InfrastructureFingerprint:
    """
    Analyzes aggregated response headers, wire models, and samples to detect proxy & cloud infrastructure.
    """
    merged_headers: dict[str, str] = {}
    models_seen: set[str] = set()
    fingerprints_seen: set[str] = set()

    if headers:
        for k, v in headers.items():
            merged_headers[k.lower().strip()] = str(v).strip()

    if model_returned:
        models_seen.add(model_returned)

    if system_fingerprint:
        fingerprints_seen.add(system_fingerprint)

    if raw_samples:
        for s in raw_samples:
            if s.headers:
                for k, v in s.headers.items():
                    merged_headers[k.lower().strip()] = str(v).strip()
            if s.model_returned:
                models_seen.add(s.model_returned)
            if s.fingerprint:
                fingerprints_seen.add(s.fingerprint)

    signatures: dict[str, str] = {}
    proxy_gateway: str | None = None
    upstream_cloud: str | None = None
    deployment_id: str | None = None
    server_software: str | None = None
    region: str | None = None
    confidence_points = 0.0

    # 1. Server Software extraction
    server_header = merged_headers.get("server", "").lower()
    if server_header:
        server_software = server_header
        signatures["server"] = server_header

    # 2. Check for Cloudflare AI Gateway
    if "cf-aig-request-id" in merged_headers or any(
        k.startswith("cf-aig-") for k in merged_headers
    ):
        proxy_gateway = "cloudflare"
        confidence_points += 0.9
        signatures["cf_aig"] = "Cloudflare AI Gateway headers detected"
    elif "cf-ray" in merged_headers:
        signatures["cf_ray"] = merged_headers["cf-ray"]
        # cf-ray often contains datacenter code e.g. "861...-FRA"
        cf_match = re.search(r"-([A-Z]{3})$", merged_headers["cf-ray"])
        if cf_match:
            region = cf_match.group(1)

    # 3. Check for LiteLLM
    # LiteLLM signs with x-litellm-* or runs on uvicorn with model patterns or openai-model
    has_litellm_header = any(k.startswith("x-litellm-") for k in merged_headers)
    if has_litellm_header:
        proxy_gateway = "litellm"
        confidence_points += 0.95
        for k, v in merged_headers.items():
            if k.startswith("x-litellm-"):
                signatures[k] = v
    elif "uvicorn" in server_header:
        # Check if model starts with azure/, openai/, vertex/, or openai-model header present
        has_upstream_pattern = (
            any("/" in m for m in models_seen) or "openai-model" in merged_headers
        )
        if has_upstream_pattern:
            proxy_gateway = "litellm"
            confidence_points += 0.8
            signatures["litellm_heuristic"] = (
                f"Uvicorn server with upstream routing ({list(models_seen)})"
            )

    # 4. Check for OneAPI / NewAPI
    has_oneapi_header = any(
        k in merged_headers
        for k in ("x-oneapi-request-id", "x-channel-id", "x-consumed-quota")
    ) or any(k.startswith("x-oneapi-") for k in merged_headers)
    if has_oneapi_header:
        proxy_gateway = "oneapi"
        confidence_points += 0.95
        signatures["oneapi"] = "OneAPI / NewAPI specific headers detected"
    elif "gin" in server_header:
        proxy_gateway = "oneapi"
        confidence_points += 0.75
        signatures["gin_heuristic"] = (
            "Gin Web Framework server (standard for OneAPI/NewAPI)"
        )

    # 5. Check for OpenRouter
    if any(k.startswith("x-openrouter-") for k in merged_headers) or any(
        "openrouter" in m.lower() for m in models_seen
    ):
        proxy_gateway = "openrouter"
        confidence_points += 0.95
        signatures["openrouter"] = "OpenRouter headers / model tag detected"

    # 6. Check for vLLM
    if any(k.startswith("x-vllm-") for k in merged_headers) or "vllm" in server_header:
        proxy_gateway = "vllm"
        confidence_points += 0.9
        signatures["vllm"] = "vLLM signature detected"

    # 7. Check Upstream Cloud Provider: Microsoft Azure OpenAI
    # Signatures: x-ms-request-id, azureml-model-group, x-ms-region, x-ms-served-model, model with azure/
    has_azure_headers = any(
        k in merged_headers
        for k in (
            "x-ms-request-id",
            "x-ms-client-request-id",
            "azureml-model-group",
            "x-ms-served-model",
        )
    )
    azure_model = next((m for m in models_seen if m.startswith("azure/")), None)
    openai_model_header = merged_headers.get("openai-model", "")
    ms_served_model = merged_headers.get("x-ms-served-model", "")
    if (
        azure_model
        or has_azure_headers
        or openai_model_header.startswith("azure/")
        or ms_served_model
    ):
        upstream_cloud = "azure"
        confidence_points += 0.95
        if has_azure_headers:
            signatures["azure_headers"] = "Microsoft Azure request headers present"
        if ms_served_model:
            signatures["azure_served_model"] = (
                f"Authoritative served model: {ms_served_model}"
            )
        if "x-ms-region" in merged_headers:
            region = merged_headers["x-ms-region"]
            signatures["azure_region"] = region
        # Extract deployment id if pattern is azure/<model>/<deployment_id>
        matched_model = azure_model or (
            openai_model_header if openai_model_header.startswith("azure/") else ""
        )
        if matched_model:
            signatures["azure_model_string"] = matched_model
            parts = matched_model.split("/")
            if len(parts) >= 3:
                deployment_id = parts[2]
            elif len(parts) == 2:
                deployment_id = parts[1]

    # 8. Check Upstream Cloud Provider: AWS Bedrock
    bedrock_model = next((m for m in models_seen if m.startswith("bedrock/")), None)
    has_bedrock_headers = any(
        k in merged_headers
        for k in ("x-amzn-requestid", "x-amzn-bedrock-invocation-latency")
    ) or any(k.startswith("x-amz-") for k in merged_headers)
    if bedrock_model or has_bedrock_headers:
        upstream_cloud = "bedrock"
        confidence_points += 0.95
        signatures["bedrock"] = "AWS Bedrock signature detected"
        if bedrock_model:
            parts = bedrock_model.split("/")
            if len(parts) >= 2:
                deployment_id = parts[-1]

    # 9. Check Upstream Cloud Provider: Google Cloud Vertex AI
    vertex_model = next(
        (m for m in models_seen if m.startswith(("vertex_ai/", "google/"))), None
    )
    has_vertex_headers = (
        "x-goog-request-id" in merged_headers
        or "x-cloud-trace-context" in merged_headers
    )
    if vertex_model or has_vertex_headers:
        upstream_cloud = "vertex"
        confidence_points += 0.95
        signatures["vertex"] = "Google Cloud / Vertex AI signature detected"

    # 10. Check Upstream Cloud Provider: Official OpenAI
    has_openai_headers = (
        "openai-organization" in merged_headers
        or "openai-processing-ms" in merged_headers
    )
    if has_openai_headers and upstream_cloud != "azure":
        upstream_cloud = "openai"
        confidence_points += 0.9
        signatures["openai_official"] = "Official OpenAI processing headers present"

    # 11. Check Groq
    if any(k.startswith("x-groq-") for k in merged_headers) or any(
        m.startswith("groq/") for m in models_seen
    ):
        upstream_cloud = "groq"
        confidence_points += 0.95
        signatures["groq"] = "Groq LPU signature detected"

    # 12. Provider-reported routing metadata (OpenRouter / Azure; unsigned)
    proof_data = next(
        (s.routing_proof for s in (raw_samples or []) if s.routing_proof), None
    )
    if proof_data:
        proof_router = proof_data.get("router", "openrouter")
        if proof_router != "azure":
            proxy_gateway = proof_router
        upstream = proof_data.get("upstream_provider")
        if upstream and upstream != "unknown":
            upstream_cloud = upstream
        confidence_points += 1.0
        signatures["routing_metadata"] = (
            f"Provider-reported (unsigned) route: {proof_data.get('endpoint_slug')} "
            f"via {proof_router}"
        )

    final_confidence = (
        min(1.0, max(0.5, confidence_points))
        if (proxy_gateway or upstream_cloud)
        else 0.0
    )

    return InfrastructureFingerprint(
        proxy_gateway=proxy_gateway,
        upstream_cloud=upstream_cloud,
        deployment_id=deployment_id,
        server_software=server_software,
        region=region,
        confidence=final_confidence,
        raw_signatures=signatures,
        routing_proof=proof_data,
    )
