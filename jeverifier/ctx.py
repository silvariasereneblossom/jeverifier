"""Context harness: keep a project's context readable, and cheap to reload in a fresh session.

  index   Split a repo's Markdown docs into heading sections (plain code, no model) and write a
          human-readable table of contents with file:line ranges and token estimates.
  find    Jev scores every section for relevance to a task; returns a reading list that fits a
          token budget, so a fresh session reads the brief + those sections instead of every doc.
  digest  Jev triages a Claude Code session transcript, turn by turn, into decisions, user
          preferences, open items and status changes; writes a compact, readable digest that the
          handover can be written from without re-reading the transcript.

Jev only selects and labels; it never writes the summaries. Text stays verbatim (trimmed), so
nothing in the digest or reading list is paraphrased by a model.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient, Noul, RetryPolicy

from . import jev

# Secret-looking strings are masked before any text reaches Jev.
_SECRET = re.compile(
    r"(?:sk-[A-Za-z0-9_\-]{16,}|sk-ant-[A-Za-z0-9_\-]{16,}|github_pat_[A-Za-z0-9_]{8,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[abprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+"
    r"|(?:api[_-]?key|token|secret|passw(?:or)?d)[_:=\s-]*[A-Za-z0-9_\-]{12,}"
    r"|\b[A-Fa-f0-9]{32,}\b|\b(?=[A-Za-z0-9+_\-]*\d)[A-Za-z0-9+_\-]{40,}={0,2})",  # no '/': keeps URLs and paths
    re.I,
)


def redact(text: str) -> str:
    return _SECRET.sub("[redacted]", text) if text else text


CHARS_PER_TOKEN = 4  # rough English/Markdown average; good enough for budgets
SECTION_MAX = 6000
OUT = Path(__file__).resolve().parent.parent / "out"  # out/ in the checkout: indexes, review lists, Jev caches
QUESTIONS_PER_REQUEST = 24


def tok(chars: int) -> int:
    return max(1, chars // CHARS_PER_TOKEN)


# ---------------------------------------------------------------- index

@dataclass
class Section:
    file: str
    start: int  # 1-based, inclusive
    end: int
    heading: str  # "Top > Sub > Leaf"
    chars: int
    lead: str  # first sentence, for the human-readable index

    @property
    def id(self) -> str:
        return f"{self.file}:{self.start}"


def _lead(text: str) -> str:
    body = " ".join(l.strip() for l in text.split("\n") if l.strip() and not l.lstrip().startswith(("#", "|", "```", "<")))
    m = re.match(r"(.{20,220}?[.!?])(\s|$)", body)
    return (m.group(1) if m else body[:180]).strip()


def sections_of(path: Path, rel: str) -> list[Section]:
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    heads, fenced = [], False
    for i, l in enumerate(lines):
        if l.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and (m := re.match(r"^(#{1,4})\s+(.*)", l)):  # '#' inside a code fence is not a heading
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    if not heads or heads[0][0] != 0:
        heads.insert(0, (0, 1, rel))
    out, stack = [], []
    for n, (i, level, title) in enumerate(heads):
        stack = [s for s in stack if s[0] < level] + [(level, title)]
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        # split oversize sections on blank lines so each fits one Jev question comfortably
        start = i
        while start < end:
            stop, size = start, 0
            while stop < end and (size < SECTION_MAX or stop == start):
                size += len(lines[stop]) + 1
                stop += 1
            if stop < end:
                back = next((k for k in range(stop, start + 1, -1) if not lines[k - 1].strip()), stop)
                stop = back if back > start + 1 else stop
            text = "\n".join(lines[start:stop])
            if text.strip():
                out.append(Section(rel, start + 1, stop, " > ".join(t for _, t in stack), len(text), _lead(text)))
            start = stop
    return out


def index(repo: Path, globs: tuple[str, ...] = ("*.md", "docs/*.md")) -> list[Section]:
    files = sorted({p for g in globs for p in repo.glob(g) if p.is_file()})
    return [s for p in files for s in sections_of(p, p.relative_to(repo).as_posix())]


def section_text(repo: Path, s: Section) -> str:
    lines = (repo / s.file).read_text(encoding="utf-8", errors="replace").split("\n")
    return "\n".join(lines[s.start - 1:s.end])


def write_index(repo: Path, out_dir: Path) -> Path:
    secs = index(repo)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.json").write_text(json.dumps([asdict(s) for s in secs], indent=1), encoding="utf-8", newline="\n")
    md = [f"# Context index — {repo.name}", "",
          f"{len(secs)} sections, ≈{tok(sum(s.chars for s in secs)):,} tokens in total. "
          "Read a section by its file and line range; `jeverifier ctx find` picks the ones a task needs.", ""]
    for f in sorted({s.file for s in secs}):
        fs = [s for s in secs if s.file == f]
        md += [f"## {f}  (≈{tok(sum(s.chars for s in fs)):,} tokens)", "", "| lines | ≈tok | section | starts with |", "|---|---|---|---|"]
        md += [f"| {s.start}–{s.end} | {tok(s.chars):,} | {s.heading.split(' > ')[-1][:70]} | {s.lead[:110].replace('|', '/')} |" for s in fs]
        md.append("")
    path = out_dir / "CONTEXT_INDEX.md"
    path.write_text("\n".join(md), encoding="utf-8", newline="\n")
    return path


# ---------------------------------------------------------------- find

def _client() -> AsyncTypeSafeClient:
    p = jev.choose()
    kwargs = {"base_url": p.base_url} if p.base_url else {}
    return AsyncTypeSafeClient(api_key=os.environ[p.key_env], model=p.model,  # retries ride out 429s
                               retry=RetryPolicy(max_retries=10, backoff_max=20.0, timeout=120.0), **kwargs)


async def _score_sections(repo: Path, secs: list[Section], task: str, concurrency: int = 8) -> dict[str, float]:
    sem = asyncio.Semaphore(concurrency)
    scores: dict[str, float] = {}
    async with _client() as client:
        async def batch(chunk: list[Section]) -> None:
            qs = {f"s{i}": Noul(instructions={
                      "section": {"where": f"{s.file} — {s.heading}", "text": redact(section_text(repo, s))[:SECTION_MAX]},
                      "question": "Does someone about to do `task` need to read `section` to do it correctly?"},
                      criteria={"true": "The section states rules, structure, decisions or gotchas that `task` touches.",
                                "false": "The section is about other parts of the project, or is history `task` does not depend on."})
                  for i, s in enumerate(chunk)}
            async with sem:
                r = await client.system_one({"task": task}, qs)
            for i, s in enumerate(chunk):
                scores[s.id] = r.nouls[f"s{i}"].noul
        await asyncio.gather(*(batch(secs[i:i + QUESTIONS_PER_REQUEST]) for i in range(0, len(secs), QUESTIONS_PER_REQUEST)))
    return scores


def find(repo: Path, task: str, budget_tokens: int = 25_000, threshold: float = 0.5,
         always: tuple[str, ...] = ()) -> tuple[list[tuple[Section, float]], int]:
    """Sections most relevant to `task`, highest score first, within `budget_tokens`.
    `always` names files that are loaded anyway (e.g. the brief) and so are not scored."""
    secs = [s for s in index(repo) if s.file not in always]
    scores = asyncio.run(_score_sections(repo, secs, task))
    ranked = sorted(secs, key=lambda s: -scores[s.id])
    picked, used = [], 0
    for s in ranked:
        if scores[s.id] < threshold:
            break
        if used + tok(s.chars) > budget_tokens:
            continue
        picked.append((s, scores[s.id]))
        used += tok(s.chars)
    return picked, tok(sum(s.chars for s in secs))


def render_reading_list(task: str, picked: list[tuple[Section, float]], total_tokens: int) -> str:
    used = sum(tok(s.chars) for s, _ in picked)
    out = [f"## Reading list for: {task}", "",
           f"{len(picked)} sections, ≈{used:,} tokens (of ≈{total_tokens:,} across all docs). "
           "Read these ranges; open other sections only if one of these points to them.", ""]
    for s, p in sorted(picked, key=lambda sp: (sp[0].file, sp[0].start)):
        out.append(f"- `{s.file}:{s.start}-{s.end}` — {s.heading.split(' > ')[-1]} (≈{tok(s.chars):,} tok, relevance {p:.2f})")
    return "\n".join(out)


# ---------------------------------------------------------------- digest

KINDS = {
    "decision": ("Does this message record a decision about the project: a choice made, or an approach "
                 "adopted or rejected, with its reason?",
                 "A choice is settled here.", "Only discussion, exploration, progress chatter or tool output."),
    "preference": ("Does the user state a preference, rule or standing instruction for how work should be "
                   "done from now on?",
                   "The user says how they want things done going forward.", "No standing instruction is given."),
    "open": ("Does this message explicitly defer something: name a question, risk, known limitation or task "
             "as unresolved and left for a later time?",
             "It says something is deferred, unresolved, a known gap, or to be done later.",
             "Nothing is deferred. A request being worked on now, a question answered in the same message, "
             "or an offer of next steps is not an open item."),
    "status": ("Does this message report that a milestone, phase, review or significant piece of work was "
               "finished, committed or changed state?",
               "Work is reported done, committed, merged, or its state changed.", "No change of state is reported."),
}
_NOISE = re.compile(r"<(system-reminder|local-command|command-name|task-notification)[\s\S]*?(</\1>|$)", re.I)


def resolve_transcript(session: str) -> Path:
    """A path, a session id (or prefix), or 'latest' (newest transcript of any project)."""
    p = Path(session)
    if p.is_file():
        return p
    root = Path.home() / ".claude" / "projects"
    found = sorted(root.glob("*/*.jsonl") if session == "latest" else root.glob(f"*/{session}*.jsonl"),
                   key=lambda f: f.stat().st_mtime)
    if not found:
        raise FileNotFoundError(f"no transcript matches {session!r} under {root}")
    return found[-1]


@dataclass
class Turn:
    when: str
    who: str
    text: str


def turns_of(transcript: Path, since: str = "", until: str = "~") -> list[Turn]:
    out = []
    for line in transcript.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ts = r.get("timestamp", "")
        if r.get("type") not in ("user", "assistant") or not (since <= ts <= until) or r.get("isSidechain"):
            continue
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
        text = _NOISE.sub("", c or "").strip()
        if len(text) < 40:
            continue
        who = "user" if r["type"] == "user" else "claude"
        if out and out[-1].who == who and who == "claude":
            out[-1].text += "\n\n" + text  # one assistant turn, several text blocks
        else:
            out.append(Turn(ts, who, text))
    return out


async def _triage(turns: list[Turn], concurrency: int = 8) -> list[dict[str, float]]:
    sem = asyncio.Semaphore(concurrency)
    async with _client() as client:
        async def one(t: Turn) -> dict[str, float]:
            qs = {k: Noul(instructions=q, criteria={"true": yes, "false": no}) for k, (q, yes, no) in KINDS.items()}
            async with sem:
                r = await client.system_one({"speaker": t.who, "message": redact(t.text)[:6000]}, qs)
            return {k: r.nouls[k].noul for k in KINDS}
        return await asyncio.gather(*(one(t) for t in turns))


def _excerpt(text: str, limit: int = 420) -> str:
    text = re.sub(r"```[\s\S]*?```", "[code]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def _paragraphs(text: str) -> list[str]:
    text = re.sub(r"```[\s\S]*?```", "", text)
    parts = re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)|\n(?=#)", text)
    return [p.strip() for p in parts if len(p.strip()) >= 30][:40]


async def _best_paragraphs(items: list[tuple[Turn, str]], concurrency: int = 8) -> list[str]:
    """For each (turn, kind), the paragraph(s) that actually carry that kind — the line-by-line
    search pattern — so a long assistant turn is quoted at its decision, not at its preamble."""
    sem = asyncio.Semaphore(concurrency)
    async with _client() as client:
        async def one(t: Turn, kind: str) -> str:
            paras = _paragraphs(t.text)
            if len(paras) <= 1 or len(t.text) <= 600:
                return _excerpt(t.text, 600)
            q, yes, no = KINDS[kind]
            qs = {f"p{i}": Noul(instructions={"paragraph": redact(p)[:2000],
                                              "question": q.replace("this message", "`paragraph` itself")},
                                criteria={"true": yes, "false": no})
                  for i, p in enumerate(paras)}
            async with sem:
                r = await client.system_one({"speaker": t.who}, qs)
            ranked = sorted(range(len(paras)), key=lambda i: -r.nouls[f"p{i}"].noul)
            keep = sorted(ranked[:2] if r.nouls[f"p{ranked[1]}"].noul >= 0.6 else ranked[:1])
            return " … ".join(_excerpt(paras[i], 360) for i in keep)
        return await asyncio.gather(*(one(t, k) for t, k in items))


async def _resolved(quotes: list[str], handover: str, concurrency: int = 8) -> list[float]:
    """P(the handover shows this open item as resolved/decided/done)."""
    sem = asyncio.Semaphore(concurrency)
    async with _client() as client:
        async def batch(chunk: list[str]) -> list[float]:
            qs = {f"i{n}": Noul(instructions={"item": q, "question": "Does `handover` show that `item` has since been "
                                              "answered, decided, done or dropped?"},
                                criteria={"true": "The handover records an outcome for this item.",
                                          "false": "The handover still lists it as open, or does not mention it."})
                  for n, q in enumerate(chunk)}
            async with sem:
                r = await client.system_one({"handover": redact(handover)[:60_000]}, qs)
            return [r.nouls[f"i{n}"].noul for n in range(len(chunk))]
        parts = await asyncio.gather(*(batch(quotes[i:i + 20]) for i in range(0, len(quotes), 20)))
    return [p for part in parts for p in part]


def digest(transcript: Path, since: str = "", until: str = "~", threshold: float = 0.6,
           handover: Path | None = None) -> tuple[str, dict]:
    turns = turns_of(transcript, since, until)
    labels = asyncio.run(_triage(turns))
    titles = {"decision": "Decisions", "preference": "Standing preferences (from the user)",
              "open": "Open items", "status": "Status changes"}
    kept = {k: [(t, l[k]) for t, l in zip(turns, labels) if l[k] >= threshold and (k != "preference" or t.who == "user")]
            for k in KINDS}
    flat = [(t, k) for k in KINDS for t, _ in kept[k]]
    quotes = dict(zip([(id(t), k) for t, k in flat], asyncio.run(_best_paragraphs(flat))))
    resolved: list[tuple[Turn, float]] = []
    if handover is not None and kept["open"]:
        probs = asyncio.run(_resolved([quotes[(id(t), "open")] for t, _ in kept["open"]],
                                      handover.read_text(encoding="utf-8", errors="replace")))
        resolved = [(t, p) for (t, _), p in zip(kept["open"], probs) if p >= threshold]
        kept["open"] = [(t, s) for (t, s), p in zip(kept["open"], probs) if p < threshold]
    span = f"{turns[0].when[:16]} → {turns[-1].when[:16]}" if turns else "(empty)"
    out = [f"# Session digest — {transcript.stem[:8]}", "",
           f"{span} · {len(turns)} conversational turns triaged by Jev; excerpts are verbatim (trimmed), "
           "newest last. Tool output is excluded.", ""]
    for k, title in titles.items():
        out += [f"## {title} ({len(kept[k])})", ""]
        out += [f"- **{t.when[:10]}** · {t.who} · {quotes[(id(t), k)]}" for t, _ in kept[k]] or ["- (none)"]
        out.append("")
    if resolved:
        out += [f"<details><summary>{len(resolved)} open items the handover already resolves</summary>", ""]
        out += [f"- {t.when[:10]} · {_excerpt(quotes[(id(t), 'open')], 160)}" for t, _ in resolved]
        out += ["", "</details>", ""]
    body = "\n".join(out)
    stats = {"turns": len(turns), "turn_chars": sum(len(t.text) for t in turns), "digest_chars": len(body),
             **{f"kept_{k}": len(v) for k, v in kept.items()}, "resolved_open": len(resolved)}
    return body, stats
