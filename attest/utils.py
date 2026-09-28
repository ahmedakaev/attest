"""
General utility functions for Attest.
"""

from __future__ import annotations

import re

# Boundary-aware pattern matching for reasoning / chain-of-thought models.
# Matches models like o1, o3, o1-mini, o3-mini, gpt-6, gemini-3.7-thinking,
# gemini-3.8-flash, deepseek-r1, deepseek-reasoner, or custom thinking tags,
# while avoiding false positives on unrelated substrings like 'polo1', 'proto12', 'mascot'.
REASONING_MODEL_REGEX = re.compile(
    r"(?:"
    r"(?:^|[-_/])o[134](?:[-_/]|$)"
    r"|gpt-6"
    r"|gemini-3\.[789]"
    r"|deepseek[-_]r1"
    r"|(?:^|[-_/])r1(?:[-_/]|$)"
    r"|reasoner"
    r"|thinking"
    r"|(?:^|[-_/])cot(?:[-_/]|$)"
    r")",
    re.IGNORECASE,
)


# Models that think by default (or always) even without an explicit reasoning request:
# Claude Opus/Fable/Mythos 5.x (adaptive thinking, always on), GPT-5.x, DeepSeek V4 Pro,
# Qwen 3.x (hybrid thinking on by default). Their hidden thinking tokens count
# against max_tokens.
THINKING_BY_DEFAULT_REGEX = re.compile(
    r"(?:"
    r"claude-(?:opus|fable|mythos)-5"
    r"|gpt-5"
    r"|deepseek-v4-pro"
    r"|qwen-?3"
    r")",
    re.IGNORECASE,
)

# Output cap floor for thinking models: a probe cap of 1-5 tokens is spent on hidden
# thinking and the visible answer comes back empty. Only generated tokens are billed.
THINKING_MIN_OUTPUT_TOKENS = 2048


def needs_thinking_headroom(name: str | None) -> bool:
    """Return True if the model spends hidden thinking tokens from the output budget."""
    if not name:
        return False
    return is_reasoning_model_name(name) or bool(
        THINKING_BY_DEFAULT_REGEX.search(name.strip())
    )


def is_reasoning_model_name(name: str | None) -> bool:
    """
    Return True if the model name indicates an internal reasoning / thinking architecture
    (e.g., OpenAI o-series, Gemini 3.7+ Thinking, DeepSeek R1, GPT-6 Astra, Reasoner).
    """
    if not name:
        return False
    return bool(REASONING_MODEL_REGEX.search(name.strip()))


O1_TEMPERATURE_REJECT_REGEX = re.compile(
    r"(?:^|[-_/])o1-(?:preview|mini)(?:[-_/]|$)",
    re.IGNORECASE,
)


def rejects_custom_temperature(name: str | None) -> bool:
    """
    Return True if the model rejects custom temperature parameters (e.g., OpenAI o1-preview, o1-mini).
    """
    if not name:
        return False
    return bool(O1_TEMPERATURE_REJECT_REGEX.search(name.strip()))


def canonicalize_model_name(name: str) -> str:
    """
    Extract canonical model name by stripping known provider namespaces/prefixes.
    Example: 'openai/gpt-5.5' -> 'gpt-5.5', 'anthropic/claude-fable-5-1' -> 'claude-fable-5-1'.
    """
    if not name:
        return ""
    clean = name.strip()
    if "/" in clean:
        return clean.rsplit("/", 1)[-1]
    return clean


def calculate_token_cost(total_tokens: int, cost_per_million: float = 5.0) -> float:
    """
    Calculate estimated dollar cost from total token volume and cost per million tokens.
    """
    return (total_tokens / 1_000_000) * cost_per_million
