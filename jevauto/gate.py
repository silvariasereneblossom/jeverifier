"""The Jev fidelity layer.

Claude proposes a step (action + intent + the element id it believes is right). Before
anything touches the screen, Jev independently judges, in parallel:

  target        Choice over the on-screen elements (+ "none"): which element fits the intent?
  planner_match Noul: does the element Claude picked accomplish the intent?
  risk          Choice: what kind of consequence does this action have?
  blocker       Choice over the screen: is a bot check, sign-in wall, dialog or error in the way?

Code (policy.py) turns those judgments into act / confirm / reject / halt. After acting,
a Noul checks Claude's stated expectation against the new screen.
"""

from __future__ import annotations

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from typesafe_sdk import Choice, Noul, TypeSafeClient, TypeSafeError

from .model import Action, Element, Observation

MAX_OPTIONS = 200  # Jev allows 255 options per Choice; leave headroom for the extra outcomes

RISK_CRITERIA = {
    "observe": "Only reads, navigates, opens, expands, scrolls, searches, filters, sorts, "
               "switches a view, or answers a cookie banner (accepting or rejecting cookies). "
               "Nothing is saved, sent, or changed outside this screen.",
    "edit_local": "Types into or changes a field, selection, checkbox or draft that is not yet "
                  "submitted or saved and can simply be changed back.",
    "commit": "Submits, saves, sends, posts, publishes, purchases, pays, books, deletes, uploads, "
              "accepts terms of service or a legal agreement, grants app or device permissions, or "
              "changes account or security settings: an effect beyond this screen that may not be "
              "undoable. Cookie banners are not in this category.",
}

BLOCKER_CRITERIA = {
    "none": "Nothing blocks the page; its main content is usable.",
    "bot_check": "A CAPTCHA, 'verify you are human', or other bot-detection challenge is shown.",
    "sign_in": "The page requires signing in, a password, or a verification code to continue.",
    "dialog": "A cookie or consent banner, popup, or modal dialog covers the page and must be "
              "dismissed first.",
    "error": "An error is shown instead of the expected content, such as page not found, access "
             "denied, or a failed request.",
    "loading": "The main content is still loading or the page is blank.",
}

# Code-side floor on risk: names that almost always mean an irreversible effect.
_COMMIT_WORDS = re.compile(
    r"\b(submit|send|post|publish|buy|purchase|pay|checkout|place order|order now|book|confirm|"
    r"delete|remove|erase|unsubscribe|transfer|withdraw|sign up|register|accept|agree|allow|"
    r"authori[sz]e|upload|save|apply|reply|tweet|share)\b",
    re.I,
)
_COOKIE = re.compile(r"\bcookies?\b", re.I)


@dataclass
class Assessment:
    """Raw Jev judgments for one proposed step, kept separate from the policy decision."""

    target: str
    target_probs: dict[str, float]
    target_conf: float
    planner_match: float | None
    risk: str
    risk_probs: dict[str, float]
    risk_floor: str | None  # set when code heuristics force a higher risk
    blocker: str
    blocker_probs: dict[str, float]
    latency_ms: int
    model: str = ""

    def top_targets(self, obs: Observation, k: int = 3) -> list[str]:
        ranked = sorted(self.target_probs.items(), key=lambda kv: kv[1], reverse=True)[:k]
        out = []
        for eid, p in ranked:
            el = obs.by_id(eid)
            out.append(f"[{eid}] {el.describe() if el else 'none of the elements'} (p={p:.2f})")
        return out


@dataclass
class Verification:
    satisfied: float
    changed: bool
    latency_ms: int


@dataclass
class JevGate:
    client: TypeSafeClient
    trace: list[dict[str, Any]] = field(default_factory=list)
    _blocker_cache: dict[str, tuple[str, dict[str, float]]] = field(default_factory=dict)

    # ---------- before acting ----------

    def assess(self, obs: Observation, action: Action, intent: str, planner_pick: Element,
               text: str | None) -> Assessment:
        started = time.perf_counter()
        candidates = shortlist(obs.elements, intent, keep=planner_pick.id)
        step = {"action": action, "intent": intent}
        if text is not None and action in ("fill", "select", "press"):
            step["text"] = "••••" if planner_pick.is_secret_field else text[:200]
        state = {
            "screen": {"title": obs.title, "location": obs.location},
            "step": step,
            "planner_pick": planner_pick.describe(),
        }
        criteria = {e.id: e.describe() for e in candidates}
        criteria["none"] = "None of these elements is the right place to perform `step.action` " \
                           "for `step.intent`."
        step_questions = {
            "target": Choice(
                instructions="Which on-screen element should `step.action` be performed on to "
                             "accomplish `step.intent`?",
                criteria=criteria,
            ),
            "planner_match": Noul(
                instructions="Is performing `step.action` on the element `planner_pick` the right "
                             "way to accomplish `step.intent`?",
            ),
            "risk": Choice(
                instructions="If `step.action` is performed on `planner_pick` (with `step.text`, if "
                             "any), what kind of effect does that have?",
                criteria=RISK_CRITERIA,
            ),
        }
        # The blocker question gets its own, text-heavy state so the page text doesn't
        # distract the element choice. Both requests run concurrently.
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_step = pool.submit(self.client.system_one, state, step_questions)
            f_block = pool.submit(self._blocker, obs)
            res = f_step.result()
            blocker, blocker_probs = f_block.result()

        target = res.choices["target"]
        risk = res.choices["risk"]
        cookie_banner = bool(_COOKIE.search(f"{planner_pick.context} {planner_pick.name}"))
        floor = "commit" if (_COMMIT_WORDS.search(planner_pick.name) or
                             planner_pick.attrs.get("type") == "submit") \
            and action in ("click", "press") and not cookie_banner else None
        a = Assessment(
            target=target.choice, target_probs=dict(target.probabilities), target_conf=target.confidence,
            planner_match=res.nouls["planner_match"].noul,
            risk=risk.choice, risk_probs=dict(risk.probabilities), risk_floor=floor,
            blocker=blocker, blocker_probs=blocker_probs,
            latency_ms=int((time.perf_counter() - started) * 1000), model=res.model,
        )
        self.trace.append({"kind": "assess", "state": state, "candidates": len(candidates),
                           "answers": {"target": a.target, "target_conf": a.target_conf,
                                       "planner_match": a.planner_match, "risk": a.risk_probs,
                                       "risk_floor": floor, "blocker": blocker_probs},
                           "latency_ms": a.latency_ms, "model": a.model})
        return a

    def _blocker(self, obs: Observation) -> tuple[str, dict[str, float]]:
        key = hashlib.sha1(f"{obs.title}\n{obs.location}\n{obs.text[:3000]}".encode()).hexdigest()
        if key not in self._blocker_cache:
            res = self.client.system_one(
                {"title": obs.title, "location": obs.location, "visible_text": obs.text[:3000]},
                {"blocker": Choice(
                    instructions="What, if anything, currently blocks normal use of this page?",
                    criteria=BLOCKER_CRITERIA,
                )},
            )
            b = res.choices["blocker"]
            self._blocker_cache[key] = (b.choice, dict(b.probabilities))
        return self._blocker_cache[key]

    # ---------- after acting ----------

    def verify(self, before: Observation, after: Observation, expected: str) -> Verification:
        started = time.perf_counter()
        changed = (before.title, before.location, before.text) != (after.title, after.location, after.text) \
            or [e.describe() for e in before.elements] != [e.describe() for e in after.elements]
        res = self.client.system_one(
            {"expected": expected,
             "after": {"title": after.title, "location": after.location,
                       "elements": [e.describe() for e in after.elements[:80]],
                       "visible_text": after.text[:2500]}},
            {"satisfied": Noul(
                instructions="Does the `after` screen show that `expected` is now true?",
                criteria={"true": "The screen clearly reflects `expected`.",
                          "false": "The screen does not reflect `expected`, or shows an error."},
            )},
        )
        v = Verification(satisfied=res.nouls["satisfied"].noul, changed=changed,
                         latency_ms=int((time.perf_counter() - started) * 1000))
        self.trace.append({"kind": "verify", "expected": expected, "satisfied": v.satisfied,
                           "changed": changed, "latency_ms": v.latency_ms})
        return v


def shortlist(elements: list[Element], intent: str, keep: str | None, limit: int = MAX_OPTIONS) -> list[Element]:
    """Keep Choice options under the API limit: rank by word overlap with the intent,
    always keeping the planner's pick, then restore on-screen order."""
    if len(elements) <= limit:
        return elements
    words = set(re.findall(r"\w+", intent.lower()))

    def score(e: Element) -> float:
        desc = set(re.findall(r"\w+", e.describe().lower()))
        return len(words & desc) + (0.5 if e.in_view else 0)

    ranked = sorted(elements, key=score, reverse=True)[:limit]
    if keep and all(e.id != keep for e in ranked):
        ranked[-1] = next(e for e in elements if e.id == keep)
    order = {e.id: i for i, e in enumerate(elements)}
    return sorted(ranked, key=lambda e: order[e.id])


__all__ = ["JevGate", "Assessment", "Verification", "shortlist", "TypeSafeError"]
