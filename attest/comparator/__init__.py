"""
Multi-tier comparator package for Attest.
"""

from attest.comparator.compare import ComparisonResult, compare_runs
from attest.comparator.distribution import compare_distributions_jsd
from attest.comparator.embedding import compare_semantic_embeddings
from attest.comparator.latency import compare_latency_throughput
from attest.comparator.mmd import compute_mmd_permutation
from attest.comparator.pipeline import ComparatorPipeline, PipelineResult
from attest.comparator.quick import run_quick_checks

__all__ = [
    "ComparatorPipeline",
    "ComparisonResult",
    "PipelineResult",
    "compare_distributions_jsd",
    "compare_latency_throughput",
    "compare_runs",
    "compare_semantic_embeddings",
    "compute_mmd_permutation",
    "run_quick_checks",
]
