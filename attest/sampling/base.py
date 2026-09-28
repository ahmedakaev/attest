"""
Abstract base class for LLM provider adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from attest.models import RawSample


class ProviderAdapter(ABC):
    """Base interface for all LLM provider connectors."""

    @abstractmethod
    async def sample(
        self,
        prompt_id: int,
        prompt_text: str,
        params: dict[str, Any],
        messages: list[dict[str, Any]] | None = None,
    ) -> RawSample:
        """Query the model with a single prompt and return standard RawSample."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Gracefully release HTTP clients and connections."""
        ...
