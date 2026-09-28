"""
Level 3: Maximum Mean Discrepancy (MMD) with RBF Kernel & Permutation Test.
Provides rigorous two-sample hypothesis testing for ambiguous cases.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial.distance import cdist

from attest.config import ThresholdsConfig
from attest.models import MethodTier, RawSample, Score, Verdict


def rbf_kernel(x: np.ndarray, y: np.ndarray, gamma: float) -> np.ndarray:
    """Computes Gaussian RBF kernel matrix between matrices x and y."""
    dist_sq = cdist(x, y, metric="sqeuclidean")
    return np.exp(-gamma * dist_sq)


def compute_mmd(x: np.ndarray, y: np.ndarray, gamma: float | None = None) -> float:
    """
    Computes empirical Maximum Mean Discrepancy (MMD^2) between feature vectors x and y.
    """
    m = x.shape[0]
    n = y.shape[0]
    if m == 0 or n == 0:
        return 0.0

    # Estimate gamma using the median heuristic if not provided
    if gamma is None:
        combined = np.vstack([x, y])
        dists = cdist(combined, combined, metric="euclidean")
        # Extract upper triangle non-zero elements
        upper_idx = np.triu_indices_from(dists, k=1)
        pairwise_dists = dists[upper_idx]
        median_dist = (
            float(np.median(pairwise_dists)) if len(pairwise_dists) > 0 else 1.0
        )
        if median_dist <= 1e-6:
            median_dist = 1.0
        gamma = 1.0 / (2.0 * (median_dist**2))

    k_xx = rbf_kernel(x, x, gamma)
    k_yy = rbf_kernel(y, y, gamma)
    k_xy = rbf_kernel(x, y, gamma)

    mmd_sq = float(
        (k_xx.sum() / (m * m)) + (k_yy.sum() / (n * n)) - (2.0 * k_xy.sum() / (m * n))
    )
    return max(0.0, mmd_sq)


def permutation_test(
    x: np.ndarray,
    y: np.ndarray,
    n_resamples: int = 500,
    rng_seed: int = 42,
) -> tuple[float, float]:
    """
    Runs Monte Carlo permutation test for MMD^2.
    Returns:
        (observed_mmd, p_value)
    """
    m = x.shape[0]
    n = y.shape[0]
    total = m + n

    combined = np.vstack([x, y])
    # Compute median heuristic on the full pooled dataset
    dists = cdist(combined, combined, metric="euclidean")
    upper_idx = np.triu_indices_from(dists, k=1)
    pairwise_dists = dists[upper_idx]
    median_dist = float(np.median(pairwise_dists)) if len(pairwise_dists) > 0 else 1.0
    if median_dist <= 1e-6:
        median_dist = 1.0
    gamma = 1.0 / (2.0 * (median_dist**2))

    observed_mmd = compute_mmd(x, y, gamma=gamma)
    if observed_mmd <= 1e-8:
        return 0.0, 1.0

    rng = np.random.default_rng(rng_seed)
    greater_count = 0

    for _ in range(n_resamples):
        shuffled_indices = rng.permutation(total)
        idx_x = shuffled_indices[:m]
        idx_y = shuffled_indices[m:]

        perm_x = combined[idx_x]
        perm_y = combined[idx_y]

        perm_mmd = compute_mmd(perm_x, perm_y, gamma=gamma)
        if perm_mmd >= observed_mmd:
            greater_count += 1

    p_value = (greater_count + 1) / (n_resamples + 1)
    return observed_mmd, float(p_value)


def compute_mmd_permutation(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    run_id: int,
    thresholds: ThresholdsConfig,
    n_resamples: int = 500,
) -> list[Score]:
    """
    Runs Level 3 MMD permutation testing on response-shape features.

    Latency is deliberately excluded: it reflects network path and datacenter as much
    as the model, so cross-provider audits would otherwise turn a latency-only WARN
    (which triggers this level) into a FAIL. Samples are restricted to prompts present
    on both sides so a different battery mix does not masquerade as a model change.
    """
    common_ids = {s.prompt_id for s in baseline_samples} & {
        s.prompt_id for s in run_samples
    }
    baseline_samples = [s for s in baseline_samples if s.prompt_id in common_ids]
    run_samples = [s for s in run_samples if s.prompt_id in common_ids]

    if len(baseline_samples) < 5 or len(run_samples) < 5:
        return [
            Score(
                id=None,
                run_id=run_id,
                method=MethodTier.MMD_PERMUTATION.value,
                scope="aggregate",
                value=1.0,
                threshold=thresholds.mmd_pvalue_fail,
                verdict=Verdict.SKIP,
                details={
                    "message": "Insufficient sample volume for permutation testing (need >=5)"
                },
            )
        ]

    # Feature vector per sample: [log(char_len + 1), log(completion_tokens + 1)]
    def extract_features(samples: list[RawSample]) -> np.ndarray:
        matrix = []
        for s in samples:
            char_len = len(s.raw_text)
            tokens = s.usage.get("completion_tokens") if s.usage else None
            if not isinstance(tokens, (int, float)):
                tokens = 0
            matrix.append([np.log1p(char_len), np.log1p(float(tokens))])
        return np.array(matrix, dtype=np.float64)

    x = extract_features(baseline_samples)
    y = extract_features(run_samples)

    observed_mmd, p_val = permutation_test(x, y, n_resamples=n_resamples)

    if p_val < thresholds.mmd_pvalue_fail:
        verdict = Verdict.FAIL
    elif p_val < thresholds.mmd_pvalue_warn:
        verdict = Verdict.WARN
    else:
        verdict = Verdict.PASS

    score = Score(
        id=None,
        run_id=run_id,
        method=MethodTier.MMD_PERMUTATION.value,
        scope="aggregate",
        value=round(p_val, 4),
        threshold=thresholds.mmd_pvalue_fail,
        verdict=verdict,
        details={
            "observed_mmd": round(observed_mmd, 6),
            "p_value": round(p_val, 4),
            "resamples": n_resamples,
            "baseline_count": len(baseline_samples),
            "run_count": len(run_samples),
        },
    )
    return [score]
