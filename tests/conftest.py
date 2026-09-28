import pytest

from attest.security import VENDOR_ENV_VARS


@pytest.fixture(autouse=True)
def _isolate_keys(monkeypatch):
    """Keep tests away from the developer's real API keys and ~/.attest/master.key."""
    monkeypatch.setenv("ATTEST_MASTER_KEY", "test-master-key-for-attest-suite")
    monkeypatch.delenv("ATTEST_API_KEY", raising=False)
    for env_vars in VENDOR_ENV_VARS.values():
        for name in env_vars:
            monkeypatch.delenv(name, raising=False)
