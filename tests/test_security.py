from attest.security import (
    decrypt_api_key,
    encrypt_api_key,
    mask_key,
    resolve_api_key,
    sanitize_target_id_for_env,
)


def test_encryption_roundtrip():
    original = "test-sample-encryption-secret-value-xyz"
    encrypted = encrypt_api_key(original)
    assert encrypted != original
    decrypted = decrypt_api_key(encrypted)
    assert decrypted == original


def test_mask_key():
    assert mask_key("test-abcdefgh1234") == "tes...1234"
    assert mask_key("short") == "***"
    assert mask_key("") == "<not set>"
    assert mask_key(None) == "<not set>"


def test_sanitize_target_id_for_env():
    assert sanitize_target_id_for_env("openrouter-gpt4o") == "OPENROUTER_GPT4O"
    assert sanitize_target_id_for_env("deepseek.v3") == "DEEPSEEK_V3"


def test_resolve_api_key_precedence(monkeypatch):
    target_id = "test-provider"
    env_var = "ATTEST_API_KEY_TEST_PROVIDER"
    enc_db_key = encrypt_api_key("test-from-db-1234")

    # 1. No env vars set -> DB key used
    key, src = resolve_api_key(target_id, enc_db_key)
    assert key == "test-from-db-1234"
    assert src == "encrypted_db"

    # 2. Generic env keys never override the target's own stored key
    monkeypatch.setenv("OPENAI_API_KEY", "test-from-openai-env")
    monkeypatch.setenv("ATTEST_API_KEY", "test-from-general-env")
    key, src = resolve_api_key(
        target_id, enc_db_key, base_url="https://api.openai.com/v1"
    )
    assert key == "test-from-db-1234"

    # 3. Target-specific env var overrides everything
    monkeypatch.setenv(env_var, "test-target-specific-env")
    key, src = resolve_api_key(target_id, enc_db_key)
    assert key == "test-target-specific-env"
    assert src == f"env:{env_var}"


def test_resolve_api_key_vendor_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-token-1234")
    key, src = resolve_api_key(
        "openrouter-gpt4o", base_url="https://openrouter.ai/api/v1"
    )
    assert key == "test-openrouter-token-1234"
    assert src == "env:OPENROUTER_API_KEY"


def test_vendor_env_key_never_sent_to_third_party_host(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-real-openai-key")
    # Target id mentions the vendor, but the host is a reseller under audit
    for target_id, url in [
        ("shady-reseller-gpt4o", "https://reseller.example/v1"),
        ("reseller-openai-proxy", "https://reseller.example/v1"),
        ("lookalike", "https://api.openai.com.evil.example/v1"),
        ("no-url", None),
    ]:
        key, src = resolve_api_key(target_id, base_url=url)
        assert key == "", (target_id, src)

    key, _ = resolve_api_key("my-gpt", base_url="https://api.openai.com/v1")
    assert key == "test-real-openai-key"


def test_detect_env_key_for_provider(monkeypatch):
    from attest.security import detect_env_key_for_provider

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-token-9988776655")
    has_key, preview, source = detect_env_key_for_provider("deepseek")
    assert has_key is True
    assert "tes...6655" in preview
    assert source == "DEEPSEEK_API_KEY"

    has_key_fake, _, _ = detect_env_key_for_provider("unknown_vendor_xyz")
    assert has_key_fake is False
