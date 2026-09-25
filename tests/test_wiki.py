"""Wiki scaffolding, anchors, pairing and coverage — offline, on a temp repo."""

from __future__ import annotations

from jevauto import wiki


def make_repo(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "ARCH.md").write_text(
        "# Arch\nThe `BattleState` owns squads.\n\n## 1. Layers — the rule\n`BattleState` and `SquadState` live in rules.\n"
        + "\n" * 200 + "## Limits\nA file holds at most `max_lines_per_file` of 500 lines.\n", encoding="utf-8")
    (tmp_path / "docs" / "HANDOVER.md").write_text(
        "# Handover\nNext: split `SquadState` from `BattleState`; `max_lines_per_file` stays 800.\n", encoding="utf-8")
    return tmp_path


def test_slug_matches_github_anchors():
    assert wiki.slug("1. Layers — the rule") == "1-layers--the-rule"
    assert wiki.slug("4.5 Rules read TAGS, never `ids`") == "45-rules-read-tags-never-ids"


def test_init_scaffolds_links_and_claude_pointer(tmp_path):
    repo = make_repo(tmp_path)
    written = wiki.init(repo, "Demo", "A demo project.")
    names = {p.relative_to(repo).as_posix() for p in written}
    assert {"docs/wiki/home.md", "docs/wiki/map.md", "docs/wiki/protocols/2-spot-check.md", "CLAUDE.md"} <= names
    assert "docs/wiki/" in (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Co-Authored-By" in (repo / "CLAUDE.md").read_text(encoding="utf-8")  # the no-attribution rule
    orphans, broken = wiki.coverage(repo)
    assert orphans == [] and broken == []
    assert wiki.init(repo, "Demo", "again") == [repo / "docs/wiki/map.md"]  # idempotent: nothing overwritten


def test_coverage_reports_orphans_and_broken_links(tmp_path):
    repo = make_repo(tmp_path)
    wiki.init(repo, "Demo", "x")
    (repo / "docs/wiki/lonely.md").write_text("# Lonely\n", encoding="utf-8")
    (repo / "docs/wiki/overview.md").write_text("# O\n[gone](nowhere.md)\n[home](home.md)\n", encoding="utf-8")
    orphans, broken = wiki.coverage(repo)
    assert orphans == ["docs/wiki/lonely.md"]
    assert broken == [("docs/wiki/overview.md", "nowhere.md")]


def test_cli_parses_every_command(capsys):
    import pytest

    from jevauto import cli

    for argv in (["wiki", "--help"], ["ctx", "--help"], ["keys", "--help"], ["run", "--help"]):
        with pytest.raises(SystemExit) as e:
            cli.main(argv)
        assert e.value.code == 0
