from attest.providers import (
    canonicalize_model_name,
    get_provider,
    list_providers,
)


def test_provider_registry():
    providers = list_providers()
    assert len(providers) >= 7

    openai = get_provider("openai")
    assert openai is not None
    assert openai.is_trusted_reference is True
    assert "https://api.openai.com/v1" in openai.base_url
    assert "gpt-5.5" in openai.popular_models

    deepseek = get_provider("deepseek")
    assert deepseek is not None

    custom = get_provider("custom")
    assert custom is not None

    openrouter = get_provider("openrouter")
    assert openrouter is not None
    assert openrouter.base_url == "https://openrouter.ai/api/v1"
    # Namespaced ids pass through untouched; no vendor is forced on other models
    assert openrouter.format_model_call("openai/gpt-5.5") == "openai/gpt-5.5"
    assert (
        openrouter.format_model_call("anthropic/claude-sonnet-5")
        == "anthropic/claude-sonnet-5"
    )
    # Without a fixed prefix the vendor namespace is part of the model id
    assert openrouter.clean_model_name("openai/gpt-5.5") == "openai/gpt-5.5"


def test_canonicalize_model_name():
    assert canonicalize_model_name("openai/gpt-5.5") == "gpt-5.5"
    assert canonicalize_model_name("anthropic/claude-fable-5-1") == "claude-fable-5-1"
    assert canonicalize_model_name("meta-llama/llama-4-scout") == "llama-4-scout"
    assert canonicalize_model_name("gpt-5.6-luna") == "gpt-5.6-luna"
    assert canonicalize_model_name("") == ""
