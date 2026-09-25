"""Which Jev endpoint to use. Both speak the same /v1/systemone API, so the TypeSafe SDK
works for either; only the base URL, key and model name differ.

  typesafe  TypeSafe's own API. Model pinned to jev-1.13.0 (policy thresholds were set on it).
  openjev   OpenJEV (openjev.sh), a third-party public gateway to Jev funded by $JEV token fees.
            It exposes a single model alias, "openjev", so the underlying Jev version can't be
            pinned or seen: re-check thresholds if its behavior shifts.

Default: typesafe if TYPESAFE_API_KEY is available, otherwise openjev. Force one with
JEVERIFIER_JEV_PROVIDER=typesafe|openjev.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from typesafe_sdk import TypeSafeClient

from . import keys


@dataclass(frozen=True)
class Provider:
    name: str
    key_env: str
    base_url: str | None
    model: str


PROVIDERS = {
    "typesafe": Provider("typesafe", "TYPESAFE_API_KEY", None, "jev-1.13.0"),
    "openjev": Provider("openjev", "OPENJEV_API_KEY", "https://api.openjev.sh", "openjev"),
}


def choose() -> Provider:
    keys.load_into_env(tuple(p.key_env for p in PROVIDERS.values()))
    forced = os.environ.get("JEVERIFIER_JEV_PROVIDER", "").strip().lower()
    if forced:
        if forced not in PROVIDERS:
            raise RuntimeError(f"JEVERIFIER_JEV_PROVIDER must be one of {', '.join(PROVIDERS)}")
        provider = PROVIDERS[forced]
    else:
        provider = next((p for p in PROVIDERS.values() if os.environ.get(p.key_env)), PROVIDERS["typesafe"])
    if not os.environ.get(provider.key_env):
        raise RuntimeError("No Jev key stored. Add TYPESAFE_API_KEY or OPENJEV_API_KEY in the keys "
                           "window (jeverifier keys gui).")
    return provider


def client(provider: Provider | None = None, model: str | None = None) -> TypeSafeClient:
    p = provider or choose()
    kwargs = {"base_url": p.base_url} if p.base_url else {}
    return TypeSafeClient(api_key=os.environ[p.key_env], model=model or p.model, **kwargs)
