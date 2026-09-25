"""Shared data types: what a surface observes and what the planner asks it to do."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Protocol

# Secret-looking strings are masked before any screen content reaches Jev or Claude.
_SECRET = re.compile(
    r"(?:sk-[A-Za-z0-9_\-]{16,}|sk-ant-[A-Za-z0-9_\-]{16,}|github_pat_[A-Za-z0-9_]{8,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[abprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+"
    r"|(?:api[_-]?key|token|secret|passw(?:or)?d)[_:=\s-]*[A-Za-z0-9_\-]{12,}"
    r"|\b[A-Fa-f0-9]{32,}\b|\b(?=[A-Za-z0-9+_\-]*\d)[A-Za-z0-9+_\-]{40,}={0,2})",  # no '/': keeps URLs and paths
    re.I,
)


def redact(text: str) -> str:
    return _SECRET.sub("[redacted]", text) if text else text

Action = Literal["click", "fill", "select", "press", "check", "hover"]
ACTIONS: tuple[Action, ...] = ("click", "fill", "select", "press", "check", "hover")


@dataclass
class Element:
    id: str
    role: str
    name: str = ""
    value: str = ""
    placeholder: str = ""
    context: str = ""  # enclosing form/dialog/section label, if any
    attrs: dict[str, str] = field(default_factory=dict)  # href, input type, checked, disabled…
    in_view: bool = True

    def __post_init__(self) -> None:
        self.name, self.value, self.placeholder, self.context = (
            redact(self.name), redact(self.value), redact(self.placeholder), redact(self.context))
        self.attrs = {k: redact(v) for k, v in self.attrs.items()}

    def describe(self) -> str:
        """One-line natural-language description, used for Jev criteria and for Claude."""
        parts = [self.role]
        if self.name:
            parts.append(f'"{self.name}"')
        if self.placeholder and self.placeholder != self.name:
            parts.append(f"placeholder \"{self.placeholder}\"")
        if self.value:
            shown = "••••" if self.attrs.get("type") == "password" else self.value[:60]
            parts.append(f'value "{shown}"')
        for k in ("type", "href", "checked", "disabled", "expanded"):
            if k in self.attrs:
                parts.append(f"{k}={self.attrs[k][:80]}")
        if self.context:
            parts.append(f"in {self.context}")
        if not self.in_view:
            parts.append("(off-screen)")
        return " ".join(parts)

    @property
    def is_secret_field(self) -> bool:
        return self.attrs.get("type") == "password"


@dataclass
class Observation:
    title: str
    location: str  # URL for browsers, process/window for desktop apps
    elements: list[Element]
    text: str  # trimmed visible text, for blocker and postcondition checks

    def __post_init__(self) -> None:
        self.title, self.location, self.text = redact(self.title), redact(self.location), redact(self.text)

    def by_id(self, element_id: str) -> Element | None:
        return next((e for e in self.elements if e.id == element_id), None)

    def render(self, max_elements: int = 250) -> str:
        """Compact listing for the planner."""
        lines = [f"TITLE: {self.title}", f"LOCATION: {self.location}", "ELEMENTS:"]
        lines += [f"  [{e.id}] {e.describe()}" for e in self.elements[:max_elements]]
        if len(self.elements) > max_elements:
            lines.append(f"  … {len(self.elements) - max_elements} more elements not shown")
        lines += ["VISIBLE TEXT (truncated):", self.text[:2500]]
        return "\n".join(lines)


class Surface(Protocol):
    """Something that can be observed and acted on: a browser page or a desktop window."""

    kind: str

    def observe(self) -> Observation: ...

    def perform(self, action: Action, element: Element, text: str | None) -> None: ...

    def navigate(self, target: str) -> None: ...

    def close(self) -> None: ...
