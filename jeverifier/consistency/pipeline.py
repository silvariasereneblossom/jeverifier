from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from itertools import combinations
from pathlib import Path
from typesafe_sdk import Noul
import asyncio
import datetime as dt
import json
import math
import re
import tempfile

from .. import ctx
from . import core as rt
from .core import CONTRA, Claim, Store, _Jev, _judge, _judge_same, _kinds, _stem, _tags, claims_of, fingerprint, merge_topics, topics_of, words


TOP_TOPICS, MIN_TOPIC_P = 2, 0.10


NEIGHBOURS = 5


def _pairs(claims: list[Claim], tags: dict[str, list], canon: dict[str, str], current: set[int]) -> set[tuple[int, int]]:
    by_topic = defaultdict(list)
    for i in current:
        agg = defaultdict(float)
        for t, p in tags[claims[i].key]:
            agg[canon.get(t, t)] += p  # merged headings pool their probability
        keep = [t for t, p in sorted(agg.items(), key=lambda kv: -kv[1])[:TOP_TOPICS] if p >= MIN_TOPIC_P and t != "other"]
        for t in keep or [max(agg, key=agg.get)]:
            by_topic[t].append(i)
    topical = {(min(i, j), max(i, j)) for idx in by_topic.values() for i, j in combinations(idx, 2)
               if claims[i].section.id != claims[j].section.id}
    return topical | _neighbours(claims, current)


def _neighbours(claims: list[Claim], current: set[int], per_claim: int = NEIGHBOURS) -> set[tuple[int, int]]:
    """Each claim's closest claims by shared wording (idf-weighted), in any other section. Topics come from
    each document's own headings, so the same fact restated in README and ARCHITECTURE can land under
    unrelated topics; wording catches those. Measured need: 3 of 7 fair plants were never paired by topic."""
    idx = sorted(current)
    ws = {i: words(claims[i].text) for i in idx}
    df = defaultdict(int)
    for i in idx:
        for w in ws[i]:
            df[w] += 1
    n = len(idx)
    by_word = defaultdict(list)
    for i in idx:
        for w in ws[i]:
            if df[w] <= max(8, n // 20):  # words shared by everything pair everything and mean nothing
                by_word[w].append(i)
    out = set()
    for i in idx:
        score = defaultdict(float)
        for w in ws[i]:
            for j in by_word.get(w, ()):
                if j != i and claims[j].section.id != claims[i].section.id:
                    score[j] += math.log(n / df[w])
        for j, _ in sorted(score.items(), key=lambda kv: -kv[1])[:per_claim]:
            out.add((min(i, j), max(i, j)))
    return out


# ---------------------------------------------------------------- the number check (code finds, Jev confirms)
#
# Two current-state statements that count the same thing with different numbers cannot both be right. Code
# does the arithmetic part (extracting quantities, normalising "three" = 3, spotting different values);
# Jev only answers the judgment code cannot: are these two counts of the SAME specific thing?

_WORDNUM = {w: n for n, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}


# A standalone number (not a section ref §11, not part of 4,979 / 1.5 / 40%, not inside a path or identifier)
# followed by the word it counts.
_QTYN = re.compile(r"(?<![\w§#/.,\-])(\d{1,4}|" + "|".join(_WORDNUM) + r")(?![\w,.%/]|\.\d)\s+([A-Za-z][A-Za-z-]{2,})", re.I)


_GENERIC_NOUNS = {"thing", "that", "place", "time", "way", "other", "more", "less", "the", "and", "for", "per", "than",
                  "each", "new", "old", "one", "part", "case", "step", "line"}  # "line" alone is too generic; "lines" stems to "lin"


NUM_REVIEW = 50


NUMERIC = {"true": "They count or measure the same specific thing in the same scope, so the two numbers cannot both be right.",
           "false": "They count different things, or the same kind of thing in a different scope, case, file, phase or time."}


def quantities(text: str) -> list[tuple[int, str, str]]:
    """(value, counted-noun stem, the words as written) for each stated quantity in `text`."""
    out = []
    for m in _QTYN.finditer(text):
        tok, noun = m.group(1).lower(), m.group(2)
        stem = _stem(noun)
        if stem not in _GENERIC_NOUNS:
            out.append((int(tok) if tok.isdigit() else _WORDNUM[tok], stem, m.group(0)))
    return out


def numeric_pairs(claims: list[Claim], current: set[int]) -> list[tuple[int, int, str, str]]:
    """Pairs of current claims in different sections that count the same noun with different numbers."""
    by_stem = defaultdict(list)
    for i in sorted(current):
        for value, stem, span in quantities(claims[i].text):
            by_stem[stem].append((i, value, span))
    out = {}
    for items in by_stem.values():
        for a, b in combinations(items, 2):
            (i, vi, si), (j, vj, sj) = sorted((a, b))
            if vi != vj and claims[i].section.id != claims[j].section.id and (i, j) not in out:
                out[(i, j)] = (i, j, si, sj)
    return list(out.values())


async def _judge_numeric(jv: _Jev, claims: list[Claim], pairs, cache: dict) -> list[float]:
    keys = [f"N:{fingerprint(claims[i], claims[j])}:{si}|{sj}" for i, j, si, sj in pairs]
    todo = [(k, p) for k, p in zip(keys, pairs) if k not in cache]
    jv.afford(f"checking {len(todo):,} number pairs", sum(ctx.tok(len(claims[i].text) + len(claims[j].text)) + 120
                                                         for _, (i, j, _, _) in todo))

    async def batch(chunk):
        r = await jv.call({"context": "Two statements from the docs of one software project that state different numbers."},
                          {f"q{n}": Noul(instructions={"first": claims[i].text, "second": claims[j].text,
                                                       "first_says": si, "second_says": sj,
                                                       "question": "Are `first_says` and `second_says` counts of the same "
                                                                   "specific thing, in the same scope?"}, criteria=NUMERIC)
                           for n, (_, (i, j, si, sj)) in enumerate(chunk)})
        for n, (k, _) in enumerate(chunk):
            cache[k] = r.nouls[f"q{n}"].noul
    await asyncio.gather(*(batch(todo[i:i + 40]) for i in range(0, len(todo), 40)))
    return [cache[k] for k in keys]


SECOND_STAGE, REVIEW = 2000, 130  # 130: two valid plants ranked 109 and 127 (2026-09-24)


@dataclass
class Result:
    claims: list[Claim]
    ranked: list[tuple[float, float, float, int, int]]  # score, contra, same, i, j
    kinds: dict[str, str]  # section id -> current / history / plan
    scores: dict[tuple[int, int], tuple[float, float | None]]  # every judged pair: (contra, same or None)
    stats: dict
    numeric: list[tuple[float, int, int, str, str]] = field(default_factory=list)  # P(same thing), i, j, both quantities


async def _pipeline(repo: Path, secs: list[ctx.Section], store: Store, max_cost: float | None = None) -> Result:
    claims = claims_of(repo, secs)
    topics = topics_of(secs)
    canon = merge_topics(topics)
    judged = store.load("judged")
    try:
        async with rt._client() as client:
            jv = _Jev(client, max_cost)
            kinds = await _kinds(jv, repo, secs, store)
            current = {i for i, c in enumerate(claims) if kinds[c.section.id] == "current"}
            tags = await _tags(jv, [claims[i] for i in sorted(current)], topics, store)  # history/plan claims are never paired
            cand = _pairs(claims, tags, canon, current)
            suppressed = {vid for vid, v in store.verdicts().items() if v["verdict"] == "false-alarm"}
            pairs = sorted(pq for pq in cand if fingerprint(claims[pq[0]], claims[pq[1]]) not in suppressed)
            contra = await _judge(jv, claims, pairs, CONTRA, "Do `first` and `second` contradict each other?", judged, "c")
            stage1 = sorted(zip(contra, pairs), reverse=True)[:SECOND_STAGE]
            same = await _judge_same(jv, claims, [pq for _, pq in stage1], judged)
            npairs = [p for p in numeric_pairs(claims, current)
                      if fingerprint(claims[p[0]], claims[p[1]]) not in suppressed]
            nsame = await _judge_numeric(jv, claims, npairs, judged)
    finally:
        store.save("judged", judged)  # judged pairs are kept even when a run is cut off
    numeric = sorted(((p, i, j, si, sj) for p, (i, j, si, sj) in zip(nsame, npairs)), reverse=True)
    scores = {pq: (c, None) for c, pq in zip(contra, pairs)} | {pq: (c, s) for (c, pq), s in zip(stage1, same)}
    ranked = sorted(((c * s, c, s, i, j) for (c, (i, j)), s in zip(stage1, same)), reverse=True)
    stats = {"sections": len(secs), "claims": len(claims), "topics": len(set(canon.values())),
             "current_sections": sum(k == "current" for k in kinds.values()), "current_claims": len(current),
             "pairs_current": len(cand), "suppressed": len(cand) - len(pairs), "pairs_judged": len(pairs),
             "number_pairs": len(npairs), "jev_tokens": jv.spent, "cost_usd": round(jv.spent / 1e6 * 0.042, 3)}
    return Result(claims, ranked, kinds, scores, stats, numeric)


def run(repo: Path, secs: list[ctx.Section], cache_name: str | None = None, max_cost: float | None = None) -> Result:
    return asyncio.run(_pipeline(repo, secs, Store(repo, cache_name), max_cost))


# ---------------------------------------------------------------- delta mode
#
# After a review, `accept` records the text of every claim as reviewed (baseline.json, in the repo so it
# travels with the verdicts). A later `check` then lists only pairs in which at least one statement is new
# or changed since then, above a score floor -- the repetitive part Jev can carry. `--deep` shows the full
# ranking instead. Floors are set below every planted contradiction the self-test found (2026-09-24:
# general contra >= 0.72, number same >= 0.54), with margin; `selftest --delta` re-measures them.

DELTA_MIN_CONTRA = 0.5


DELTA_MIN_SAME_NUMBER = 0.45


def delta(res: Result, baseline: set[str], top: int = REVIEW, top_numbers: int = NUM_REVIEW):
    """(general, numeric) restricted to pairs touching a claim whose text is not in `baseline`."""
    new = {i for i, c in enumerate(res.claims) if c.key not in baseline}
    general = [r for r in res.ranked if (r[3] in new or r[4] in new) and r[1] >= DELTA_MIN_CONTRA][:top]
    numeric = [r for r in res.numeric if (r[1] in new or r[2] in new) and r[0] >= DELTA_MIN_SAME_NUMBER][:top_numbers]
    return general, numeric, new


def accept(repo: Path, git_ref: str | None = None) -> tuple[Path, dict]:
    """Record the current claim texts (or those at `git_ref` for tracked files) as reviewed."""
    from ..wiki import _wiki_and_docs

    secs = _wiki_and_docs(repo)
    if git_ref is None:
        keys = {c.key for c in claims_of(repo, secs)}
    else:
        import subprocess

        with tempfile.TemporaryDirectory(prefix="jeverifier-accept-") as tmp:
            root = Path(tmp)
            for f in {s.file for s in secs}:
                shown = subprocess.run(["git", "-C", str(repo), "show", f"{git_ref}:{f}"], capture_output=True)
                (root / f).parent.mkdir(parents=True, exist_ok=True)
                # untracked files (e.g. a wiki not committed yet) are taken as they are now
                (root / f).write_bytes(shown.stdout if shown.returncode == 0 else (repo / f).read_bytes())
            keys = {c.key for c in claims_of(root, _wiki_and_docs(root))}
    data = {"accepted": dt.datetime.now().isoformat(timespec="seconds"), "ref": git_ref or "working tree",
            "claims": sorted(keys)}
    return Store(repo, model="-").save_baseline(data), {"claims": len(keys), "ref": data["ref"]}


# ---------------------------------------------------------------- 7: the review list

def report(repo: Path, res: Result, top: int = REVIEW, top_numbers: int = NUM_REVIEW,
           ranked=None, numeric=None, mode: str = "") -> tuple[str, list[dict]]:
    today = dt.date.today().isoformat()
    s = res.stats
    ranked = res.ranked[:top] if ranked is None else ranked
    numeric = res.numeric[:top_numbers] if numeric is None else numeric

    def item(kind, i, j, **extra):
        a, b = res.claims[i], res.claims[j]
        return {"id": fingerprint(a, b), "list": kind, **extra,
                "a": {"where": f"{a.section.file}:{a.line}", "text": a.text},
                "b": {"where": f"{b.section.file}:{b.line}", "text": b.text}}

    numbers = [item("numbers", i, j, same=round(p, 3), says=[si, sj]) for p, i, j, si, sj in numeric]
    general = [item("general", i, j, score=round(score, 3), contra=round(c, 3), same=round(sm, 3))
               for score, c, sm, i, j in ranked]
    out = [f"# Consistency check — {repo.resolve().name} — {today}", "",
           *([mode, ""] if mode else []),
           f"{s['claims']:,} claims in {s['sections']} sections ({s['current_sections']} current); "
           f"{s.get('number_pairs', 0):,} number pairs and {s['pairs_judged']:,} other current-state pairs judged "
           f"({s['suppressed']} known false alarms skipped); Jev cost ${s['cost_usd']}.", "",
           "**Jev ranks; it does not decide.** Review each pair (Protocol 2) and record the verdict so the list "
           "improves: `jeverifier wiki verdict <repo> <id> contradiction|stale|false-alarm --note \"...\"`. A false alarm "
           "is not shown again until either statement changes. Not covered: contradictions inside one section, and "
           "statements without a number or rule word — Protocol 2's sampled pairs cover those.", "",
           f"## Number mismatches ({len(numbers)})", "",
           "Two statements counting the same thing with different numbers; code found the numbers, Jev judged "
           "whether they count the same thing.", ""]
    for n, it in enumerate(numbers, 1):
        out += [f"### N{n}. `{it['id']}` · same thing {it['same']:.2f} · “{it['says'][0]}” vs “{it['says'][1]}”", "",
                f"- `{it['a']['where']}` — {it['a']['text']}",
                f"- `{it['b']['where']}` — {it['b']['text']}", ""]
    if not numbers:
        out += ["No number mismatches.", ""]
    out += [f"## Other possible contradictions ({len(general)})", ""]
    items = numbers + general
    for n, it in enumerate(general, 1):
        out += [f"### {n}. `{it['id']}` · score {it['score']:.2f} (contradict {it['contra']:.2f} × same {it['same']:.2f})", "",
                f"- `{it['a']['where']}` — {it['a']['text']}",
                f"- `{it['b']['where']}` — {it['b']['text']}", ""]
    if not general:
        out.append("No pairs to review.")
    return "\n".join(out) + "\n", items


def check(repo: Path, top: int = REVIEW, max_cost: float | None = 1.0, deep: bool = False) -> tuple[Path, dict]:
    """Delta mode when a baseline exists (only pairs touching new or changed statements, above the floors);
    the full ranking on a first run or with deep=True."""
    from ..wiki import _wiki_and_docs

    res = run(repo, _wiki_and_docs(repo), max_cost=max_cost)
    base = Store(repo, model="-").baseline()
    if base is None or deep:
        why = "no baseline yet (first run)" if base is None else "--deep"
        mode = (f"**Full ranking** ({why}): the top {top} pairs and top {NUM_REVIEW} number mismatches. After the "
                "review, record verdicts and run `jeverifier wiki accept <repo>` so later checks show only what changed.")
        text, items = report(repo, res, top, mode=mode)
        res.stats.update(mode="full")
    else:
        general, numeric, new = delta(res, set(base["claims"]), top)
        mode = (f"**Delta** since the review accepted {base['accepted']} ({base['ref']}): {len(new):,} new or changed "
                f"statements; only pairs touching one of them, with contradiction ≥ {DELTA_MIN_CONTRA} (general) or "
                f"same-thing ≥ {DELTA_MIN_SAME_NUMBER} (numbers). `--deep` shows the full ranking.")
        text, items = report(repo, res, top, ranked=general, numeric=numeric, mode=mode)
        res.stats.update(mode="delta", new_claims=len(new), listed=len(items))
    dest = rt.OUT / repo.resolve().name / f"consistency-{dt.date.today().isoformat()}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8", newline="\n")
    dest.with_suffix(".json").write_text(json.dumps({"stats": res.stats, "pairs": items}, ensure_ascii=False, indent=1),
                                         encoding="utf-8", newline="\n")
    return dest, res.stats
