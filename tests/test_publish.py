"""Publishing to the public mirror, offline: allowlist, link rewriting, internal marker and deny list."""

from __future__ import annotations

import json

import pytest

from jeverifier import publish

URL = "https://github.com/me/pub"


def make_repo(tmp_path, deny=("secretproject",)):
    (tmp_path / "docs/wiki/sessions").mkdir(parents=True)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "private.txt").write_text("not listed\n", encoding="utf-8")
    (tmp_path / "docs/wiki/home.md").write_text(
        "# Home\n\n- [How](how.md#setup) — details\n- [Logs](sessions/index.md) — internal\n"
        "See [a.py](../../pkg/a.py).\n", encoding="utf-8")
    (tmp_path / "docs/wiki/how.md").write_text("# How\n\n## Setup\n\nBack [home](home.md).\n", encoding="utf-8")
    (tmp_path / "docs/wiki/sessions/index.md").write_text("<!-- INTERNAL ONLY -->\n# Logs\n", encoding="utf-8")
    (tmp_path / "publish.json").write_text(json.dumps({
        "repo_url": URL, "files": ["pkg/*.py"], "deny": list(deny),
        "wiki": {"docs/wiki/home.md": "Home", "docs/wiki/how.md": "How-It-Works"}}), encoding="utf-8")
    return tmp_path


def test_publish_mirrors_only_the_allowlist_and_rewrites_links(tmp_path):
    repo, dest = make_repo(tmp_path / "repo"), tmp_path / "pub"
    (dest / ".git").mkdir(parents=True)
    (dest / "stale.md").write_text("old\n", encoding="utf-8")
    assert publish.publish(repo, dest) == ["pkg/a.py", "wiki/Home.md", "wiki/How-It-Works.md"]
    home = (dest / "wiki/Home.md").read_text(encoding="utf-8")
    assert "- [How](How-It-Works#setup) — details" in home and "Logs" not in home
    assert f"[a.py]({URL}/blob/main/pkg/a.py)" in home
    assert (dest / ".git").exists() and not (dest / "stale.md").exists() and not (dest / "private.txt").exists()


def test_internal_pages_links_and_denied_text_stop_the_publish(tmp_path):
    repo = make_repo(tmp_path / "repo", deny=("x = 1",))
    with pytest.raises(publish.PublishError, match="pkg/a.py: 'x = 1'"):
        publish.plan(repo)
    repo = make_repo(tmp_path / "repo2")
    m = json.loads((repo / "publish.json").read_text(encoding="utf-8"))
    m["wiki"]["docs/wiki/sessions/index.md"] = "Logs"
    (repo / "publish.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(publish.PublishError, match="marked internal only"):
        publish.plan(repo)
    (repo / "docs/wiki/how.md").write_text("Prose link to [logs](sessions/index.md).\n", encoding="utf-8")
    del m["wiki"]["docs/wiki/sessions/index.md"]
    (repo / "publish.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(publish.PublishError, match="not published"):
        publish.plan(repo)
