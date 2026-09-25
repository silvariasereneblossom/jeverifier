"""Small window for pasting API keys into Windows Credential Manager.

Shows the keys jeverifier knows about plus any custom ones you've added; "Add a key" stores a key
under any env-var-style name so other tools can use the same vault.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from . import keys

LABELS = {
    "TYPESAFE_API_KEY": "TypeSafe (Jev)",
    "OPENJEV_API_KEY": "OpenJEV (Jev)",
}


def _test(name: str, value: str) -> str:
    """Check the key works with the cheapest call each service offers."""
    try:
        if name in ("TYPESAFE_API_KEY", "OPENJEV_API_KEY"):
            from typesafe_sdk import Noul, TypeSafeClient

            from . import jev

            provider = jev.PROVIDERS["typesafe" if name == "TYPESAFE_API_KEY" else "openjev"]
            kwargs = {"base_url": provider.base_url} if provider.base_url else {}
            with TypeSafeClient(api_key=value, model=provider.model, **kwargs) as c:
                c.system_one("ping", {"ok": Noul(instructions="Is this text the word ping?")})
        else:
            return "no test for this key"
        return "✓ works"
    except Exception as err:  # show any failure in the window rather than crash it
        return f"✗ {type(err).__name__}"


class Row:
    def __init__(self, app: "App", r: int, name: str) -> None:
        self.app, self.name = app, name
        f = app.rows_frame
        ttk.Label(f, text=LABELS.get(name, name), width=20).grid(row=r, column=0, sticky="w", pady=5)
        self.var = tk.StringVar()
        self.entry = ttk.Entry(f, textvariable=self.var, show="•", width=40)
        self.entry.grid(row=r, column=1, padx=6)
        self.entry.bind("<Return>", lambda _e: self.save())
        buttons = [("Show", self.toggle), ("Paste", self.paste), ("Save", self.save),
                   ("Test", self.test), ("Delete", self.delete)]
        for c, (label, cmd) in enumerate(buttons, start=2):
            ttk.Button(f, text=label, width=7, command=cmd).grid(row=r, column=c, padx=(4, 0))
        self.status = ttk.Label(f, width=28, foreground="#555")
        self.status.grid(row=r, column=7, sticky="w", padx=(10, 0))
        self.refresh()

    def refresh(self, note: str = "") -> None:
        stored = keys.get(self.name)
        text = f"stored {keys.masked(stored)}" if stored else "not stored"
        self.status.config(text=f"{text}  {note}".strip())

    def toggle(self) -> None:
        self.entry.config(show="" if self.entry.cget("show") else "•")

    def paste(self) -> None:
        try:
            self.var.set(self.entry.clipboard_get().strip())
        except tk.TclError:
            self.refresh("clipboard empty")

    def save(self) -> None:
        value = self.var.get().strip()
        if not value:
            self.refresh("nothing to save")
            return
        try:
            keys.set_(self.name, value)
        except ValueError as err:
            self.refresh(f"✗ {err}")
            return
        self.var.set("")
        self.entry.clipboard_clear()  # don't leave the key sitting in the clipboard
        self.refresh("✓ saved")

    def test(self) -> None:
        typed = self.var.get().strip()
        value = typed or keys.get(self.name)
        if not value:
            self.refresh("nothing to test")
            return
        self.refresh("testing…")

        def done(result: str) -> None:
            if typed and result.startswith("✓"):
                self.save()  # a key that just passed its test is the one you want stored
                self.refresh("✓ works, saved")
            elif typed:
                self.refresh(f"{result} (not saved)")
            else:
                self.refresh(result)

        def work() -> None:
            result = _test(self.name, value)
            self.status.after(0, lambda: done(result))

        threading.Thread(target=work, daemon=True).start()

    def delete(self) -> None:
        keys.delete(self.name)
        if self.name in keys.KNOWN_KEYS:
            self.refresh("deleted")
        else:
            self.app.rebuild()  # custom keys disappear from the list once deleted


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        outer = ttk.Frame(root, padding=14)
        outer.grid()
        ttk.Label(outer, text="Paste a key and press Save. Keys are kept in Windows Credential Manager "
                              "and never written to files.").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.rows_frame = ttk.Frame(outer)
        self.rows_frame.grid(row=1, column=0, sticky="w")

        add = ttk.LabelFrame(outer, text="Add a key for another service", padding=8)
        add.grid(row=2, column=0, sticky="we", pady=(12, 0))
        ttk.Label(add, text="Name").grid(row=0, column=0, sticky="w")
        self.new_name = tk.StringVar()
        name_entry = ttk.Entry(add, textvariable=self.new_name, width=26)
        name_entry.grid(row=0, column=1, padx=6)
        ttk.Label(add, text="Key").grid(row=0, column=2, sticky="w")
        self.new_value = tk.StringVar()
        value_entry = ttk.Entry(add, textvariable=self.new_value, show="•", width=34)
        value_entry.grid(row=0, column=3, padx=6)
        value_entry.bind("<Return>", lambda _e: self.add())
        ttk.Button(add, text="Paste", width=7,
                   command=lambda: self.new_value.set(self._clipboard())).grid(row=0, column=4)
        ttk.Button(add, text="Add", width=7, command=self.add).grid(row=0, column=5, padx=(4, 0))
        self.add_status = ttk.Label(add, foreground="#555")
        self.add_status.grid(row=1, column=0, columnspan=6, sticky="w", pady=(6, 0))
        self.add_status.config(text="Use the env-var name the service's docs give, e.g. MY_SERVICE_API_KEY.")
        self.rebuild()

    def _clipboard(self) -> str:
        try:
            return self.root.clipboard_get().strip()
        except tk.TclError:
            return ""

    def rebuild(self) -> None:
        for child in self.rows_frame.winfo_children():
            child.destroy()
        for i, name in enumerate(keys.names()):
            Row(self, i, name)

    def add(self) -> None:
        name = self.new_name.get().strip().upper().replace("-", "_").replace(" ", "_")
        try:
            keys.set_(name, self.new_value.get())
        except ValueError as err:
            self.add_status.config(text=f"✗ {err}")
            return
        self.new_name.set("")
        self.new_value.set("")
        self.root.clipboard_clear()
        self.add_status.config(text=f"✓ saved {name}")
        self.rebuild()


def main() -> None:
    root = tk.Tk()
    root.title("jeverifier — API keys")
    root.resizable(False, False)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
