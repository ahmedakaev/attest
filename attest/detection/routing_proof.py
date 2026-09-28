"""
Provider-Reported Routing Metadata Extraction Module.

Extracts routing metadata (OpenRouter reasoning_details tokens, metadata fields,
routing headers, Azure x-ms-served-model) describing which upstream model served a
request. Token signatures are NOT verified: this is the provider's own claim. It is
strong evidence when it contradicts the advertised model (self-incrimination), but
a matching value proves nothing, since any reseller can forge it.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RoutingProof:
    """Provider-reported routing metadata extracted from response payloads (unsigned)."""

    endpoint_slug: str
    upstream_provider: str
    upstream_model: str
    model_snapshot: str | None = None
    router: str = "openrouter"
    # Signatures are never checked, so this stays False (kept for serialized reports)
    is_verified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutingProof:
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**clean)


def extract_routing_proof(
    response_data: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> RoutingProof | None:
    """
    Extracts and decodes provider-reported routing metadata from OpenAI-compatible response payloads.
    Specifically checks for OpenRouter JWT metadata embedded in reasoning_details or headers.
    """
    if not isinstance(response_data, dict):
        return None

    # 1. Search in choices[].message.reasoning_details
    choices = response_data.get("choices")
    if isinstance(choices, list) and choices:
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            msg = choice.get("message") or {}
            reasoning_details = msg.get("reasoning_details") or choice.get(
                "reasoning_details"
            )
            if isinstance(reasoning_details, list):
                for item in reasoning_details:
                    if isinstance(item, dict):
                        data_str = item.get("data")
                        if isinstance(data_str, str) and "." in data_str:
                            proof = _parse_jwt_segment(data_str, router="openrouter")
                            if proof:
                                return proof

    # 2. Search in top-level reasoning_details or openrouter metadata
    top_rd = response_data.get("reasoning_details")
    if isinstance(top_rd, list):
        for item in top_rd:
            if isinstance(item, dict):
                data_str = item.get("data")
                if isinstance(data_str, str) and "." in data_str:
                    proof = _parse_jwt_segment(data_str, router="openrouter")
                    if proof:
                        return proof

    # 3. Search in openrouter_metadata or top-level metadata dictionary
    for meta_key in ("openrouter_metadata", "metadata"):
        meta = response_data.get(meta_key)
        if isinstance(meta, dict):
            slug = (
                meta.get("endpoint_slug")
                or meta.get("endpoint")
                or meta.get("model_slug")
                or meta.get("slug")
                or meta.get("model")
            )
            if isinstance(slug, str) and slug.strip():
                return _parse_slug_string(
                    slug.strip(), router="openrouter", metadata=meta
                )

    # 4. Check for OpenRouter headers or Azure x-ms-served-model if passed
    if headers:
        for k, v in headers.items():
            k_low = k.lower().strip()
            v_val = str(v).strip()
            if k_low in ("x-openrouter-model", "x-openrouter-endpoint") and v_val:
                return _parse_slug_string(v_val, router="openrouter")
            if k_low == "x-ms-served-model" and v_val:
                return _parse_azure_served_model(v_val)

    return None


def _parse_jwt_segment(
    raw_data: str, router: str = "openrouter"
) -> RoutingProof | None:
    """
    Decodes the unencrypted metadata payload of a token (e.g. FernetCipher.JWT_Payload).
    """
    try:
        parts = raw_data.split(".")
        # The unencrypted metadata payload is located after the first dot
        candidate_b64 = parts[1] if len(parts) > 1 else parts[0]
        padding = 4 - len(candidate_b64) % 4
        if padding != 4:
            candidate_b64 += "=" * padding

        decoded_bytes = base64.urlsafe_b64decode(candidate_b64)
        payload = json.loads(decoded_bytes.decode("utf-8", errors="replace"))
        if not isinstance(payload, dict):
            return None

        slug = (
            payload.get("endpoint_slug")
            or payload.get("model_slug")
            or payload.get("slug")
        )
        if isinstance(slug, str) and slug.strip():
            return _parse_slug_string(slug.strip(), router=router, metadata=payload)
    except Exception:  # noqa: BLE001
        return None
    return None


def _parse_azure_served_model(served_model: str) -> RoutingProof:
    """
    Parses Microsoft Azure OpenAI authoritative 'x-ms-served-model' header into a RoutingProof.
    """
    clean_model = served_model.strip()
    snapshot_match = re.search(r"(\d{4}-?\d{2}-?\d{2}|\d{8})", clean_model)
    model_snapshot = snapshot_match.group(1) if snapshot_match else None
    return RoutingProof(
        endpoint_slug=f"azure/{clean_model}|azure",
        upstream_provider="azure",
        upstream_model=clean_model,
        model_snapshot=model_snapshot,
        router="azure",
        is_verified=False,
        metadata={"source": "x-ms-served-model", "served_model": clean_model},
    )


def _parse_slug_string(
    slug: str,
    router: str = "openrouter",
    metadata: dict[str, Any] | None = None,
) -> RoutingProof:
    """
    Parses a slug like 'openai/gpt-5.6-sol-20260709|openai' into structured components.
    """
    meta = metadata or {}
    upstream_provider = (
        meta.get("provider", "unknown") if isinstance(meta, dict) else "unknown"
    )
    upstream_model = slug

    if "|" in slug:
        parts = slug.split("|", 1)
        upstream_model = parts[0].strip()
        upstream_provider = parts[1].strip()
    elif "/" in slug:
        # e.g. 'openai/gpt-5.6-sol'
        upstream_provider = slug.split("/", 1)[0].strip()

    # Detect snapshot date stamp (e.g. 20260709 or 2024-08-06)
    snapshot_match = re.search(r"(\d{4}-?\d{2}-?\d{2}|\d{8})", upstream_model)
    model_snapshot = snapshot_match.group(1) if snapshot_match else None

    return RoutingProof(
        endpoint_slug=slug,
        upstream_provider=upstream_provider,
        upstream_model=upstream_model,
        model_snapshot=model_snapshot,
        router=router,
        is_verified=False,
        metadata=meta,
    )


def verify_routing_proof_against_model(
    claimed_model: str,
    proof: RoutingProof,
) -> tuple[bool, str]:
    """
    Compares the claimed model against the provider-reported upstream model.
    Returns (is_match, message).
    """
    from attest.comparator.quick import is_compatible_model_name

    is_match, reason = is_compatible_model_name(claimed_model, proof.upstream_model)
    if is_match:
        return (
            True,
            (
                f"Provider-reported routing matches: upstream model '{proof.upstream_model}' "
                f"via {proof.upstream_provider} ({reason}; unsigned, not proof of authenticity)"
            ),
        )

    return (
        False,
        (
            f"Routing metadata mismatch: claimed '{claimed_model}', but the provider's own "
            f"routing metadata reports '{proof.upstream_model}' via {proof.upstream_provider}"
        ),
    )
