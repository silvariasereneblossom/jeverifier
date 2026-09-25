"""Key vault and provider selection, against an in-memory keyring (never the real vault)."""

from __future__ import annotations

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from jevauto import jev, keys


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.data.get((service, username))

    def set_password(self, service, username, password):
        self.data[(service, username)] = password

    def delete_password(self, service, username):
        if self.data.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def memory_vault(monkeypatch):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    monkeypatch.setattr(keys, "_windows_user_env", lambda name: None)
    for k in ("TYPESAFE_API_KEY", "OPENJEV_API_KEY", "ANTHROPIC_API_KEY", "MY_SERVICE_API_KEY",
              "JEVAUTO_JEV_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    yield
    keyring.set_keyring(previous)


def test_custom_keys_are_listed_loaded_and_deleted(monkeypatch):
    keys.set_("MY_SERVICE_API_KEY", "abc123def456ghi")
    assert "MY_SERVICE_API_KEY" in keys.names()
    assert "MY_SERVICE_API_KEY" in keys.load_into_env()
    assert keys.delete("MY_SERVICE_API_KEY")
    assert "MY_SERVICE_API_KEY" not in keys.names()


def test_bad_names_and_values_are_rejected():
    for name in ("lowercase", "HAS SPACE", "__names__", "1STARTS_WITH_DIGIT"):
        with pytest.raises(ValueError):
            keys.set_(name, "abc123def456")
    with pytest.raises(ValueError):
        keys.set_("GOOD_NAME", "has a space")


def test_provider_prefers_typesafe_then_openjev(monkeypatch):
    with pytest.raises(RuntimeError):
        jev.choose()
    keys.set_("OPENJEV_API_KEY", "oj-key-1234567890")
    assert jev.choose().name == "openjev"
    keys.set_("TYPESAFE_API_KEY", "sk-key-1234567890")
    monkeypatch.delenv("OPENJEV_API_KEY", raising=False)
    assert jev.choose().name == "typesafe"
    monkeypatch.setenv("JEVAUTO_JEV_PROVIDER", "openjev")
    p = jev.choose()
    assert (p.name, p.base_url, p.model) == ("openjev", "https://api.openjev.sh", "openjev")
