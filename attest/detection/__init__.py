"""Infrastructure and proxy detection module for Attest."""

from attest.detection.infrastructure import (
    InfrastructureFingerprint,
    detect_infrastructure,
)

__all__ = ["InfrastructureFingerprint", "detect_infrastructure"]
