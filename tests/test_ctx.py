"""Context harness pieces that need no model: section splitting and transcript parsing."""

from __future__ import annotations

import json

from jeverifier import ctx


def test_sections_follow_headings_and_ignore_code_fences(tmp_path):
    doc = tmp_path / "A.md"
    doc.write_text("# Top\nIntro sentence here, long enough.\n\n## Sub\nBody.\n```\n# not a heading\n```\n## Other\nMore text.\n",
                   encoding="utf-8")
    secs = ctx.sections_of(doc, "A.md")
    assert [s.heading for s in secs] == ["Top", "Top > Sub", "Top > Other"]
    assert (secs[1].start, secs[1].end) == (4, 8)
    assert "not a heading" in ctx.section_text(tmp_path, secs[1])


def test_oversize_sections_are_split_on_blank_lines(tmp_path):
    para = "word " * 300
    doc = tmp_path / "B.md"
    doc.write_text("# Big\n" + "\n\n".join([para] * 12), encoding="utf-8")
    secs = ctx.sections_of(doc, "B.md")
    assert len(secs) > 1 and all(s.chars <= ctx.SECTION_MAX + len(para) + 2 for s in secs)
    assert secs[-1].end == len(doc.read_text(encoding="utf-8").split("\n"))


def test_transcript_turns_skip_tool_output_and_reminders(tmp_path):
    rows = [
        {"type": "user", "timestamp": "2026-09-20T10:00:00Z", "message": {"content": "Please keep commits authored by me only, always."}},
        {"type": "user", "timestamp": "2026-09-20T10:00:01Z", "message": {"content": [{"type": "tool_result", "content": "x" * 500}]}},
        {"type": "assistant", "timestamp": "2026-09-20T10:00:02Z", "message": {"content": [
            {"type": "text", "text": "Understood, I will commit as you with no co-author trailer."},
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]}},
        {"type": "user", "timestamp": "2026-09-20T10:00:03Z", "message": {"content": "<system-reminder>ignore me entirely please</system-reminder>"}},
    ]
    t = tmp_path / "s.jsonl"
    t.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    turns = ctx.turns_of(t)
    assert [x.who for x in turns] == ["user", "claude"]
    assert ctx.turns_of(t, since="2026-09-20T10:00:02") [0].who == "claude"


def test_secrets_are_redacted_before_jev_sees_them():
    text = ("key sk-ant-api03-abcdefghijklmnopqrstuvwx, token: ghp_abcdefghijklmnopqrstuvwxyz0123, "
            "my github_pat_11ABCDEFG0qVZSmr here and 0123456789abcdef0123456789abcdef")
    out = ctx.redact(text)
    for leaked in ("sk-ant-api03", "ghp_abc", "github_pat_11", "0123456789abcdef0123"):
        assert leaked not in out
    assert ctx.redact("Search products") == "Search products"


def test_urls_and_paths_survive_redaction():
    url = "file:///C:/Users/someone/projects/jeverifier/docs/page.html"
    assert ctx.redact(url) == url


def test_code_sections_hold_the_api_and_lists_show_full_heading_paths(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/grid.gd").write_text(
        "class_name Grid\nextends RefCounted\n\n## Cells a unit can reach.\nstatic func reach(cell: Vector2i) -> Array:\n"
        "\tvar out := []\n\treturn out\n", encoding="utf-8")
    secs = ctx.code_sections(tmp_path, ("scripts/**/*.gd",))
    assert [(s.file, s.end) for s in secs] == [("scripts/grid.gd", 8)]
    api = ctx.section_text(tmp_path, secs[0])
    assert "static func reach(cell: Vector2i) -> Array:" in api and "## Cells a unit can reach." in api
    assert "var out" not in api and "return out" not in api  # bodies stay out
    doc = ctx.Section("ARCH.md", 10, 20, "Data > Tags > Known tags", 400, "")
    out = ctx.render_reading_list("t", [(doc, 0.9), (secs[0], 0.8)], 1000)
    assert "`ARCH.md:10-20` — Data > Tags > Known tags" in out and "`scripts/grid.gd` — API" in out
