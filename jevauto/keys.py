"""API keys stored in the OS credential vault (Windows Credential Manager via keyring).

Keys never touch disk in plaintext or shell history. At startup `load_into_env()` copies
any stored key into os.environ for this process only, so the TypeSafe and Anthropic SDKs
pick them up with their normal env-var lookup.

Any env-var-style name can be stored. Names (not values) of custom keys are kept in an index
entry in the same vault so they can be listed; Credential Manager itself can't enumerate them.
"""

from __future__ import annotations

import getpass
import json
import os
import re

import keyring
from keyring.errors import PasswordDeleteError

SERVICE = "jevauto"
KNOWN_KEYS = ("TYPESAFE_API_KEY", "OPENJEV_API_KEY", "ANTHROPIC_API_KEY")
_INDEX = "__names__"
_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")


def valid_name(name: str) -> bool:
    return bool(_NAME.match(name)) and name != _INDEX


def _custom_names() -> list[str]:
    raw = keyring.get_password(SERVICE, _INDEX)
    try:
        return [n for n in json.loads(raw) if valid_name(n)] if raw else []
    except ValueError:
        return []


def names() -> list[str]:
    """Known keys first, then any custom names that have been stored."""
    return list(KNOWN_KEYS) + [n for n in _custom_names() if n not in KNOWN_KEYS]


def get(name: str) -> str | None:
    return keyring.get_password(SERVICE, name)


def set_(name: str, value: str) -> None:
    if not valid_name(name):
        raise ValueError("name must look like an env var: CAPITALS, digits and _ (e.g. OPENJEV_API_KEY)")
    value = value.strip()
    if not value or any(c.isspace() for c in value):
        raise ValueError("key is empty or contains whitespace")
    keyring.set_password(SERVICE, name, value)
    custom = _custom_names()
    if name not in KNOWN_KEYS and name not in custom:
        keyring.set_password(SERVICE, _INDEX, json.dumps(sorted(custom + [name])))


def delete(name: str) -> bool:
    custom = _custom_names()
    if name in custom:
        keyring.set_password(SERVICE, _INDEX, json.dumps([n for n in custom if n != name]))
    try:
        keyring.delete_password(SERVICE, name)
        return True
    except PasswordDeleteError:
        return False


def masked(value: str) -> str:
    return f"{value[:4]}…{value[-4:]}" if len(value) > 12 else "****"


def read_clipboard() -> str:
    import tkinter

    root = tkinter.Tk()
    root.withdraw()
    try:
        return root.clipboard_get()
    finally:
        root.destroy()


def clear_clipboard() -> None:
    import tkinter

    root = tkinter.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.update()
    root.destroy()


def prompt_and_store(name: str, from_clipboard: bool = False) -> str:
    if from_clipboard:
        value = read_clipboard()
        clear_clipboard()
    else:
        value = getpass.getpass(f"Paste {name} (input hidden): ")
    set_(name, value)
    return masked(value.strip())


def import_from_env(name: str) -> bool:
    """Move a key that is already in the environment into the vault."""
    value = os.environ.get(name) or _windows_user_env(name)
    if not value:
        return False
    set_(name, value)
    return True


def _windows_user_env(name: str) -> str | None:
    """A user env var saved in the registry but not yet inherited by this process
    (set after the terminal was opened)."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0] or None
    except (ImportError, OSError):
        return None


def load_into_env(only: tuple[str, ...] | None = None) -> list[str]:
    """Populate os.environ from the vault, then from saved Windows user env vars.
    A variable already in this process's environment wins. Returns names loaded."""
    loaded = []
    for name in only or names():
        if os.environ.get(name):
            continue
        value = get(name) or _windows_user_env(name)
        if value:
            os.environ[name] = value
            loaded.append(name)
    return loaded
