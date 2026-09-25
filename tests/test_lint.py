"""Semantic lint, offline: a fake Jev flags any function that assigns `state.cell`."""

from __future__ import annotations

import json

import httpx2
from typesafe_sdk import AsyncTypeSafeClient

from jeverifier import lint
from jeverifier.consistency import core, record_verdict

RULE = {"id": "view_never_writes_model", "paths": ["scripts/presentation/"],
        "rule": "A view never writes the model.", "exceptions": ["Setup may spawn."], "true": "It writes.", "false": "It only reads."}


def make_repo(tmp_path):
    (tmp_path / "scripts/presentation").mkdir(parents=True)
    (tmp_path / "scripts/presentation/cursor.gd").write_text(
        "extends Node\n\n## Moves the cursor.\nfunc move(state, cell):\n\tstate.cell = cell\n\n"
        "func show(state):\n\tprint(state.cell)\n", encoding="utf-8")
    (tmp_path / "docs/wiki/checks").mkdir(parents=True)
    (tmp_path / "docs/wiki/checks/lint.json").write_text(json.dumps([RULE]), encoding="utf-8")
    return tmp_path


def test_lint_flags_caches_and_honours_false_alarms(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        hit = "state.cell =" in json.dumps(body)
        answers = {q: {"type": "noul", "noul": 0.9 if hit else 0.1} for q in body["questions"]}
        return httpx2.Response(200, json={"model": "fake", "answers": answers, "usage": {"input_tokens": 10, "output_tokens": 1}})

    monkeypatch.setattr(core, "OUT", tmp_path / "out")
    monkeypatch.setattr(core, "_model", lambda: "fake-jev")
    monkeypatch.setattr(core, "_client", lambda: AsyncTypeSafeClient(api_key="sk-test", transport=httpx2.MockTransport(handler)))
    repo = make_repo(tmp_path / "repo")

    units = lint.functions(repo, ["scripts/"])
    assert [(u["where"], u["name"]) for u in units] == [("scripts/presentation/cursor.gd:4", "move"),
                                                        ("scripts/presentation/cursor.gd:7", "show")]
    assert units[0]["code"].startswith("## Moves the cursor.") and "## Moves" not in units[1]["code"]

    report, stats = lint.lint(repo)
    assert stats["findings"] == 1 and stats["asked_jev"] == 2 and "move" in report.read_text(encoding="utf-8")
    assert "Allowed exception: Setup may spawn." in json.dumps(calls[0])

    _, stats = lint.lint(repo)  # unchanged code: answered from the cache
    assert stats["asked_jev"] == 0 and stats["findings"] == 1 and len(calls) == 2

    fid = f"lint:view_never_writes_model:{core._hash(units[0]['code'])[:10]}"
    record_verdict(repo, fid, "false-alarm")
    assert lint.lint(repo)[1]["findings"] == 0
