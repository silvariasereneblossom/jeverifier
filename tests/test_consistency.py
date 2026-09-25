"""Consistency pipeline, offline: a fake Jev (mock transport) drives the real SDK and the real pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import httpx2
import pytest
from typesafe_sdk import AsyncTypeSafeClient

from jevauto import consistency as cs
from jevauto import ctx, wiki


def make_repo(tmp_path):
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "ENGINEERING.md").write_text(
        "# Engineering\n\n## Limits\n\nA file holds at most 800 lines under `max_lines_per_file`.\n\n"
        "## Style\n\nEvery comment must explain why, never what.\n", encoding="utf-8")
    (tmp_path / "ARCH.md").write_text(
        "# Architecture\n\n## Tooling\n\nThe checker caps each file at 500 lines through `max_lines_per_file`.\n\n"
        "## History\n\nBefore Hardening-1 the cap was 900 lines and nobody checked it.\n", encoding="utf-8")
    return tmp_path


def fake_client(kind_of=lambda text: "current", contra_of=None):
    """Tags every claim with the first two topic options, labels sections with `kind_of`, and calls a
    pair contradictory when both statements mention max_lines_per_file (or per `contra_of`)."""
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        answers = {}
        for qid, q in body["questions"].items():
            ins = q["instructions"]
            if q["type"] == "choice" and "claim" in ins:
                opts = list(q["criteria"])
                probs = {o: 0.0 for o in opts} | {opts[0]: 0.6, opts[1]: 0.4}
                answers[qid] = {"type": "choice", "choice": opts[0], "probabilities": probs, "confidence": 0.5}
            elif q["type"] == "choice":
                k = kind_of(ins["section"]["text"])
                answers[qid] = {"type": "choice", "choice": k, "probabilities": {o: float(o == k) for o in q["criteria"]},
                                "confidence": 1.0}
            else:
                both = ins["first"] + ins["second"]
                hit = contra_of(ins) if contra_of else both.count("max_lines_per_file") == 2
                answers[qid] = {"type": "noul", "noul": 0.9 if hit else 0.1}
        return httpx2.Response(200, json={"model": "fake", "answers": answers, "usage": {"input_tokens": 10, "output_tokens": 1}})

    return (lambda: AsyncTypeSafeClient(api_key="sk-test", transport=httpx2.MockTransport(handler))), calls


@pytest.fixture(autouse=True)
def isolated_out(tmp_path, monkeypatch):
    monkeypatch.setattr(cs.core, "OUT", tmp_path / "out")
    monkeypatch.setattr(cs.core, "_model", lambda: "fake-jev")  # never look up the real provider in tests


def test_pipeline_ranks_the_contradiction_first(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "repo")
    client, _ = fake_client()
    monkeypatch.setattr(cs.core, "_client", client)
    res = cs.run(repo, wiki._wiki_and_docs(repo))
    score, contra, same, i, j = res.ranked[0]
    texts = {res.claims[i].text, res.claims[j].text}
    assert any("800" in t for t in texts) and any("500" in t for t in texts)
    assert contra == pytest.approx(0.9) and res.stats["pairs_judged"] >= 1
    assert same == pytest.approx(0.9)


def test_history_sections_are_filtered_and_owner_override_wins(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "repo")
    client, _ = fake_client(kind_of=lambda text: "history" if "Before Hardening" in text else "current")
    monkeypatch.setattr(cs.core, "_client", client)
    res = cs.run(repo, wiki._wiki_and_docs(repo))
    assert all("900" not in res.claims[i].text + res.claims[j].text for *_, i, j in res.ranked)
    checks = repo / "docs" / "wiki" / "checks"
    checks.mkdir(parents=True)
    (checks / "kinds.json").write_text(json.dumps({"ENGINEERING.md#Engineering > Limits": "history"}), encoding="utf-8")
    res = cs.run(repo, wiki._wiki_and_docs(repo))
    assert all("800" not in res.claims[i].text + res.claims[j].text for *_, i, j in res.ranked)


def test_false_alarm_verdict_suppresses_pair_until_text_changes(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "repo")
    client, _ = fake_client()
    monkeypatch.setattr(cs.core, "_client", client)
    res = cs.run(repo, wiki._wiki_and_docs(repo))
    _, _, _, i, j = res.ranked[0]
    pid = cs.fingerprint(res.claims[i], res.claims[j])
    cs.record_verdict(repo, pid, "false-alarm", "different files")
    res2 = cs.run(repo, wiki._wiki_and_docs(repo))
    assert pid not in {cs.fingerprint(res2.claims[a], res2.claims[b]) for *_, a, b in res2.ranked}
    assert res2.stats["suppressed"] == 1
    eng = repo / "ENGINEERING.md"
    eng.write_text(eng.read_text(encoding="utf-8").replace("800", "850"), encoding="utf-8")
    res3 = cs.run(repo, wiki._wiki_and_docs(repo))
    assert res3.stats["suppressed"] == 0 and res3.ranked[0][1] == pytest.approx(0.9)


def test_caches_mean_a_rerun_only_pays_for_changes(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "repo")
    client, calls = fake_client()
    monkeypatch.setattr(cs.core, "_client", client)
    cs.run(repo, wiki._wiki_and_docs(repo))
    first = len(calls)
    cs.run(repo, wiki._wiki_and_docs(repo))
    assert len(calls) == first  # kinds, tags and judgments all came from the cache: an unchanged rerun is free


def test_fingerprint_ignores_line_moves_and_whitespace_but_not_text():
    s = wiki.ctx.Section("A.md", 1, 5, "A", 10, "")
    a, b = cs.Claim(s, 3, "A file holds 500 lines."), cs.Claim(s, 9, "Files hold  500 lines.")
    moved = cs.Claim(s, 40, "A file holds 500 lines.")
    assert cs.fingerprint(a, b) == cs.fingerprint(b, moved)
    assert cs.fingerprint(a, b) != cs.fingerprint(cs.Claim(s, 3, "A file holds 800 lines."), b)


def test_merge_topics_folds_headings_that_extend_a_shorter_one():
    canon = cs.merge_topics(["Determinism", "Determinism is inherited, and asserted", "Mods", "Static checks"])
    assert canon["Determinism is inherited, and asserted"] == "Determinism" and canon["Mods"] == "Mods"


def test_plants_are_same_quantity_pairs_and_skip_refs_and_parts_of_numbers(tmp_path):
    repo = make_repo(tmp_path / "repo")
    (repo / "README.md").write_text(
        "# Readme\n\nThe checker caps each file at 500 lines, see §11 and 4,979 checks and 40% of 11 things.\n",
        encoding="utf-8")
    claims = cs.claims_of(repo, wiki._wiki_and_docs(repo))
    plants = cs.choose_plants(claims)
    assert plants and all(q == ("500", "lines") for _, q, _ in plants)  # never §11, 4,979 or 40%
    assert all(claims[a].section.id != claims[b].section.id for a, _, b in plants)
    assert cs._plant("A file holds 500 lines, not 4,500.", "500", "lines") == "A file holds 800 lines, not 4,500."
    assert cs._plant("See §500 lines.", "500", "lines") is None
    assert cs._bump("500") == "800" and cs._bump("three") == "six" and cs._bump("Twelve") == "Four"


def test_quantities_normalise_words_and_skip_refs_parts_and_generic_nouns():
    q = cs.quantities("Three baselines, 12 cells and 3 things; see §11 rules, 4,979 checks and 40% of units.")
    assert (3, "baselin", "Three baselines") in q and (12, "cell", "12 cells") in q
    assert all(stem not in ("thing", "rule", "check") for _, stem, _ in q)  # generic noun, §11 and 4,979 are skipped


def test_number_check_pairs_same_noun_different_value_and_ranks_it(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "repo")
    client, _ = fake_client()
    monkeypatch.setattr(cs.core, "_client", client)
    res = cs.run(repo, wiki._wiki_and_docs(repo))
    p, i, j, si, sj = res.numeric[0]
    assert {si, sj} == {"800 lines", "500 lines"} and p == pytest.approx(0.9)
    text, items = cs.report(repo, res)
    assert "## Number mismatches" in text and items[0]["list"] == "numbers"


def test_rule_plants_flip_one_rule_word_between_matching_statements(tmp_path):
    repo = make_repo(tmp_path / "repo")
    (repo / "README.md").write_text("# Readme\n\nEvery comment must explain why a guard exists, never what.\n",
                                    encoding="utf-8")
    claims = cs.claims_of(repo, wiki._wiki_and_docs(repo))
    plants = cs.choose_rule_plants(claims, set(range(len(claims))))
    assert plants and all(claims[a].section.id != claims[b].section.id for a, _, b in plants)
    assert cs._plant_rule("You MUST pin it; must is must.", "MUST") == "You MAY pin it; must is must."
    assert cs._plant_rule("Never do it.", "Never") == "Always do it."


def test_delta_mode_lists_only_pairs_touching_changed_statements(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "repo")
    client, _ = fake_client()
    monkeypatch.setattr(cs.core, "_client", client)
    _, stats = cs.check(repo)
    assert stats["mode"] == "full"  # no baseline yet: the first run is the full ranking
    cs.accept(repo)
    _, stats = cs.check(repo)
    assert stats["mode"] == "delta" and stats["new_claims"] == 0 and stats["listed"] == 0
    arch = repo / "ARCH.md"
    arch.write_text(arch.read_text(encoding="utf-8").replace("500 lines", "600 lines"), encoding="utf-8")
    dest, stats = cs.check(repo)
    pairs = json.loads(dest.with_suffix(".json").read_text(encoding="utf-8"))["pairs"]
    assert stats["new_claims"] == 1 and pairs
    assert all("600 lines" in p["a"]["text"] + p["b"]["text"] for p in pairs)  # every pair touches the edit
    assert all(p.get("contra", 1) >= cs.DELTA_MIN_CONTRA for p in pairs)  # the floor holds
    _, stats = cs.check(repo, deep=True)
    assert stats["mode"] == "full"


def test_accept_at_a_git_ref_uses_the_committed_text(tmp_path, monkeypatch):
    import subprocess

    repo = make_repo(tmp_path / "repo")
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "docs"], check=True)
    arch = repo / "ARCH.md"
    arch.write_text(arch.read_text(encoding="utf-8").replace("500 lines", "600 lines"), encoding="utf-8")
    client, _ = fake_client()
    monkeypatch.setattr(cs.core, "_client", client)
    cs.accept(repo, git_ref="HEAD")  # the review covered the committed text, not the edit
    _, stats = cs.check(repo)
    assert stats["mode"] == "delta" and stats["new_claims"] == 1 and stats["listed"] >= 1


def test_verdict_rejects_unknown_labels(tmp_path):
    with pytest.raises(ValueError):
        cs.record_verdict(tmp_path, "abc", "maybe")


def test_cost_limit_stops_before_sending(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "repo")
    client, calls = fake_client()
    monkeypatch.setattr(cs.core, "_client", client)
    with pytest.raises(cs.CostLimit):
        cs.run(repo, wiki._wiki_and_docs(repo), max_cost=0.0000001)
    assert calls == []  # the estimate refused the first stage; no request went out


def test_a_run_cut_off_by_an_api_error_keeps_what_it_paid_for(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "repo")
    good, _ = fake_client()
    monkeypatch.setattr(cs.core, "_client", good)
    cs.run(repo, wiki._wiki_and_docs(repo))
    judged = cs.Store(repo).load("judged")
    assert judged  # sanity: a full run caches its judgments
    (cs.Store(repo).cache_dir / "judged.json").unlink()

    def broke(request):  # kinds and tags are cached; the first judging request fails like a 402
        return httpx2.Response(402, json={"detail": "no credits"})
    monkeypatch.setattr(cs.core, "_client", lambda: AsyncTypeSafeClient(api_key="sk-test", transport=httpx2.MockTransport(broke)))
    with pytest.raises(Exception):
        cs.run(repo, wiki._wiki_and_docs(repo))
    assert (cs.Store(repo).cache_dir / "judged.json").exists()  # saved on the way out
    assert cs.Store(repo).load("tags") and cs.Store(repo).load("kinds")


def test_folder_prefix_override_and_exact_entry_precedence():
    s = wiki.ctx.Section("docs/contracts/CONVENTIONS_M2C.md", 1, 9, "Conventions > Pace", 10, "")
    other = wiki.ctx.Section("ARCHITECTURE.md", 1, 9, "Architecture", 10, "")
    rules = {"docs/contracts/": "history", "docs/contracts/CONVENTIONS_M2C.md#Conventions > Pace": "current"}
    assert cs.override_kind({"docs/contracts/": "history"}, s) == "history"
    assert cs.override_kind(rules, s) == "current"  # an exact entry beats a folder rule
    assert cs.override_kind(rules, other) is None


def test_caches_are_kept_apart_per_model(tmp_path):
    repo = make_repo(tmp_path / "repo")
    a, b = cs.Store(repo, model="jev-1.13.0"), cs.Store(repo, model="openjev")
    a.save("judged", {"c:x": 0.9})
    assert b.load("judged") == {} and a.cache_dir != b.cache_dir


def test_output_dir_is_the_project_out_folder():
    assert ctx.OUT == Path(__file__).resolve().parent.parent / "out"  # the suite redirects core.OUT
