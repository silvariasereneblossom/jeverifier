"""Explicit policy: turns raw Jev judgments into a decision. All thresholds live here.

The numbers are conservative starting points, not tuned values. Tune them against traces from
your own runs (runs/*.jsonl), and pin the Jev version you tuned on (see config.JEV_MODEL).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .gate import Assessment
from .model import Action, Element, Observation

Decision = Literal["act", "confirm", "reject", "halt"]

RISK_ORDER = ["observe", "edit_local", "commit"]
# Minimum target confidence to act without asking, by risk level.
ACT_CONFIDENCE = {"observe": 0.5, "edit_local": 0.6, "commit": 0.8}
PLANNER_MATCH_MIN = 0.6
COMMIT_PROB_FLOOR = 0.2  # a 20% chance of an irreversible effect is treated as irreversible
BLOCKER_MIN = 0.5
VERIFY_OK = 0.6


@dataclass
class Verdict:
    decision: Decision
    risk: str
    reasons: list[str]

    def as_text(self) -> str:
        return f"{self.decision.upper()} (risk={self.risk}): " + "; ".join(self.reasons)


def effective_risk(a: Assessment) -> str:
    risk = a.risk
    if a.risk_probs.get("commit", 0.0) >= COMMIT_PROB_FLOOR:
        risk = "commit"
    if a.risk_floor and RISK_ORDER.index(a.risk_floor) > RISK_ORDER.index(risk):
        risk = a.risk_floor
    return risk


def decide(a: Assessment, obs: Observation, action: Action, pick: Element, text: str | None) -> Verdict:
    risk = effective_risk(a)

    # Hard rules first: things this tool never does on its own.
    if pick.is_secret_field and action in ("fill", "press"):
        return Verdict("halt", risk, ["this is a password field; the user must enter credentials themselves"])
    if a.blocker_probs.get("bot_check", 0) >= BLOCKER_MIN:
        return Verdict("halt", risk, ["a CAPTCHA / bot check is on screen; the user must handle it"])
    if a.blocker_probs.get("sign_in", 0) >= BLOCKER_MIN and a.blocker == "sign_in":
        return Verdict("halt", risk, ["the page requires signing in; the user must sign in themselves"])
    if "disabled" in pick.attrs and action in ("click", "fill", "select", "check"):
        return Verdict("reject", risk, [f"[{pick.id}] is disabled"])

    reasons: list[str] = []
    if a.blocker in ("dialog", "error", "loading") and a.blocker_probs[a.blocker] >= BLOCKER_MIN:
        reasons.append(f"screen check: {a.blocker} ({a.blocker_probs[a.blocker]:.2f})")

    if a.target == "none":
        return Verdict("reject", risk, reasons + [
            f"Jev found no element that fits the intent (p_none={a.target_probs.get('none', 0):.2f})",
            "top candidates: " + " | ".join(a.top_targets(obs))])
    if a.target != pick.id:
        return Verdict("reject", risk, reasons + [
            f"Jev disagrees with [{pick.id}]: it picked [{a.target}] (conf={a.target_conf:.2f})",
            "top candidates: " + " | ".join(a.top_targets(obs))])
    if (a.planner_match or 0) < PLANNER_MATCH_MIN:
        return Verdict("reject", risk, reasons + [
            f"Jev doubts [{pick.id}] accomplishes the intent (p={a.planner_match:.2f})"])
    if a.target_conf < ACT_CONFIDENCE[risk]:
        return Verdict("reject", risk, reasons + [
            f"target is ambiguous for a {risk} action (conf={a.target_conf:.2f} < {ACT_CONFIDENCE[risk]})",
            "top candidates: " + " | ".join(a.top_targets(obs))])

    reasons.append(f"Jev agrees on [{pick.id}] (conf={a.target_conf:.2f}, match={a.planner_match:.2f})")
    if risk == "commit":
        return Verdict("confirm", risk, reasons + ["irreversible effect: needs the user's OK"])
    return Verdict("act", risk, reasons)
