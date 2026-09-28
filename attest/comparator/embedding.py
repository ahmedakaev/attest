"""
Level 2: 100% Local Text Similarity (Embeddings & Semantic Cosine).
Completely self-contained. No external API calls, no network leakage.
Supports local sentence-transformers / fastembed if available, with built-in
subword n-gram TF-IDF cosine similarity fallback.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import numpy as np

from attest.config import ThresholdsConfig
from attest.models import MethodTier, PromptItem, RawSample, Score, Verdict


class LocalTextVectorizer:
    """
    High-performance 100% local text vectorizer.
    Combines character 3-5 n-grams and word tokens for semantic and stylistic similarity.
    """

    def __init__(
        self, model_name: str = "all-MiniLM-L6-v2", allow_download: bool = False
    ):
        self.model_name = model_name
        self.allow_download = allow_download
        self._dense_model = None
        self._tried_dense = False

    def _get_dense_model(self):
        if self._tried_dense:
            return self._dense_model
        self._tried_dense = True
        try:
            # Check if sentence_transformers is available locally
            from sentence_transformers import SentenceTransformer

            # Only load from the local cache unless downloads were explicitly allowed,
            # keeping the "no network" guarantee of this level.
            self._dense_model = SentenceTransformer(
                self.model_name, local_files_only=not self.allow_download
            )
        except (ImportError, RuntimeError, OSError, ValueError, TypeError):
            self._dense_model = None
        return self._dense_model

    @property
    def mode(self) -> str:
        if self._get_dense_model() is not None:
            return f"sentence-transformers ({self.model_name})"
        return "ngram_fallback (subword TF-IDF)"

    def _extract_features(self, text: str) -> Counter[str]:
        clean = text.lower().strip()
        words = re.findall(r"\b\w+\b", clean)
        features: Counter[str] = Counter()

        # Word unigrams and bigrams
        for w in words:
            features[f"w:{w}"] += 1
        for i in range(len(words) - 1):
            features[f"w2:{words[i]}_{words[i + 1]}"] += 1

        # Character 3-grams and 4-grams (captures code syntax, morphology, tone)
        for n in (3, 4):
            for i in range(max(0, len(clean) - n + 1)):
                features[f"c{n}:{clean[i : i + n]}"] += 1

        return features

    def cosine_similarity(self, text_a: str, text_b: str) -> float:
        """Calculate pairwise cosine similarity between two texts."""
        if not text_a.strip() or not text_b.strip():
            return 0.0

        dense = self._get_dense_model()
        if dense is not None:
            try:
                embeds = dense.encode([text_a, text_b], normalize_embeddings=True)
                return float(np.dot(embeds[0], embeds[1]))
            except (RuntimeError, ValueError):
                pass

        # N-gram sparse cosine similarity
        feat_a = self._extract_features(text_a)
        feat_b = self._extract_features(text_b)

        common_keys = set(feat_a.keys()) & set(feat_b.keys())
        if not common_keys:
            return 0.0

        dot = sum(feat_a[k] * feat_b[k] for k in common_keys)
        norm_a = math.sqrt(sum(v * v for v in feat_a.values()))
        norm_b = math.sqrt(sum(v * v for v in feat_b.values()))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return max(0.0, min(1.0, dot / (norm_a * norm_b)))


_VECTORIZER_CACHE: dict[tuple[str, bool], LocalTextVectorizer] = {}


def get_vectorizer(
    model_name: str, allow_download: bool = False
) -> LocalTextVectorizer:
    """Process-wide vectorizer cache so the dense model is loaded once, not per run."""
    key = (model_name, allow_download)
    if key not in _VECTORIZER_CACHE:
        _VECTORIZER_CACHE[key] = LocalTextVectorizer(model_name, allow_download)
    return _VECTORIZER_CACHE[key]


def compare_semantic_embeddings(
    baseline_samples: list[RawSample],
    run_samples: list[RawSample],
    prompts_map: dict[int, PromptItem],
    run_id: int,
    thresholds: ThresholdsConfig,
) -> list[Score]:
    """
    Compare long-form responses (code, factual, style, refusal, canary) using local similarity.
    """
    model_name = getattr(thresholds, "embedding_model", "all-MiniLM-L6-v2")
    vectorizer = get_vectorizer(
        model_name, getattr(thresholds, "embedding_allow_download", False)
    )

    # Keep capability probes only: one-token and random-string answers have their
    # own distribution checks, and tokenizer probes ('Hello') exist for their input
    # token counts; the small talk they get back says nothing about the model
    target_prompts = [
        p
        for p in prompts_map.values()
        if p.category not in ("one_token", "bpe_fingerprint", "iris", "tokenizer_probe")
        and p.id is not None
    ]

    if not target_prompts:
        return [
            Score(
                id=None,
                run_id=run_id,
                method=MethodTier.EMBEDDING_COSINE.value,
                scope="aggregate",
                value=1.0,
                threshold=thresholds.embedding_cosine_fail,
                verdict=Verdict.SKIP,
                details={"message": "No capability prompts to compare with embeddings"},
            )
        ]

    base_by_prompt: dict[int, list[str]] = {}
    for s in baseline_samples:
        base_by_prompt.setdefault(s.prompt_id, []).append(s.raw_text)

    run_by_prompt: dict[int, list[str]] = {}
    for s in run_samples:
        run_by_prompt.setdefault(s.prompt_id, []).append(s.raw_text)

    prompt_scores: list[dict[str, Any]] = []
    category_sims: dict[str, list[float]] = {}
    all_sims: list[float] = []

    for p in target_prompts:
        if p.id is None:
            continue
        b_texts = base_by_prompt.get(p.id, [])
        r_texts = run_by_prompt.get(p.id, [])

        if not b_texts or not r_texts:
            continue

        # Average pairwise similarity across all samples of this prompt
        pair_sims = [
            vectorizer.cosine_similarity(b, r) for b in b_texts for r in r_texts
        ]
        avg_prompt_sim = float(np.mean(pair_sims)) if pair_sims else 0.0

        all_sims.append(avg_prompt_sim)
        category_sims.setdefault(p.category, []).append(avg_prompt_sim)

        prompt_scores.append(
            {
                "prompt_id": p.id,
                "category": p.category,
                "text": p.text[:40] + ("..." if len(p.text) > 40 else ""),
                "similarity": round(avg_prompt_sim, 4),
            }
        )

    if not all_sims:
        return [
            Score(
                id=None,
                run_id=run_id,
                method=MethodTier.EMBEDDING_COSINE.value,
                scope="aggregate",
                value=1.0,
                threshold=thresholds.embedding_cosine_fail,
                verdict=Verdict.SKIP,
                details={"message": "No samples collected for capability probes"},
            )
        ]

    overall_avg = float(np.mean(all_sims))
    is_dense = vectorizer._get_dense_model() is not None
    if is_dense:
        warn_th = thresholds.embedding_cosine_warn
        fail_th = thresholds.embedding_cosine_fail
    else:
        # Calibrated thresholds for lexical / subword n-gram cosine similarity.
        # Paraphrased responses have naturally lower lexical overlap than dense embeddings.
        warn_th = min(thresholds.embedding_cosine_warn, 0.70)
        fail_th = min(thresholds.embedding_cosine_fail, 0.55)

    if overall_avg < fail_th:
        verdict = Verdict.FAIL
    elif overall_avg < warn_th:
        verdict = Verdict.WARN
    else:
        verdict = Verdict.PASS

    cat_breakdown = {
        cat: round(float(np.mean(vals)), 4) for cat, vals in category_sims.items()
    }

    aggregate_score = Score(
        id=None,
        run_id=run_id,
        method=MethodTier.EMBEDDING_COSINE.value,
        scope="aggregate",
        value=round(overall_avg, 4),
        threshold=fail_th,
        verdict=verdict,
        details={
            "mean_cosine": round(overall_avg, 4),
            "vectorizer": vectorizer.mode,
            "by_category": cat_breakdown,
            "prompts": prompt_scores,
            "threshold_warn": warn_th,
            "threshold_fail": fail_th,
        },
    )

    return [aggregate_score]
