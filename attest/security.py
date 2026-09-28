"""
Security and Key Management for Attest.

Handles:
- Environment variable key resolution (highest priority, never touches disk)
- At-rest encryption for keys stored in SQLite using Fernet
- Master key generation and storage in ~/.attest/master.key (mode 0600)
- API key masking for logs, terminal outputs, and reports
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet

DEFAULT_ATTEST_DIR = Path.home() / ".attest"
DEFAULT_MASTER_KEY_FILE = DEFAULT_ATTEST_DIR / "master.key"


def _derive_fernet_key(raw: bytes) -> bytes:
    """Ensure key is exactly 32 url-safe base64 bytes for Fernet."""
    try:
        Fernet(raw)
        return raw
    except (ValueError, TypeError):
        import base64
        import hashlib

        digest = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(digest)


def get_or_create_master_key() -> bytes:
    """
    Retrieve or initialize the master encryption key.
    Checks ATTEST_MASTER_KEY env variable first, then ~/.attest/master.key.
    """
    env_key = os.getenv("ATTEST_MASTER_KEY")
    if env_key:
        return _derive_fernet_key(env_key.encode("utf-8").strip())

    if DEFAULT_MASTER_KEY_FILE.exists():
        with open(DEFAULT_MASTER_KEY_FILE, "rb") as f:
            content = f.read().strip()
            return _derive_fernet_key(content)

    # Create new master key with secure file permissions (0600)
    DEFAULT_ATTEST_DIR.mkdir(parents=True, exist_ok=True)
    new_key = Fernet.generate_key()
    with open(DEFAULT_MASTER_KEY_FILE, "wb") as f:
        f.write(new_key)
    DEFAULT_MASTER_KEY_FILE.chmod(0o600)
    return new_key


def encrypt_api_key(api_key: str) -> str:
    """Encrypt plain API key into a safe ciphertext string for database storage."""
    if not api_key:
        return ""
    master_key = get_or_create_master_key()
    fernet = Fernet(master_key)
    return fernet.encrypt(api_key.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt stored ciphertext back to plaintext API key."""
    if not encrypted_key:
        return ""
    master_key = get_or_create_master_key()
    fernet = Fernet(master_key)
    return fernet.decrypt(encrypted_key.encode("utf-8")).decode("utf-8")


def sanitize_target_id_for_env(target_id: str) -> str:
    """Convert target id like 'openrouter-gpt4o' to 'OPENROUTER_GPT4O'."""
    return re.sub(r"[^A-Za-z0-9]", "_", target_id).upper()


VENDOR_ENV_VARS: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "anthropic_proxy": ["ANTHROPIC_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
}

# Official API hosts for each vendor. A vendor env key (e.g. OPENAI_API_KEY) is only
# ever sent to these hosts, never to a third-party reseller or proxy under audit.
VENDOR_HOSTS: dict[str, tuple[str, ...]] = {
    "openai": ("api.openai.com",),
    "openrouter": ("openrouter.ai",),
    "deepseek": ("api.deepseek.com",),
    "anthropic": ("api.anthropic.com",),
    "groq": ("api.groq.com",),
    "together": ("api.together.xyz", "api.together.ai"),
    "gemini": ("generativelanguage.googleapis.com",),
}


def url_hostname(url: str | None) -> str:
    """Return the lowercase hostname of a URL ('' if it cannot be parsed)."""
    if not url:
        return ""
    raw = url.strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        return (urlparse(raw).hostname or "").lower()
    except ValueError:
        return ""


def _host_matches(host: str, allowed: tuple[str, ...]) -> bool:
    return any(host == h or host.endswith(f".{h}") for h in allowed)


def vendor_for_url(base_url: str | None) -> str | None:
    """Return the vendor whose official API host serves base_url, if any."""
    host = url_hostname(base_url)
    if not host:
        return None
    for vendor, hosts in VENDOR_HOSTS.items():
        if _host_matches(host, hosts):
            return vendor
    return None


def detect_env_key_for_provider(provider_id: str) -> tuple[bool, str, str]:
    """
    Checks if an environment variable exists for a given provider preset.
    Returns (has_key, masked_preview, source_var_name).
    """
    prov_key = provider_id.lower().strip()
    # Check ATTEST_API_KEY_<PROVIDER_ID> first
    specific_env = f"ATTEST_API_KEY_{sanitize_target_id_for_env(prov_key)}"
    val = os.getenv(specific_env)
    if val:
        return True, mask_key(val.strip()), specific_env

    # Check known vendor env vars
    candidates = VENDOR_ENV_VARS.get(prov_key, [])
    for env_var in candidates:
        val = os.getenv(env_var)
        if val:
            return True, mask_key(val.strip()), env_var

    # Check general fallback
    val = os.getenv("ATTEST_API_KEY")
    if val:
        return True, mask_key(val.strip()), "ATTEST_API_KEY"

    return False, "", ""


def resolve_api_key(
    target_id: str,
    stored_encrypted_key: str | None = None,
    base_url: str | None = None,
) -> tuple[str, str]:
    """
    Resolves the API key for a target with strict security precedence:
    1. Target-specific env var: ATTEST_API_KEY_<TARGET_ID>
    2. Encrypted key stored for this target in the local SQLite database
    3. Vendor env var (e.g. OPENAI_API_KEY) -- only when base_url is that vendor's
       official API host, so vendor keys never leak to resellers under audit
    4. General env var: ATTEST_API_KEY (explicit catch-all opt-in)

    Returns:
        (plaintext_key, source_description)
    """
    specific_env_name = f"ATTEST_API_KEY_{sanitize_target_id_for_env(target_id)}"
    val = os.getenv(specific_env_name)
    if val:
        return val.strip(), f"env:{specific_env_name}"

    if stored_encrypted_key:
        try:
            return decrypt_api_key(stored_encrypted_key), "encrypted_db"
        except Exception as err:
            raise ValueError(
                f"Failed to decrypt stored API key for target '{target_id}'. "
                f"Ensure ~/.attest/master.key or ATTEST_MASTER_KEY is valid. Details: {err}"
            ) from err

    vendor = vendor_for_url(base_url)
    if vendor:
        for v_env in VENDOR_ENV_VARS.get(vendor, []):
            val = os.getenv(v_env)
            if val:
                return val.strip(), f"env:{v_env}"

    val = os.getenv("ATTEST_API_KEY")
    if val:
        return val.strip(), "env:ATTEST_API_KEY"

    return "", "none"


def mask_key_for_diagnostics(key: str | None) -> str:
    """Longer mask for error messages, in the format vendor dashboards show keys
    ('test-or-key-433...fda'), so the user can tell which of their keys was sent."""
    if not key:
        return "<not set>"
    clean = key.strip()
    if len(clean) < 24:
        return mask_key(clean)
    return f"{clean[:12]}...{clean[-3:]}"


def mask_key(key: str | None) -> str:
    """Return a masked representation of an API key, e.g., 'sk-...c1d4'."""
    if not key:
        return "<not set>"
    clean = key.strip()
    if len(clean) <= 8:
        return "***"
    prefix = clean[:3]
    suffix = clean[-4:]
    return f"{prefix}...{suffix}"
