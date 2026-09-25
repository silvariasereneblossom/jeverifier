"""Windows desktop surface via UI Automation (pywinauto). Same shape as the browser surface."""

from __future__ import annotations

import re
import time

from pywinauto import Application, Desktop, mouse

from .model import Action, Element, Observation

_INTERACTIVE = {
    "Button", "Edit", "Document", "ComboBox", "CheckBox", "RadioButton", "MenuItem",
    "ListItem", "TreeItem", "TabItem", "Hyperlink", "SplitButton", "Slider", "DataItem",
}
_TEXTUAL = {"Text", "Document", "Edit", "StatusBar", "Header", "TitleBar"}
_ROLE = {"Edit": "textbox", "Document": "textbox", "ComboBox": "combobox", "Hyperlink": "link",
         "MenuItem": "menuitem", "ListItem": "option", "TreeItem": "treeitem", "TabItem": "tab"}


class DesktopSurface:
    kind = "desktop"

    def __init__(self, window: str | None = None, launch: str | None = None,
                 max_elements: int = 400) -> None:
        self.max_elements = max_elements
        self._ids: dict[tuple, str] = {}
        self._wrappers: dict[str, object] = {}
        self._next = 1
        if launch:
            Application(backend="uia").start(launch)
            time.sleep(2.0)
        if not window:
            raise ValueError("desktop surface needs a window title pattern (--window)")
        self.navigate(window)

    def navigate(self, target: str) -> None:
        """Attach to (and focus) the top-level window whose title matches `target` (regex)."""
        deadline = time.time() + 15
        pattern = re.compile(target, re.I)
        while True:
            wins = [w for w in Desktop(backend="uia").windows() if pattern.search(w.window_text() or "")]
            if len(wins) > 1:
                titles = "; ".join(w.window_text() for w in wins)
                raise LookupError(f"{target!r} matches {len(wins)} windows ({titles}); use a more specific pattern")
            if wins:
                self.window = wins[0]
                break
            if time.time() > deadline:
                raise LookupError(f"no window title matches {target!r}")
            time.sleep(0.5)
        # No set_focus here: taking focus steals the user's keystrokes from whatever they are typing in.
        # UI Automation invoke/set-text work unfocused; only the mouse/keyboard fallbacks call _front().

    def _id_for(self, wrapper) -> str:
        key = tuple(wrapper.element_info.runtime_id or ()) or (id(wrapper),)
        if key not in self._ids:
            self._ids[key] = f"d{self._next}"
            self._next += 1
        return self._ids[key]

    def observe(self) -> Observation:
        elements: list[Element] = []
        texts: list[str] = []
        self._wrappers.clear()
        for w in self.window.descendants():
            info = w.element_info
            ctype = info.control_type or ""
            name = (info.name or "").strip()
            try:
                if not w.is_visible():
                    continue
            except Exception:
                continue
            if ctype in _TEXTUAL and name:
                texts.append(name)
            if ctype not in _INTERACTIVE or len(elements) >= self.max_elements:
                continue
            attrs: dict[str, str] = {}
            try:
                if not w.is_enabled():
                    attrs["disabled"] = "true"
            except Exception:
                pass
            if ctype in ("CheckBox", "RadioButton"):
                try:
                    attrs["checked"] = str(bool(w.get_toggle_state()))
                except Exception:
                    pass
            value = ""
            if ctype in ("Edit", "Document", "ComboBox"):
                try:
                    value = (w.get_value() if hasattr(w, "get_value") else w.window_text()) or ""
                except Exception:
                    value = ""
                if value:
                    texts.append(value[:2000])
            eid = self._id_for(w)
            self._wrappers[eid] = w
            elements.append(Element(
                id=eid, role=_ROLE.get(ctype, ctype.lower()), name=name[:120],
                value=" ".join(value.split())[:200], context=(info.automation_id or "")[:60],
                attrs=attrs,
            ))
        return Observation(
            title=self.window.window_text(), location=f"desktop window (pid {self.window.process_id()})",
            elements=elements, text=" | ".join(texts)[:6000],
        )

    def perform(self, action: Action, element: Element, text: str | None) -> None:
        w = self._wrappers.get(element.id)
        if w is None:
            raise LookupError(f"element {element.id} is no longer present")
        if action == "click":
            # Invoke the control through UI Automation when it supports that: no real mouse
            # movement, so an overlapping window can't swallow the click.
            try:
                w.invoke()
            except Exception:
                self._front()
                w.click_input()
        elif action == "fill":
            if hasattr(w, "set_edit_text"):
                w.set_edit_text(text or "")
            else:
                self._front()
                w.click_input()
                w.type_keys(text or "", with_spaces=True, with_newlines=True)
        elif action == "select":
            w.select(text)
        elif action == "press":
            self._front()  # real keystrokes go to the focused window
            w.type_keys(_to_keys(text or "Enter"))
        elif action == "check":
            if hasattr(w, "toggle"):
                w.toggle()
            else:
                self._front()
                w.click_input()
        elif action == "hover":
            mouse.move(coords=w.rectangle().mid_point())
        else:
            raise ValueError(f"unsupported action {action!r}")
        time.sleep(0.4)  # let the app repaint before the next observation

    def _front(self) -> None:
        try:
            self.window.set_focus()
        except Exception:
            pass

    def close(self) -> None:
        pass  # never close the user's app on their behalf


def _to_keys(key: str) -> str:
    """Playwright-style key names ('Enter', 'Control+S') to pywinauto syntax."""
    mods = {"control": "^", "ctrl": "^", "shift": "+", "alt": "%"}
    parts = key.split("+")
    prefix = "".join(mods.get(p.lower(), "") for p in parts[:-1])
    last = parts[-1]
    return prefix + (last.lower() if len(last) == 1 else "{" + last.upper() + "}")
