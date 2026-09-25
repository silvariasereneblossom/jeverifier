"""`jeverifier wiki publish`: mirror a private repo's public parts into a public checkout.

`publish.json` at the repo root is an allowlist: `files` (globs, copied as they are) and `wiki` (internal page ->
public GitHub Wiki page name). Everything else stays private. On the way out, relative links become wiki page
names or GitHub URLs; a list item linking to an unpublished page is dropped, and any other such link is an error.
Nothing is written if a mirrored wiki page starts with <!-- INTERNAL ONLY --> or any output contains a `deny` text.
The public repo's Action then copies wiki/ to its GitHub Wiki.
"""

from __future__ import annotations

import json
import posixpath
import re
import shutil
from pathlib import Path

INTERNAL = "<!-- INTERNAL ONLY -->"
LINK = re.compile(r"\]\((?!https?:|mailto:|#)([^)\s#]+)(#[^)\s]*)?\)")


class PublishError(RuntimeError):
    pass


def _internal(text: str) -> bool:
    return next((s for s in (line.strip() for line in text.splitlines()) if s and s != "---"), "") == INTERNAL


def _links(text: str, src: str, files: set[str], wiki: dict[str, str], url: str) -> str:
    out = []
    for line in text.split("\n"):
        dropped = False

        def sub(m):
            nonlocal dropped
            target, anchor = posixpath.normpath(posixpath.join(posixpath.dirname(src), m.group(1))), m.group(2) or ""
            if target in wiki:
                return f"]({wiki[target]}{anchor})"
            if target in files:
                return f"]({url}/blob/main/{target}{anchor})"
            if line.lstrip().startswith("- "):
                dropped = True
                return m.group(0)
            raise PublishError(f"{src} links to {target}, which is not published")
        line = LINK.sub(sub, line)
        if not dropped:
            out.append(line)
    return "\n".join(out)


def plan(repo: Path) -> dict[str, str]:
    """Every public path and its text, checked; raises PublishError before anything is written."""
    m = json.loads((repo / "publish.json").read_text(encoding="utf-8"))
    files = sorted({p.relative_to(repo).as_posix() for g in m["files"] for p in repo.glob(g) if p.is_file()})
    out = {f: (repo / f).read_text(encoding="utf-8") for f in files}
    for src, name in m["wiki"].items():
        out[f"wiki/{name}.md"] = _links((repo / src).read_text(encoding="utf-8"), src, set(files), m["wiki"], m["repo_url"])
    marked = [p for p in m["wiki"] if _internal((repo / p).read_text(encoding="utf-8"))]
    hits = [f"{path}: {d!r}" for path, text in out.items() for d in m["deny"] if d.lower() in text.lower()]
    if marked or hits:
        raise PublishError("not published:\n  " + "\n  ".join([f"{p}: marked internal only" for p in marked] + hits))
    return out


def publish(repo: Path, dest: Path) -> list[str]:
    """Make `dest` (a checkout of the public repo) hold exactly the planned files; its .git is left alone."""
    out = plan(repo)
    for p in dest.iterdir():
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    for rel, text in out.items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (dest / rel).write_text(text, encoding="utf-8", newline="\n")
    return sorted(out)
