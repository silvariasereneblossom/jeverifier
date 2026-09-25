"""One gated step: observe → Jev assess → policy → (confirm) → act → Jev verify.

Shared by the API planner (planner.py) and the MCP server (mcp_server.py), so both drivers
go through exactly the same fidelity checks.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .gate import JevGate, TypeSafeError
from .model import Surface
from .policy import VERIFY_OK, decide


@dataclass
class Session:
    surface: Surface
    gate: JevGate
    log: Callable[[str], None] = print
    trace_dir: Path = Path("runs")
    trace_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.trace_dir.mkdir(exist_ok=True)
        self.trace_path = self.trace_dir / time.strftime("%Y%m%d-%H%M%S.jsonl")

    def observe(self) -> str:
        return self.surface.observe().render()

    def navigate(self, target: str) -> str:
        self.surface.navigate(target)
        return self.observe()

    def act(self, action: str, element_id: str, intent: str, expect: str, text: str | None = None, *,
            confirm: Callable[[str], bool] | None = None, confirmed: bool = False,
            on_halt: Callable[[str], str] | None = None) -> str:
        """Run one gated action and describe the outcome for the planner.

        confirm:   asked for irreversible actions; if absent, `confirmed` must already be True.
        on_halt:   asked to hand a step to the user; if absent, the halt is reported back.
        """
        try:
            return self._act(action, element_id, intent, expect, text, confirm, confirmed, on_halt)
        finally:
            for rec in self.gate.trace:
                self._trace(rec)
            self.gate.trace.clear()

    def _act(self, action, element_id, intent, expect, text, confirm, confirmed, on_halt) -> str:
        before = self.surface.observe()
        pick = before.by_id(element_id)
        if pick is None:
            return f"Element {element_id} is not on the current screen (ids may be stale).\n\n{before.render()}"
        try:
            assessment = self.gate.assess(before, action, intent, pick, text)
        except TypeSafeError as err:
            return f"Fidelity layer unavailable ({type(err).__name__}); nothing was done."
        verdict = decide(assessment, before, action, pick, text)
        self._trace({"kind": "verdict", "action": action, "element": pick.describe(), "intent": intent,
                     "verdict": verdict.decision, "risk": verdict.risk, "reasons": verdict.reasons,
                     "confirmed": confirmed})
        self.log(f"  jev {assessment.latency_ms}ms → {verdict.as_text()}")

        if verdict.decision == "halt":
            if on_halt is None:
                return (f"HALTED, nothing was done: {verdict.as_text()}. The user must do this step "
                        "themselves; tell them, wait until they say it's done, then observe again.")
            reply = on_halt(f"{verdict.reasons[0]}. Handle it in the window, then reply here (or type 'stop').")
            return f"HALTED: {verdict.as_text()}\nUser replied: {reply}\n\n{self.observe()}"
        if verdict.decision == "reject":
            return f"REJECTED, nothing was done. {verdict.as_text()}"
        if verdict.decision == "confirm" and not confirmed:
            shown = f' with "{text}"' if text and not pick.is_secret_field else ""
            summary = f"{action} {pick.describe()}{shown} (intent: {intent})"
            if confirm is None:
                return (f"NEEDS CONFIRMATION, nothing was done: {verdict.as_text()}\n  {summary}\n"
                        "Ask the user in plain words; only if they approve, call act again with confirmed=true.")
            if not confirm(summary):
                return "The user declined this action; nothing was done. Ask them how to proceed."

        try:
            self.surface.perform(action, pick, text)  # type: ignore[arg-type]
        except Exception as err:
            return f"Action failed: {type(err).__name__}: {err}\n\n{self.observe()}"
        after = self.surface.observe()
        try:
            v = self.gate.verify(before, after, expect)
            check = (f"VERIFIED (p={v.satisfied:.2f})" if v.satisfied >= VERIFY_OK
                     else f"NOT VERIFIED (p={v.satisfied:.2f}, screen changed: {v.changed}). "
                          "Check the screen before continuing.")
        except TypeSafeError as err:
            check = f"verification unavailable ({type(err).__name__})"
        self.log(f"  done: {check}")
        return f"DONE {action} on [{pick.id}]. {check}\n\n{after.render()}"

    def _trace(self, record: dict) -> None:
        with self.trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
