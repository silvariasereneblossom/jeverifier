from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typesafe_sdk import AsyncTypeSafeClient
from typesafe_sdk import Choice, Noul
import asyncio
import datetime as dt
import hashlib
import json
import re

from .. import jev
from .. import ctx
from ..model import redact


CONCURRENCY = 4  # TypeSafe allows 250k tokens/s; tagging requests are large


OUT = ctx.OUT


def _model() -> str:
    return jev.choose().model


# ---------------------------------------------------------------- 3-6: Jev stages

_client = ctx._client  # one client factory (with retries) for every Jev caller


class CostLimit(RuntimeError):
    """Raised before a stage would push a run past its budget; nothing for that stage was spent."""


PRICE_PER_TOKEN = 0.042 / 1e6


class _Jev:
    """One client, one concurrency limit, one token counter and one budget, for every stage of a run."""

    def __init__(self, client: AsyncTypeSafeClient, max_cost: float | None = None) -> None:
        self.client, self.sem, self.spent = client, asyncio.Semaphore(CONCURRENCY), 0
        self.max_cost = max_cost

    def afford(self, stage: str, est_tokens: int) -> None:
        """Refuse a stage whose estimate would take the run past max_cost (checked before any request)."""
        if self.max_cost is None or est_tokens == 0:
            return
        total = (self.spent + est_tokens) * PRICE_PER_TOKEN
        if total > self.max_cost:
            raise CostLimit(f"{stage} would bring this run to about ${total:.2f}, over the --max-cost limit of "
                            f"${self.max_cost:.2f} (spent so far ${self.spent * PRICE_PER_TOKEN:.2f}). Nothing was "
                            "sent for this stage; raise --max-cost to continue. Earlier stages are cached.")

    async def call(self, state, qs):
        async with self.sem:
            r = await self.client.system_one(state, qs)
        self.spent += r.usage.input_tokens
        return r


_CUE = re.compile(r"\d|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|hundred|"
                  r"must|never|always|only|every|each|no|none|at most|at least|cap|caps|limit|exactly|all|"
                  r"may|should|shall|cannot|directly)\b", re.I)


_STOP = set("""the a an and or of to in on for with by is are was were be been being this that these those it its as at from
not but if then than so such into onto over under which who whom whose what when where why how there here they them
their our we you your he she his her also can may will would should could does did done has have had more most less
same other only just very each every all any some no nor per via""".split())


@dataclass
class Claim:
    section: ctx.Section
    line: int
    text: str

    @property
    def key(self) -> str:
        return _hash(self.text)


def _hash(text: str) -> str:
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:16]


def fingerprint(a: Claim, b: Claim) -> str:
    """Stable id of a pair: changes when either claim's text changes, not when lines move."""
    return _hash("\n".join(sorted((" ".join(a.text.split()), " ".join(b.text.split())))))[:12]


# ---------------------------------------------------------------- 1-2: claims and topics

def claims_of(repo: Path, secs: list[ctx.Section]) -> list[Claim]:
    out = []
    for s in secs:
        lines = ctx.section_text(repo, s).split("\n")
        para, start, fenced = [], 0, False
        units: list[tuple[int, str]] = []
        for i, l in enumerate(lines + [""]):
            if l.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            boundary = not l.strip() or l.lstrip().startswith(("#", "|", "- ", "* ")) or re.match(r"\s*\d+\.\s", l)
            if boundary and para:
                units.append((start, " ".join(para)))
                para = []
            if l.strip().startswith("|"):
                units.append((i, l.strip()))  # a table row is one claim
            elif l.strip() and not l.lstrip().startswith("#"):
                if not para:
                    start = i
                para.append(l.strip().lstrip("-* "))
        for i, text in units:
            for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z`*(])", text):
                sent = sent.strip()
                if 30 <= len(sent) <= 900 and _CUE.search(sent):
                    out.append(Claim(s, s.start + i, redact(sent)))
    return out


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9_]{3,}", text.lower()) if w not in _STOP}


def topics_of(secs: list[ctx.Section]) -> list[str]:
    heads = set()
    for s in secs:
        for h in s.heading.split(" > ")[:3]:
            t = re.sub(r"^[\d.]+\s*", "", re.sub(r"[`*]", "", h)).strip()
            if 3 <= len(t) <= 90:
                heads.add(t)
    return sorted(heads)[:250]  # a Choice takes at most 255 options


def merge_topics(topics: list[str]) -> dict[str, str]:
    """Map a heading onto the shortest heading whose words it starts with ("Determinism is inherited,
    and asserted" -> "Determinism"), so one subject is one topic."""
    w = {t: re.findall(r"[a-z0-9]+", t.lower()) for t in topics}
    canon = {}
    for t in topics:
        prefixes = [u for u in topics if u != t and w[u] and w[t][:len(w[u])] == w[u]]
        canon[t] = min(prefixes, key=lambda u: len(w[u])) if prefixes else t
    return canon


def _stem(word: str) -> str:
    w = word.lower()
    for suffix in ("ing", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    return w


VERDICTS = ("contradiction", "stale", "false-alarm")


# ---------------------------------------------------------------- caches, verdicts, overrides

class Store:
    """Machine caches live outside the repo (out/<name>/cache); the owner's verdicts and kind overrides
    live in the repo (docs/wiki/checks/), versioned with the docs they judge."""

    def __init__(self, repo: Path, cache_name: str | None = None, model: str | None = None) -> None:
        # One cache per model: answers from different Jev versions or providers must never mix.
        model = model or _model()
        self.cache_dir = OUT / (cache_name or repo.resolve().name) / "cache" / re.sub(r"[^\w.-]+", "_", model)
        self.checks = repo / "docs" / "wiki" / "checks"

    def load(self, name: str) -> dict:
        p = self.cache_dir / f"{name}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def save(self, name: str, data: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8", newline="\n")

    def verdicts(self) -> dict[str, dict]:
        p = self.checks / "verdicts.jsonl"
        out = {}
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    v = json.loads(line)
                    out[v["id"]] = v  # the latest verdict for a pair wins
        return out

    def kind_overrides(self) -> dict[str, str]:
        p = self.checks / "kinds.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def baseline(self) -> dict | None:
        """The reviewed state delta mode compares against: {"accepted", "ref", "claims": [text hashes]}."""
        p = self.checks / "baseline.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def save_baseline(self, data: dict) -> Path:
        self.checks.mkdir(parents=True, exist_ok=True)
        p = self.checks / "baseline.json"
        p.write_text(json.dumps(data, indent=0), encoding="utf-8", newline="\n")
        return p


def record_verdict(repo: Path, pair_id: str, verdict: str, note: str = "", report: Path | None = None) -> dict:
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
    entry = {"id": pair_id, "verdict": verdict, "note": note, "date": dt.date.today().isoformat()}
    if report and report.with_suffix(".json").exists():
        pairs = {p["id"]: p for p in json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))["pairs"]}
        if pair_id in pairs:
            entry.update(a=pairs[pair_id]["a"], b=pairs[pair_id]["b"])  # keep the evidence with the verdict
    checks = repo / "docs" / "wiki" / "checks"
    checks.mkdir(parents=True, exist_ok=True)
    with (checks / "verdicts.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def section_key(s: ctx.Section) -> str:
    return f"{s.file}#{s.heading}"


def override_kind(overrides: dict[str, str], s: ctx.Section) -> str | None:
    """The owner's correction for a section: an exact "file#heading path" entry wins, then the longest
    folder or file prefix ("docs/contracts/" -> every archived contract, now and later)."""
    if section_key(s) in overrides:
        return overrides[section_key(s)]
    prefixes = [k for k in overrides if "#" not in k and s.file.startswith(k)]
    return overrides[max(prefixes, key=len)] if prefixes else None


KINDS = {
    "current": "Describes how the project is now: its structure, rules in force, behavior, or current status.",
    "history": "A record of the past: a finished milestone, a review's findings, an audit or measurement taken at a "
               "stated time, a changelog, or how something used to be.",
    "plan": "Future work: a proposal, a planned milestone, open design questions, or something not built yet.",
}


CONTRA = {"true": "Both describe the project as it is now and disagree: a different number, limit, count, name, rule, "
                  "order or behavior for the same thing.",
          "false": "They agree, are about different things, or one is explicitly history (\"was\", \"used to\", "
                   "\"before\", a dated entry) that the other updates."}


SAME = {"true": "Both state something about the same specific rule, value, count, component or behavior.",
        "false": "They are about different things, even if the wording overlaps."}


async def _kinds(jv: _Jev, repo: Path, secs: list[ctx.Section], store: Store) -> dict[str, str]:
    cache = store.load("kinds")
    texts = {s.id: ctx.section_text(repo, s)[:ctx.SECTION_MAX] for s in secs}
    todo = [s for s in secs if _hash(texts[s.id]) not in cache]
    jv.afford("labelling sections", sum(ctx.tok(len(texts[s.id])) + 120 for s in todo))

    async def batch(chunk):
        r = await jv.call({"context": "One section of a software project's docs."},
                          {f"k{n}": Choice(instructions={"section": {"where": f"{s.file} — {s.heading}", "text": texts[s.id]},
                                                         "question": "What kind of text is `section`?"}, criteria=KINDS)
                           for n, s in enumerate(chunk)})
        for n, s in enumerate(chunk):
            cache[_hash(texts[s.id])] = r.choices[f"k{n}"].choice
    try:
        await asyncio.gather(*(batch(todo[i:i + 10]) for i in range(0, len(todo), 10)))
    finally:
        store.save("kinds", cache)  # keep what was paid for even if a later request fails
    return {s.id: override_kind(store.kind_overrides(), s) or cache[_hash(texts[s.id])] for s in secs}


async def _tags(jv: _Jev, claims: list[Claim], topics: list[str], store: Store) -> dict[str, list]:
    cache = store.load("tags")
    topic_hash = _hash("\n".join(topics))
    todo = [c for c in claims if f"{topic_hash}:{c.key}" not in cache]
    crit = {f"t{i}": t for i, t in enumerate(topics)} | {"other": "None of these topics."}
    topic_tokens = ctx.tok(sum(len(t) + 8 for t in topics))  # every tagging question carries the whole topic list
    jv.afford("tagging claims", sum(topic_tokens + ctx.tok(len(c.text)) + 20 for c in todo))

    async def batch(chunk):
        r = await jv.call({"context": "Statements from the docs of one software project."},
                          {f"c{k}": Choice(instructions={"claim": c.text, "question": "Which topic is `claim` about?"},
                                           criteria=crit) for k, c in enumerate(chunk)})
        for k, c in enumerate(chunk):
            top5 = sorted(r.choices[f"c{k}"].probabilities.items(), key=lambda kv: -kv[1])[:5]
            cache[f"{topic_hash}:{c.key}"] = [(t if t == "other" else topics[int(t[1:])], p) for t, p in top5]
    try:
        await asyncio.gather(*(batch(todo[i:i + 8]) for i in range(0, len(todo), 8)))
    finally:
        store.save("tags", cache)
    return {c.key: cache[f"{topic_hash}:{c.key}"] for c in claims}


async def _judge(jv: _Jev, claims: list[Claim], pairs, crit: dict, question: str, cache: dict, prefix: str) -> list[float]:
    """Noul per pair, cached by the pair's text fingerprint: a pair is only ever paid for once."""
    keys = [f"{prefix}:{fingerprint(claims[i], claims[j])}" for i, j in pairs]
    todo = [(k, pq) for k, pq in zip(keys, pairs) if k not in cache]
    jv.afford(f"judging {len(todo):,} pairs", sum(ctx.tok(len(claims[i].text) + len(claims[j].text)) + 90 for _, (i, j) in todo))

    async def batch(chunk):
        r = await jv.call({"context": "Two statements from the docs of one software project."},
                          {f"q{n}": Noul(instructions={"first": claims[i].text, "second": claims[j].text,
                                                       "question": question}, criteria=crit)
                           for n, (_, (i, j)) in enumerate(chunk)})
        for n, (k, _) in enumerate(chunk):
            cache[k] = r.nouls[f"q{n}"].noul
    await asyncio.gather(*(batch(todo[i:i + 40]) for i in range(0, len(todo), 40)))
    return [cache[k] for k in keys]


async def _judge_same(jv: _Jev, claims: list[Claim], pairs, cache: dict) -> list[float]:
    """P(same specific thing) per pair. A yes/no Noul: measured 2026-09-24 (10 valid plants, OpenJEV) at 4/10 in
    the top 100, against 1/10 for a 3-level Score, which calls pairs with different numbers "different scope"."""
    return await _judge(jv, claims, pairs, SAME, "Are `first` and `second` about the same specific thing?", cache, "s")
