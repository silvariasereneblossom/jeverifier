"""Offline tests: the real TypeSafe SDK builds and parses requests against a mock transport,
so request shape and answer handling are exercised without an API key or network."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx2
import pytest
from typesafe_sdk import TypeSafeClient

from jevauto.gate import JevGate, shortlist
from jevauto.model import Element, Observation
from jevauto.policy import decide

HTML = (Path(__file__).parent / "fixture.html").as_uri()


def fake_jev(target: str, target_p: float, match: float, risk: dict, blocker: dict, satisfied: float = 0.9):
    """Mock TypeSafe endpoint. Answers `target` with `target_p` spread over the other options."""
    seen: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        seen.append(body)
        answers = {}
        for qid, q in body["questions"].items():
            if qid == "target":
                opts = list(q["criteria"])
                rest = (1 - target_p) / max(1, len(opts) - 1)
                probs = {o: (target_p if o == target else rest) for o in opts}
                answers[qid] = {"type": "choice", "choice": target, "probabilities": probs,
                                "confidence": (len(opts) * target_p - 1) / (len(opts) - 1)}
            elif qid in ("risk", "blocker"):
                probs = risk if qid == "risk" else blocker
                answers[qid] = {"type": "choice", "choice": max(probs, key=probs.get),
                                "probabilities": probs, "confidence": 0.9}
            elif qid == "planner_match":
                answers[qid] = {"type": "noul", "noul": match}
            elif qid == "satisfied":
                answers[qid] = {"type": "noul", "noul": satisfied}
        return httpx2.Response(200, json={"model": "jev-1.13.0", "answers": answers,
                                          "usage": {"input_tokens": 100, "output_tokens": 10}})

    client = TypeSafeClient(api_key="sk-test", model="jev-1.13.0", transport=httpx2.MockTransport(handler))
    return client, seen


def obs(*els: Element) -> Observation:
    return Observation(title="Shop", location="https://shop.test/cart", elements=list(els), text="Your cart")


SEARCH = Element(id="e1", role="searchbox", name="Search products")
BUY = Element(id="e2", role="button", name="Place order", context="form checkout")
LINK = Element(id="e3", role="link", name="Help", attrs={"href": "/help"})
PW = Element(id="e4", role="textbox", name="Password", attrs={"type": "password"})
SAFE = {"observe": 0.9, "edit_local": 0.08, "commit": 0.02}
CLEAR = {"none": 0.95, "bot_check": 0.01, "sign_in": 0.01, "dialog": 0.01, "error": 0.01, "loading": 0.01}


def test_agreement_on_safe_action_acts():
    client, seen = fake_jev("e3", 0.9, 0.95, SAFE, CLEAR)
    o = obs(SEARCH, BUY, LINK)
    a = JevGate(client).assess(o, "click", "open the help page", LINK, None)
    assert decide(a, o, "click", LINK, None).decision == "act"
    step = next(b for b in seen if "target" in b["questions"])
    assert set(step["questions"]["target"]["criteria"]) == {"e1", "e2", "e3", "none"}
    assert step["model"] == "jev-1.13.0"


def test_disagreement_rejects_with_candidates():
    client, _ = fake_jev("e1", 0.8, 0.3, SAFE, CLEAR)
    o = obs(SEARCH, BUY, LINK)
    a = JevGate(client).assess(o, "click", "search for shoes", LINK, None)
    v = decide(a, o, "click", LINK, None)
    assert v.decision == "reject" and "picked [e1]" in v.as_text()


def test_commit_word_forces_confirmation_even_if_jev_says_safe():
    client, _ = fake_jev("e2", 0.95, 0.95, SAFE, CLEAR)
    o = obs(SEARCH, BUY, LINK)
    a = JevGate(client).assess(o, "click", "place the order", BUY, None)
    v = decide(a, o, "click", BUY, None)
    assert v.risk == "commit" and v.decision == "confirm"


def test_small_commit_probability_is_treated_as_commit():
    client, _ = fake_jev("e3", 0.95, 0.95, {"observe": 0.7, "edit_local": 0.05, "commit": 0.25}, CLEAR)
    o = obs(SEARCH, BUY, LINK)
    a = JevGate(client).assess(o, "click", "open help", LINK, None)
    assert decide(a, o, "click", LINK, None).decision == "confirm"


def test_bot_check_halts():
    blocked = dict(CLEAR, none=0.1, bot_check=0.85)
    client, _ = fake_jev("e3", 0.95, 0.95, SAFE, blocked)
    o = obs(SEARCH, BUY, LINK)
    a = JevGate(client).assess(o, "click", "open help", LINK, None)
    assert decide(a, o, "click", LINK, None).decision == "halt"


def test_password_field_halts_and_is_masked_in_request():
    client, seen = fake_jev("e4", 0.95, 0.95, {"observe": 0.1, "edit_local": 0.85, "commit": 0.05}, CLEAR)
    o = obs(SEARCH, PW)
    a = JevGate(client).assess(o, "fill", "enter the password", PW, "hunter2")
    assert decide(a, o, "fill", PW, "hunter2").decision == "halt"
    assert "hunter2" not in json.dumps(seen)


def test_low_confidence_rejects():
    client, _ = fake_jev("e1", 0.4, 0.9, {"observe": 0.1, "edit_local": 0.85, "commit": 0.05}, CLEAR)
    o = obs(SEARCH, BUY, LINK)
    a = JevGate(client).assess(o, "fill", "type shoes in the search box", SEARCH, "shoes")
    assert decide(a, o, "fill", SEARCH, "shoes").decision == "reject"


def test_shortlist_respects_option_limit_and_keeps_pick():
    els = [Element(id=f"e{i}", role="link", name=f"Item {i}") for i in range(600)]
    pick = els[599]
    kept = shortlist(els, "open the checkout page", keep=pick.id)
    assert len(kept) == 200 and pick in kept


def test_verify_uses_expectation():
    client, seen = fake_jev("e3", 0.9, 0.9, SAFE, CLEAR, satisfied=0.2)
    o = obs(SEARCH, BUY, LINK)
    v = JevGate(client).verify(o, o, "the help page is shown")
    assert v.satisfied == 0.2 and v.changed is False
    assert seen[-1]["state"]["expected"] == "the help page is shown"


@pytest.mark.browser
def test_browser_observer_on_fixture():
    from jevauto.browser import BrowserSurface

    s = BrowserSurface(headless=True)
    try:
        s.navigate(HTML)
        first = s.observe()
        names = {e.name for e in first.elements}
        assert {"Search", "Sign in", "Place order", "Accept all", "Reject non-essential"} <= names
        assert "Hidden button" not in names
        pw = next(e for e in first.elements if e.name == "Password")
        assert pw.is_secret_field
        search = next(e for e in first.elements if e.role == "searchbox")
        s.perform("fill", search, "red shoes")
        second = s.observe()
        again = second.by_id(search.id)
        assert again is not None and again.value == "red shoes"  # ids survive re-observation
    finally:
        s.close()


def test_secrets_are_redacted_before_anyone_sees_them():
    e = Element(id="e9", role="textbox", name="Key", value="sk-ant-api03-abcdefghijklmnopqrstuvwx")
    o = Observation(title="token: ghp_abcdefghijklmnopqrstuvwxyz0123", location="x",
                    elements=[e], text="my github_pat_11ABCDEFG0qVZSmr here and 0123456789abcdef0123456789abcdef")
    blob = o.render()
    for leaked in ("sk-ant-api03", "ghp_abc", "github_pat_11", "0123456789abcdef0123"):
        assert leaked not in blob
    assert "Search products" == Element(id="e1", role="searchbox", name="Search products").name


@pytest.mark.desktop
@pytest.mark.skipif(sys.platform != "win32", reason="desktop mode is Windows-only")
def test_desktop_observer_on_private_window():
    import subprocess
    import time

    from jevauto.desktop import DesktopSurface

    title = f"jevauto-fixture-{int(time.time())}"
    p = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                          str(Path(__file__).parent / "desktop_fixture.ps1"), title])
    try:
        s = DesktopSurface(window=f"^{title}$")
        o = s.observe()
        box = next(e for e in o.elements if e.role == "textbox")
        btn = next(e for e in o.elements if e.name == "Search")
        s.perform("fill", box, "red shoes")
        s.perform("click", btn, None)
        assert "searched red shoes" in s.observe().text
    finally:
        p.kill()


def test_urls_and_paths_survive_redaction():
    url = "file:///C:/Users/someone/projects/jev-automation/tests/fixture.html"
    assert Observation(title="t", location=url, elements=[], text="").location == url


def test_cookie_banner_is_not_forced_to_commit():
    accept = Element(id="e1", role="button", name="Accept all", context="dialog Cookies")
    client, _ = fake_jev("e1", 0.95, 0.95, SAFE, CLEAR)
    o = obs(accept, LINK)
    a = JevGate(client).assess(o, "click", "accept the cookie banner", accept, None)
    assert a.risk_floor is None and decide(a, o, "click", accept, None).decision == "act"
